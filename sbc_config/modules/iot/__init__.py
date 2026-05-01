"""IoT modules — boto3 wrappers, certificate lifecycle, MQTT 5 helpers.

The lifecycle helpers in this package are deliberately stdlib + boto3 only so
the CDK custom-resource Lambda can bundle this subtree as its handler asset
without pulling in CLI-only dependencies (click, rich, pydantic).
"""

from sbc_config.modules.iot.client import build_session, iot_client, secrets_client
from sbc_config.modules.iot.credentials import (
    ENDPOINT_FILENAME,
    SecretBundle,
    fetch_secret_bundle,
    write_bundle_to_disk,
)
from sbc_config.modules.iot.endpoint import describe_data_ats_endpoint
from sbc_config.modules.iot.lifecycle import (
    DecommissionResult,
    decommission_thing,
    delete_certificate,
    list_orphan_certificates,
)
from sbc_config.modules.iot.pi_sync import sync_bundle, sync_repo

__all__ = [
    "ENDPOINT_FILENAME",
    "DecommissionResult",
    "SecretBundle",
    "build_session",
    "decommission_thing",
    "delete_certificate",
    "describe_data_ats_endpoint",
    "fetch_secret_bundle",
    "iot_client",
    "list_orphan_certificates",
    "secrets_client",
    "sync_bundle",
    "sync_repo",
    "write_bundle_to_disk",
]
