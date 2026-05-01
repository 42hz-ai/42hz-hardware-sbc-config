"""CDK custom-resource handler — mint + lifecycle one IoT device identity.

Bundled with ``sbc_config.modules.iot`` so ``Delete`` calls the same
``decommission_thing`` function the operator CLI uses (``sbc iot
decommission-thing``). One source of truth for the detach/inactivate/delete
sequence — no drift between CFN-driven teardown and operator-driven cleanup.

CloudFormation custom-resource contract:

* **Create**::

    {
      "RequestType": "Create",
      "ResourceProperties": {
        "ThingName": "hw-pi-001",
        "PolicyName": "iot-hello-world",
        "SecretId": "iot/things/hw-pi-001/credentials",
        "CertVersion": "1"
      }
    }

  Returns ``{"PhysicalResourceId": "<certificateId>", "Data": {...}}``.

* **Update**: if ``CertVersion`` changed, treat as Replace — the framework
  will fire a follow-up ``Delete`` on the previous ``PhysicalResourceId``
  using the *old* properties, which our shared lifecycle handles cleanly.

* **Delete**: idempotent — swallow ``ResourceNotFoundException`` at every
  step. No private key is ever logged.
"""

from __future__ import annotations

import json
import logging
import os

from typing import Any

import boto3

from sbc_config.modules.iot.credentials import SecretBundle
from sbc_config.modules.iot.lifecycle import decommission_thing

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

_iot = boto3.client("iot")
_secretsmanager = boto3.client("secretsmanager")


def on_event(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Custom-resource entry point — dispatched by the Provider framework."""
    request_type = event["RequestType"]
    props = event["ResourceProperties"]
    LOGGER.info(
        "custom-resource event type=%s thing=%s policy=%s secret=%s",
        request_type,
        props.get("ThingName"),
        props.get("PolicyName"),
        props.get("SecretId"),
    )

    if request_type == "Create":
        return _create(props)
    if request_type == "Update":
        return _update(event, props)
    if request_type == "Delete":
        return _delete(event, props)
    msg = f"unknown RequestType: {request_type!r}"
    raise ValueError(msg)


def _create(props: dict[str, Any]) -> dict[str, Any]:
    thing_name = props["ThingName"]
    policy_name = props["PolicyName"]
    secret_id = props["SecretId"]

    LOGGER.info("CreateKeysAndCertificate(setAsActive=True) thing=%s", thing_name)
    keys = _iot.create_keys_and_certificate(setAsActive=True)
    cert_id = keys["certificateId"]
    cert_arn = keys["certificateArn"]
    cert_pem = keys["certificatePem"]
    private_key = keys["keyPair"]["PrivateKey"]

    try:
        _iot.attach_policy(policyName=policy_name, target=cert_arn)
        _iot.attach_thing_principal(thingName=thing_name, principal=cert_arn)

        endpoint = _safe_describe_endpoint()
        bundle = SecretBundle(
            thing_name=thing_name,
            certificate_id=cert_id,
            certificate_arn=cert_arn,
            certificate_pem=cert_pem,
            private_key=private_key,
            iot_data_endpoint=endpoint,
        )
        _put_secret(
            secret_id=secret_id, payload=bundle.to_json(), thing_name=thing_name
        )
    except Exception:
        LOGGER.exception("Create failed mid-sequence; rolling back cert %s", cert_id)
        _rollback_cert(cert_id=cert_id, cert_arn=cert_arn, thing_name=thing_name)
        raise

    LOGGER.info(
        "Create complete thing=%s certificateId=%s endpoint=%s",
        thing_name,
        cert_id,
        endpoint or "(unset)",
    )
    return {
        "PhysicalResourceId": cert_id,
        "Data": {
            "ThingName": thing_name,
            "CertificateId": cert_id,
            "CertificateArn": cert_arn,
            "SecretId": secret_id,
            "IotDataEndpoint": endpoint or "",
        },
    }


def _update(event: dict[str, Any], props: dict[str, Any]) -> dict[str, Any]:
    """Replace on cert rotation; otherwise no-op (PhysicalResourceId unchanged)."""
    old_props = event.get("OldResourceProperties", {}) or {}
    if old_props.get("CertVersion") != props.get("CertVersion") or old_props.get(
        "ThingName"
    ) != props.get("ThingName"):
        LOGGER.info("CertVersion or ThingName changed — minting a new cert (Replace)")
        return _create(props)

    return {
        "PhysicalResourceId": event["PhysicalResourceId"],
        "Data": {
            "ThingName": props["ThingName"],
            "CertificateId": event["PhysicalResourceId"],
            "SecretId": props["SecretId"],
        },
    }


def _delete(event: dict[str, Any], props: dict[str, Any]) -> dict[str, Any]:
    """Idempotent teardown — shared with `sbc iot decommission-thing`."""
    thing_name = props.get("ThingName")
    if not thing_name:
        LOGGER.warning("Delete with no ThingName — nothing to do")
        return {"PhysicalResourceId": event["PhysicalResourceId"]}

    result = decommission_thing(
        thing_name,
        policy_name=props.get("PolicyName"),
        secret_id=props.get("SecretId"),
        iot_client=_iot,
        secrets_client=_secretsmanager,
        recovery_window_days=7,
        logger=LOGGER,
    )
    LOGGER.info(
        "Delete complete thing=%s detached=%d deleted_certs=%d secret=%s",
        thing_name,
        len(result.detached_principals),
        len(result.deleted_certificates),
        result.deleted_secret or "kept-or-skipped",
    )
    return {
        "PhysicalResourceId": event["PhysicalResourceId"],
        "Data": {
            "ThingName": thing_name,
            "DetachedPrincipals": json.dumps(result.detached_principals),
            "DeletedCertificates": json.dumps(result.deleted_certificates),
            "DeletedSecret": result.deleted_secret or "",
            "NotFoundOps": json.dumps(result.not_found),
        },
    }


def _safe_describe_endpoint() -> str | None:
    """Best-effort — Create still succeeds if DescribeEndpoint hiccups."""
    try:
        resp = _iot.describe_endpoint(endpointType="iot:Data-ATS")
    except Exception:
        LOGGER.exception("DescribeEndpoint failed; secret will omit iotDataEndpoint")
        return None
    return resp.get("endpointAddress")


def _put_secret(*, secret_id: str, payload: str, thing_name: str) -> None:
    """Create or update the secret. Existing secrets are PutSecretValue'd."""
    tags = [
        {"Key": "ManagedBy", "Value": "cdk:IotHelloStack"},
        {"Key": "ThingName", "Value": thing_name},
    ]
    try:
        _secretsmanager.create_secret(
            Name=secret_id,
            Description=(
                f"AWS IoT cert + private key for {thing_name}. Created by "
                "IotHelloStack custom resource. Never read by the CDK Lambda."
            ),
            SecretString=payload,
            Tags=tags,
        )
        LOGGER.info("CreateSecret %s", secret_id)
        return
    except _secretsmanager.exceptions.ResourceExistsException:
        LOGGER.info("Secret %s exists — calling PutSecretValue", secret_id)
    except _secretsmanager.exceptions.InvalidRequestException as exc:
        # If the secret was previously DeleteSecret'd it lives in the recovery
        # window and CreateSecret refuses; restore + put-value.
        if "scheduled for deletion" not in str(exc):
            raise
        LOGGER.info("Secret %s was scheduled for deletion — restoring", secret_id)
        _secretsmanager.restore_secret(SecretId=secret_id)

    _secretsmanager.put_secret_value(SecretId=secret_id, SecretString=payload)


def _rollback_cert(*, cert_id: str, cert_arn: str, thing_name: str) -> None:
    """Best-effort cleanup if Create blows up after CreateKeysAndCertificate."""
    try:
        _iot.detach_thing_principal(thingName=thing_name, principal=cert_arn)
    except Exception:
        LOGGER.warning("rollback: detach_thing_principal failed", exc_info=True)
    try:
        _iot.update_certificate(certificateId=cert_id, newStatus="INACTIVE")
        _iot.delete_certificate(certificateId=cert_id, forceDelete=False)
    except Exception:
        LOGGER.warning("rollback: cert teardown failed", exc_info=True)


# Quiet ruff for unused module-level boto3 sanity check.
_ = os
