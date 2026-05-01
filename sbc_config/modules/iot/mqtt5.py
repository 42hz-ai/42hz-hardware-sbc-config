"""One-shot MQTT 5 publish via ``awsiotsdk`` (Python).

Used by ``sbc iot mqtt-test`` and as a copy/paste-able example in
``SBCC-INFRA-0001``. ``awsiotsdk`` is imported lazily so that the rest of the
``sbc iot`` group (which only needs boto3) works on machines without the
``awscrt`` native build.
"""

from __future__ import annotations

import json
import threading

from dataclasses import dataclass
from pathlib import Path

DEFAULT_QOS_AT_LEAST_ONCE = 1
DEFAULT_CONNECT_TIMEOUT_S = 30
DEFAULT_PUBLISH_TIMEOUT_S = 30


@dataclass
class PublishResult:
    """Captured outcome of a one-shot publish."""

    topic: str
    client_id: str
    endpoint: str
    payload_bytes: int


def publish_once(
    *,
    endpoint: str,
    cert_path: Path,
    private_key_path: Path,
    ca_path: Path,
    client_id: str,
    topic: str,
    payload: bytes | str | dict[str, object],
    qos: int = DEFAULT_QOS_AT_LEAST_ONCE,
    connect_timeout_s: float = DEFAULT_CONNECT_TIMEOUT_S,
    publish_timeout_s: float = DEFAULT_PUBLISH_TIMEOUT_S,
) -> PublishResult:
    """Build a MQTT 5 mtls client, connect, publish once, and stop.

    Raises ``RuntimeError`` on connection or publish timeout.
    """
    # awsiotsdk lives in the optional `iot` extra so laptops/dev environments
    # that don't publish (CLI-only AWS-side usage) don't pay the awscrt native
    # build cost. Keep the imports lazy and silence the convention warning.
    try:
        from awscrt import mqtt5  # noqa: PLC0415
        from awsiot import mqtt5_client_builder  # noqa: PLC0415
    except ImportError as exc:
        msg = (
            "awsiotsdk is not installed. Install with `uv sync --extra iot` "
            "(or `pip install awsiotsdk`) on devices that need MQTT 5 publish."
        )
        raise RuntimeError(msg) from exc

    payload_bytes = _coerce_payload(payload)

    connected = threading.Event()
    stopped = threading.Event()

    def _on_lifecycle_connection_success(_event: object) -> None:
        connected.set()

    def _on_lifecycle_stopped(_event: object) -> None:
        stopped.set()

    client = mqtt5_client_builder.mtls_from_path(
        endpoint=endpoint,
        cert_filepath=str(cert_path),
        pri_key_filepath=str(private_key_path),
        ca_filepath=str(ca_path),
        client_id=client_id,
        on_lifecycle_connection_success=_on_lifecycle_connection_success,
        on_lifecycle_stopped=_on_lifecycle_stopped,
    )

    client.start()
    if not connected.wait(connect_timeout_s):
        client.stop()
        msg = f"MQTT 5 connection to {endpoint!r} timed out after {connect_timeout_s}s"
        raise RuntimeError(msg)

    publish_future = client.publish(
        mqtt5.PublishPacket(
            topic=topic,
            payload=payload_bytes,
            qos=mqtt5.QoS(qos),
        )
    )
    publish_future.result(timeout=publish_timeout_s)

    client.stop()
    stopped.wait(connect_timeout_s)

    return PublishResult(
        topic=topic,
        client_id=client_id,
        endpoint=endpoint,
        payload_bytes=len(payload_bytes),
    )


def _coerce_payload(payload: bytes | str | dict[str, object]) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, sort_keys=True).encode("utf-8")
