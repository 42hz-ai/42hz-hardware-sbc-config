"""Tests for ``sbc_config.modules.iot.lifecycle``.

This module is the single source of truth for cert teardown — both the
``sbc iot decommission-thing`` CLI and the CDK custom-resource Lambda's
``Delete`` handler call into it. The tests verify:

* Sequencing (DetachThingPrincipal -> DetachPolicy -> UpdateCertificate ->
  DeleteCertificate -> DeleteSecret).
* Idempotent ``ResourceNotFoundException`` swallowing.
* Per-Thing scoped policy auto-detection when ``policy_name`` is not given.
* Orphan certificate listing.

Note: ``# noqa: S106`` annotations on ``secret_id=`` calls suppress
ruff's ``hardcoded-password-func-arg`` heuristic — ``secret_id`` is the
AWS Secrets Manager identifier, not a credential.
"""

from __future__ import annotations

import unittest

from typing import Any
from unittest.mock import MagicMock

from sbc_config.modules.iot.credentials import SecretBundle
from sbc_config.modules.iot.lifecycle import (
    decommission_thing,
    delete_certificate,
    list_orphan_certificates,
)

_THING_SECRET_ID = "iot/things/hw-pi-001/credentials"  # noqa: S105 - test fixture
_GHOST_SECRET_ID = "iot/things/ghost/credentials"  # noqa: S105 - test fixture
_PLACEHOLDER_SECRET = "iot/test/placeholder"  # noqa: S105 - test fixture


def _client_error(code: str) -> Exception:
    """Mimic boto3 ``ClientError`` shape for ``_swallow_not_found``."""
    err = Exception(code)
    err.response = {"Error": {"Code": code}}  # type: ignore[attr-defined]
    return err


def _make_iot_mock(
    *,
    principals: list[str],
    attached_policies: list[str] | None = None,
) -> MagicMock:
    """Build an iot client mock that walks the happy path."""
    iot = MagicMock(name="iot")
    iot.list_thing_principals.return_value = {"principals": principals}
    iot.list_attached_policies.return_value = {
        "policies": [{"policyName": name} for name in (attached_policies or [])]
    }
    return iot


def _cert_arn(cert_id: str = "abc123") -> str:
    return f"arn:aws:iot:us-west-2:111122223333:cert/{cert_id}"


class DecommissionHappyPath(unittest.TestCase):
    """Full Create -> Delete sequence on a Thing with one attached cert."""

    def test_full_detach_and_delete(self) -> None:
        cert_arn = _cert_arn("cert-1")
        iot = _make_iot_mock(principals=[cert_arn])
        sm = MagicMock(name="secretsmanager")
        result = decommission_thing(
            "hw-pi-001",
            policy_name="iot-hello-world",
            secret_id=_THING_SECRET_ID,
            iot_client=iot,
            secrets_client=sm,
        )

        iot.detach_thing_principal.assert_called_once_with(
            thingName="hw-pi-001",
            principal=cert_arn,
        )
        iot.detach_policy.assert_called_once_with(
            policyName="iot-hello-world",
            target=cert_arn,
        )
        iot.update_certificate.assert_called_once_with(
            certificateId="cert-1",
            newStatus="INACTIVE",
        )
        iot.delete_certificate.assert_called_once_with(
            certificateId="cert-1",
            forceDelete=False,
        )
        sm.delete_secret.assert_called_once_with(
            SecretId=_THING_SECRET_ID,
            RecoveryWindowInDays=7,
        )

        self.assertEqual(result.detached_principals, [cert_arn])
        self.assertEqual(result.detached_policies, ["iot-hello-world"])
        self.assertEqual(result.deleted_certificates, ["cert-1"])
        self.assertEqual(result.deleted_secret, _THING_SECRET_ID)
        self.assertEqual(result.not_found, [])

    def test_force_delete_forwarded_to_delete_certificate(self) -> None:
        iot = _make_iot_mock(principals=[_cert_arn()])
        sm = MagicMock(name="secretsmanager")
        decommission_thing(
            "hw-pi-001",
            policy_name="p",
            secret_id=_PLACEHOLDER_SECRET,
            iot_client=iot,
            secrets_client=sm,
            force_delete_certificate=True,
        )
        iot.delete_certificate.assert_called_once_with(
            certificateId="abc123",
            forceDelete=True,
        )

    def test_keep_secret_skips_delete_secret(self) -> None:
        iot = _make_iot_mock(principals=[_cert_arn()])
        sm = MagicMock(name="secretsmanager")
        result = decommission_thing(
            "hw-pi-001",
            policy_name="p",
            secret_id=_PLACEHOLDER_SECRET,
            iot_client=iot,
            secrets_client=sm,
            keep_secret=True,
        )
        sm.delete_secret.assert_not_called()
        self.assertTrue(result.secret_kept)
        self.assertIsNone(result.deleted_secret)


class DecommissionIdempotency(unittest.TestCase):
    """Operations must swallow ``ResourceNotFoundException`` and continue."""

    def test_thing_not_found_short_circuits_to_secret(self) -> None:
        iot = MagicMock(name="iot")
        iot.list_thing_principals.side_effect = _client_error(
            "ResourceNotFoundException"
        )
        sm = MagicMock(name="secretsmanager")
        result = decommission_thing(
            "ghost",
            policy_name="p",
            secret_id=_GHOST_SECRET_ID,
            iot_client=iot,
            secrets_client=sm,
        )
        iot.detach_thing_principal.assert_not_called()
        sm.delete_secret.assert_called_once()
        self.assertEqual(result.detached_principals, [])
        self.assertEqual(result.deleted_certificates, [])
        self.assertEqual(result.deleted_secret, _GHOST_SECRET_ID)

    def test_detach_thing_principal_not_found_does_not_abort(self) -> None:
        iot = _make_iot_mock(principals=[_cert_arn()])
        iot.detach_thing_principal.side_effect = _client_error(
            "ResourceNotFoundException"
        )
        sm = MagicMock(name="secretsmanager")
        result = decommission_thing(
            "hw-pi-001",
            policy_name="p",
            secret_id=_PLACEHOLDER_SECRET,
            iot_client=iot,
            secrets_client=sm,
        )
        iot.detach_policy.assert_called_once()
        iot.update_certificate.assert_called_once()
        iot.delete_certificate.assert_called_once()
        self.assertIn("DetachThingPrincipal", result.not_found)

    def test_delete_certificate_not_found_does_not_abort_secret(self) -> None:
        iot = _make_iot_mock(principals=[_cert_arn()])
        iot.delete_certificate.side_effect = _client_error("NotFoundException")
        sm = MagicMock(name="secretsmanager")
        decommission_thing(
            "hw-pi-001",
            policy_name="p",
            secret_id=_PLACEHOLDER_SECRET,
            iot_client=iot,
            secrets_client=sm,
        )
        sm.delete_secret.assert_called_once()


class DecommissionPolicyAutoDetect(unittest.TestCase):
    """When ``policy_name`` is ``None``, list_attached_policies drives detach."""

    def test_uses_listed_policies(self) -> None:
        iot = _make_iot_mock(
            principals=[_cert_arn("c1")],
            attached_policies=["iot-hello-world", "extra-policy"],
        )
        sm = MagicMock(name="secretsmanager")
        result = decommission_thing(
            "hw-pi-001",
            policy_name=None,
            secret_id=_PLACEHOLDER_SECRET,
            iot_client=iot,
            secrets_client=sm,
        )
        names = [call.kwargs["policyName"] for call in iot.detach_policy.call_args_list]
        self.assertEqual(names, ["iot-hello-world", "extra-policy"])
        self.assertEqual(result.detached_policies, ["iot-hello-world", "extra-policy"])


class DeleteCertificateOrphan(unittest.TestCase):
    """``delete_certificate`` runs detach steps even without a Thing context."""

    def test_detach_then_inactivate_then_delete(self) -> None:
        cert_arn = _cert_arn("orphan-1")
        iot = MagicMock(name="iot")
        iot.describe_certificate.return_value = {
            "certificateDescription": {"certificateArn": cert_arn},
        }
        iot.list_principal_things.return_value = {"things": ["hw-pi-old"]}
        iot.list_attached_policies.return_value = {
            "policies": [{"policyName": "iot-hello-world"}]
        }
        delete_certificate("orphan-1", iot_client=iot)
        iot.detach_thing_principal.assert_called_once_with(
            thingName="hw-pi-old",
            principal=cert_arn,
        )
        iot.detach_policy.assert_called_once_with(
            policyName="iot-hello-world",
            target=cert_arn,
        )
        iot.update_certificate.assert_called_once_with(
            certificateId="orphan-1",
            newStatus="INACTIVE",
        )
        iot.delete_certificate.assert_called_once_with(
            certificateId="orphan-1",
            forceDelete=False,
        )


class ListOrphanCerts(unittest.TestCase):
    """Verify orphan listing skips certs that still have a Thing."""

    def test_skips_attached_keeps_orphan(self) -> None:
        attached_arn = _cert_arn("attached")
        orphan_arn = _cert_arn("orphan")
        iot = MagicMock(name="iot")
        iot.list_certificates.return_value = {
            "certificates": [
                {
                    "certificateId": "attached",
                    "certificateArn": attached_arn,
                    "status": "ACTIVE",
                },
                {
                    "certificateId": "orphan",
                    "certificateArn": orphan_arn,
                    "status": "ACTIVE",
                },
            ],
        }

        def _principals(*, principal: str) -> dict[str, Any]:
            return {"things": ["hw-pi-001"] if principal == attached_arn else []}

        iot.list_principal_things.side_effect = _principals
        iot.list_attached_policies.return_value = {
            "policies": [{"policyName": "iot-hello-world"}]
        }

        orphans = list_orphan_certificates(iot_client=iot)
        self.assertEqual([cert.certificate_id for cert in orphans], ["orphan"])
        self.assertEqual(orphans[0].attached_policies, ["iot-hello-world"])


class SecretBundleRoundTrip(unittest.TestCase):
    """JSON shape contract between Lambda's ``Create`` and CLI's ``fetch``."""

    def test_round_trip_preserves_fields(self) -> None:
        bundle = SecretBundle(
            thing_name="hw-pi-001",
            certificate_id="cert-1",
            certificate_arn=_cert_arn("cert-1"),
            certificate_pem="-----BEGIN CERTIFICATE-----\n...",
            private_key="-----BEGIN RSA PRIVATE KEY-----\n...",
            iot_data_endpoint="abc.iot.us-west-2.amazonaws.com",
        )
        payload = bundle.to_json()
        rehydrated = SecretBundle.from_json(payload)
        self.assertEqual(rehydrated, bundle)


if __name__ == "__main__":
    unittest.main()
