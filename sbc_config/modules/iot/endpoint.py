"""IoT data-plane endpoint resolution (``iot:Data-ATS`` only)."""

from __future__ import annotations

from typing import Any

from sbc_config.modules.iot.client import iot_client as _iot_client_factory

ENDPOINT_TYPE_DATA_ATS = "iot:Data-ATS"
ENDPOINT_TYPE_CREDENTIAL = "iot:CredentialProvider"


def describe_data_ats_endpoint(
    *,
    iot_client: Any | None = None,
) -> str:
    """Return the ATS data-plane endpoint host (no scheme).

    ATS endpoints serve the Amazon Trust Services CA chain; the legacy VeriSign
    endpoint type (``iot:Data``) is deprecated and not surfaced here.
    """
    if iot_client is None:
        iot_client = _iot_client_factory()
    resp = iot_client.describe_endpoint(endpointType=ENDPOINT_TYPE_DATA_ATS)
    address = resp.get("endpointAddress")
    if not address:
        msg = "DescribeEndpoint returned no endpointAddress"
        raise RuntimeError(msg)
    return address


def describe_credential_provider_endpoint(
    *,
    iot_client: Any | None = None,
) -> str:
    """Return the IoT Credential Provider endpoint host (Greengrass forward path)."""
    if iot_client is None:
        iot_client = _iot_client_factory()
    resp = iot_client.describe_endpoint(endpointType=ENDPOINT_TYPE_CREDENTIAL)
    address = resp.get("endpointAddress")
    if not address:
        msg = "DescribeEndpoint (CredentialProvider) returned no endpointAddress"
        raise RuntimeError(msg)
    return address
