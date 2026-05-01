"""Certificate lifecycle — single source of truth for teardown.

This module is imported verbatim by **two** call sites:

1. ``sbc iot decommission-thing`` / ``sbc iot list-orphan-certs`` (operator CLI).
2. The CDK custom-resource Lambda's ``Delete`` event handler (``infra/cdk/
   lambda/provision_device/handler.py``).

Keep this file dependency-light: stdlib + ``boto3``. No click, no rich, no
pydantic, no awsiotsdk. Errors are propagated; ``ResourceNotFoundException``
is swallowed at every step so the function is idempotent against partial
prior state.

Sequence (Delete):

1. ``ListThingPrincipals`` → for each cert principal:
   a. ``DetachThingPrincipal``.
   b. ``DetachPolicy(policy_name, target=certArn)`` if a policy_name is given.
   c. ``UpdateCertificate(status='INACTIVE')``.
   d. ``DeleteCertificate(forceDelete=force_delete_certificate)``.
2. ``DeleteSecret(RecoveryWindowInDays=recovery_window_days)`` unless
   ``keep_secret=True``.

Never log private keys. The Secrets Manager ``SecretString`` is referenced
only by ARN/name in this module; no value is read here.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any

from sbc_config.modules.iot.client import (
    iot_client as _iot_client_factory,
)
from sbc_config.modules.iot.client import (
    secrets_client as _secrets_client_factory,
)

_DEFAULT_LOGGER = logging.getLogger("sbc_config.iot.lifecycle")


@dataclass
class DecommissionResult:
    """Structured outcome of ``decommission_thing``.

    Useful for both Lambda (returned in the CFN ``Data`` block as audit info)
    and the CLI (rendered as a Rich summary).
    """

    thing_name: str
    detached_principals: list[str] = field(default_factory=list)
    detached_policies: list[str] = field(default_factory=list)
    inactivated_certificates: list[str] = field(default_factory=list)
    deleted_certificates: list[str] = field(default_factory=list)
    deleted_secret: str | None = None
    secret_kept: bool = False
    not_found: list[str] = field(default_factory=list)


def _swallow_not_found(
    operation: str,
    fn: Any,
    *args: Any,
    logger: logging.Logger,
    not_found: list[str],
    **kwargs: Any,
) -> Any:
    """Call ``fn(*args, **kwargs)`` and swallow ``ResourceNotFoundException``."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code in {
            "ResourceNotFoundException",
            "ResourceNotFound",
            "NotFoundException",
        }:
            logger.info("%s: resource missing (already gone) — skipping", operation)
            not_found.append(operation)
            return None
        raise


def _list_thing_principals(iot: Any, thing_name: str) -> list[str]:
    """Return certificate ARNs currently attached to ``thing_name``.

    Returns an empty list if the Thing does not exist (idempotent for repeat
    deletes).
    """
    try:
        page = iot.list_thing_principals(thingName=thing_name)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code in {"ResourceNotFoundException", "NotFoundException"}:
            return []
        raise
    return list(page.get("principals", []))


def _certificate_id_from_arn(cert_arn: str) -> str:
    """``arn:aws:iot:us-west-2:123:cert/abcd…`` → ``abcd…``."""
    if "/" not in cert_arn:
        msg = f"not an IoT certificate ARN: {cert_arn!r}"
        raise ValueError(msg)
    return cert_arn.rsplit("/", 1)[1]


def _is_cert_principal(arn: str) -> bool:
    """True if the principal ARN refers to an X.509 cert (vs Cognito etc.)."""
    return ":cert/" in arn


def decommission_thing(
    thing_name: str,
    *,
    policy_name: str | None = None,
    secret_id: str | None = None,
    iot_client: Any | None = None,
    secrets_client: Any | None = None,
    keep_secret: bool = False,
    force_delete_certificate: bool = False,
    recovery_window_days: int = 7,
    logger: logging.Logger | None = None,
) -> DecommissionResult:
    """Idempotent teardown of one Thing's identity.

    Parameters
    ----------
    thing_name:
        Logical IoT Thing name (e.g. ``hw-pi-001``).
    policy_name:
        IoT policy attached to the cert. If ``None``, attached policies are
        discovered via ``ListAttachedPolicies`` and detached as found.
    secret_id:
        Secrets Manager secret name or ARN holding the PEM bundle. If
        ``None`` the secret step is skipped (typical for orphan-cert cleanup).
    iot_client / secrets_client:
        Pre-built boto3 clients (e.g. from a Session in the CLI, or the
        Lambda runtime's default credentials chain). When ``None`` a default
        client is constructed.
    keep_secret:
        Skip ``DeleteSecret`` even when ``secret_id`` is supplied. Useful in
        CLI flows where the operator wants to retain PEMs for forensics.
    force_delete_certificate:
        Pass ``forceDelete=True`` to ``DeleteCertificate``. Default ``False``
        — caller should escalate manually only when a single retry confirms
        nothing else is attached.
    recovery_window_days:
        Days for ``DeleteSecret`` recovery (1-30, default 7).
    logger:
        Optional logger; when ``None`` a module logger is used. The Lambda
        passes the AWS ``LambdaContext.aws_request_id``-bound logger here.
    """
    log = logger or _DEFAULT_LOGGER

    if iot_client is None:
        iot_client = _iot_client_factory()
    if secrets_client is None and not keep_secret and secret_id:
        secrets_client = _secrets_client_factory()

    result = DecommissionResult(thing_name=thing_name)

    principals = _list_thing_principals(iot_client, thing_name)
    log.info(
        "decommission start thing=%s principals=%d policy=%s secret=%s",
        thing_name,
        len(principals),
        policy_name,
        secret_id,
    )

    for principal_arn in principals:
        if not _is_cert_principal(principal_arn):
            log.warning(
                "skipping non-cert principal %s on thing %s",
                principal_arn,
                thing_name,
            )
            continue

        cert_id = _certificate_id_from_arn(principal_arn)

        _swallow_not_found(
            "DetachThingPrincipal",
            iot_client.detach_thing_principal,
            thingName=thing_name,
            principal=principal_arn,
            logger=log,
            not_found=result.not_found,
        )
        result.detached_principals.append(principal_arn)

        policies_to_detach = _resolve_policies_to_detach(
            iot_client,
            principal_arn=principal_arn,
            policy_name=policy_name,
            logger=log,
            not_found=result.not_found,
        )
        for pol_name in policies_to_detach:
            _swallow_not_found(
                "DetachPolicy",
                iot_client.detach_policy,
                policyName=pol_name,
                target=principal_arn,
                logger=log,
                not_found=result.not_found,
            )
            result.detached_policies.append(pol_name)

        _swallow_not_found(
            "UpdateCertificate INACTIVE",
            iot_client.update_certificate,
            certificateId=cert_id,
            newStatus="INACTIVE",
            logger=log,
            not_found=result.not_found,
        )
        result.inactivated_certificates.append(cert_id)

        _swallow_not_found(
            "DeleteCertificate",
            iot_client.delete_certificate,
            certificateId=cert_id,
            forceDelete=force_delete_certificate,
            logger=log,
            not_found=result.not_found,
        )
        result.deleted_certificates.append(cert_id)

    if secret_id and not keep_secret:
        _swallow_not_found(
            "DeleteSecret",
            secrets_client.delete_secret,
            SecretId=secret_id,
            RecoveryWindowInDays=recovery_window_days,
            logger=log,
            not_found=result.not_found,
        )
        result.deleted_secret = secret_id
    elif secret_id and keep_secret:
        result.secret_kept = True

    log.info(
        "decommission done thing=%s detached=%d deleted_certs=%d secret=%s",
        thing_name,
        len(result.detached_principals),
        len(result.deleted_certificates),
        result.deleted_secret or ("kept" if result.secret_kept else "skipped"),
    )
    return result


def _resolve_policies_to_detach(
    iot: Any,
    *,
    principal_arn: str,
    policy_name: str | None,
    logger: logging.Logger,
    not_found: list[str],
) -> list[str]:
    """If ``policy_name`` was supplied, just use it; otherwise enumerate."""
    if policy_name is not None:
        return [policy_name]
    found: list[str] = []
    paginator_kwargs: dict[str, Any] = {"target": principal_arn}
    while True:
        page = _swallow_not_found(
            "ListAttachedPolicies",
            iot.list_attached_policies,
            logger=logger,
            not_found=not_found,
            **paginator_kwargs,
        )
        if page is None:
            break
        for entry in page.get("policies", []):
            name = entry.get("policyName")
            if name:
                found.append(name)
        marker = page.get("nextMarker")
        if not marker:
            break
        paginator_kwargs["marker"] = marker
    return found


def delete_certificate(
    certificate_id: str,
    *,
    iot_client: Any | None = None,
    force_delete: bool = False,
    detach_policies: bool = True,
    detach_principals: bool = True,
    logger: logging.Logger | None = None,
) -> dict[str, list[str]]:
    """Tear down a certificate that may already be orphaned (no Thing).

    Used by ``sbc iot list-orphan-certs --delete`` and by recovery scripts.
    """
    log = logger or _DEFAULT_LOGGER
    if iot_client is None:
        iot_client = _iot_client_factory()

    cert_arn = _describe_cert_arn(iot_client, certificate_id)
    not_found: list[str] = []
    detached_things: list[str] = []
    detached_policies: list[str] = []

    if detach_principals and cert_arn:
        principals_page = _swallow_not_found(
            "ListPrincipalThings",
            iot_client.list_principal_things,
            principal=cert_arn,
            logger=log,
            not_found=not_found,
        )
        if principals_page:
            for thing_name in principals_page.get("things", []):
                _swallow_not_found(
                    "DetachThingPrincipal",
                    iot_client.detach_thing_principal,
                    thingName=thing_name,
                    principal=cert_arn,
                    logger=log,
                    not_found=not_found,
                )
                detached_things.append(thing_name)

    if detach_policies and cert_arn:
        attached = _resolve_policies_to_detach(
            iot_client,
            principal_arn=cert_arn,
            policy_name=None,
            logger=log,
            not_found=not_found,
        )
        for name in attached:
            _swallow_not_found(
                "DetachPolicy",
                iot_client.detach_policy,
                policyName=name,
                target=cert_arn,
                logger=log,
                not_found=not_found,
            )
            detached_policies.append(name)

    _swallow_not_found(
        "UpdateCertificate INACTIVE",
        iot_client.update_certificate,
        certificateId=certificate_id,
        newStatus="INACTIVE",
        logger=log,
        not_found=not_found,
    )
    _swallow_not_found(
        "DeleteCertificate",
        iot_client.delete_certificate,
        certificateId=certificate_id,
        forceDelete=force_delete,
        logger=log,
        not_found=not_found,
    )
    return {
        "detached_things": detached_things,
        "detached_policies": detached_policies,
        "not_found": not_found,
    }


def _describe_cert_arn(iot: Any, certificate_id: str) -> str | None:
    try:
        resp = iot.describe_certificate(certificateId=certificate_id)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code in {"ResourceNotFoundException", "NotFoundException"}:
            return None
        raise
    return resp.get("certificateDescription", {}).get("certificateArn")


@dataclass
class CertificateSummary:
    """Subset of ``DescribeCertificate`` output for orphan listings."""

    certificate_id: str
    certificate_arn: str
    status: str
    creation_date: str | None = None
    attached_things: list[str] = field(default_factory=list)
    attached_policies: list[str] = field(default_factory=list)


def list_orphan_certificates(
    *,
    iot_client: Any | None = None,
    policy_name: str | None = None,
) -> list[CertificateSummary]:
    """Return certificates that are not attached to any Thing.

    When ``policy_name`` is given, the result is further filtered to certs
    that are also attached to that policy (i.e. policy is "leaking" into a
    cert that has no Thing).
    """
    if iot_client is None:
        iot_client = _iot_client_factory()

    orphans: list[CertificateSummary] = []
    next_marker: str | None = None
    while True:
        kwargs: dict[str, Any] = {}
        if next_marker:
            kwargs["marker"] = next_marker
        page = iot_client.list_certificates(**kwargs)
        for cert in page.get("certificates", []):
            cert_id = cert["certificateId"]
            cert_arn = cert["certificateArn"]
            things_page = iot_client.list_principal_things(principal=cert_arn)
            things = list(things_page.get("things", []))
            if things:
                continue
            attached_policies = _resolve_policies_to_detach(
                iot_client,
                principal_arn=cert_arn,
                policy_name=None,
                logger=_DEFAULT_LOGGER,
                not_found=[],
            )
            if policy_name and policy_name not in attached_policies:
                continue
            orphans.append(
                CertificateSummary(
                    certificate_id=cert_id,
                    certificate_arn=cert_arn,
                    status=cert.get("status", "?"),
                    creation_date=str(cert.get("creationDate", "") or "") or None,
                    attached_things=things,
                    attached_policies=attached_policies,
                )
            )
        next_marker = page.get("nextMarker")
        if not next_marker:
            break
    return orphans
