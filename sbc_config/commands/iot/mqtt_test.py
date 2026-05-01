"""``sbc iot mqtt-test`` — one-shot MQTT 5 mtls publish from this host."""

from __future__ import annotations

from pathlib import Path

import click

from sbc_config.modules.iot.client import build_session
from sbc_config.modules.iot.credentials import (
    CAS_SUBDIR,
    CERT_FILENAME,
    DEFAULT_OUT_DIR,
    KEY_FILENAME,
)
from sbc_config.modules.iot.endpoint import describe_data_ats_endpoint
from sbc_config.modules.iot.mqtt5 import publish_once


@click.command("mqtt-test")
@click.option(
    "--thing-name",
    required=True,
    metavar="NAME",
    help="IoT Thing name (used as MQTT clientId — must match the policy variable).",
)
@click.option(
    "--topic",
    default=None,
    metavar="TOPIC",
    help="MQTT topic (defaults to hello/<thing-name>/heartbeat).",
)
@click.option(
    "--payload",
    default='{"ok":true}',
    metavar="JSON_OR_TEXT",
    show_default=True,
    help="Payload string sent as the publish body.",
)
@click.option(
    "--cert",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    default=None,
    help=f"Path to the device certificate PEM (default: <out-dir>/{CERT_FILENAME}).",
)
@click.option(
    "--private-key",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    default=None,
    help=f"Path to the private key PEM (default: <out-dir>/{KEY_FILENAME}).",
)
@click.option(
    "--ca",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    default=None,
    help=f"Path to the root CA PEM (default: <out-dir>/{CAS_SUBDIR}/AmazonRootCA1.pem).",
)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True, exists=True),
    default=DEFAULT_OUT_DIR,
    show_default=True,
    help="Directory layout used to default --cert/--private-key/--ca.",
)
@click.option(
    "--endpoint",
    default=None,
    metavar="HOST",
    help="iot:Data-ATS endpoint host. Default: resolve via DescribeEndpoint.",
)
@click.option(
    "--qos",
    type=click.IntRange(0, 1),
    default=1,
    show_default=True,
    help="MQTT 5 publish QoS (0 = AT_MOST_ONCE, 1 = AT_LEAST_ONCE).",
)
@click.pass_context
def mqtt_test_command(
    ctx: click.Context,
    thing_name: str,
    topic: str | None,
    payload: str,
    cert: Path | None,
    private_key: Path | None,
    ca: Path | None,
    out_dir: Path,
    endpoint: str | None,
    qos: int,
) -> None:
    """Publish one MQTT 5 message using the on-disk PEM bundle."""
    console = ctx.obj["console"]
    cert = cert or out_dir / CERT_FILENAME
    private_key = private_key or out_dir / KEY_FILENAME
    ca = ca or out_dir / CAS_SUBDIR / "AmazonRootCA1.pem"
    topic = topic or f"hello/{thing_name}/heartbeat"

    if endpoint is None:
        session = build_session(
            profile=ctx.obj.get("aws_profile"),
            region=ctx.obj.get("aws_region"),
        )
        try:
            endpoint = describe_data_ats_endpoint(iot_client=session.client("iot"))
        except Exception as exc:
            console.print(f"[red]DescribeEndpoint failed:[/red] {exc}")
            raise click.Abort() from exc

    console.print(
        f"[cyan]Publishing[/cyan] thing=[bold]{thing_name}[/bold] "
        f"topic=[bold]{topic}[/bold] qos={qos}"
    )
    console.print(f"[cyan]Endpoint[/cyan] [bold]{endpoint}[/bold]")

    try:
        result = publish_once(
            endpoint=endpoint,
            cert_path=cert,
            private_key_path=private_key,
            ca_path=ca,
            client_id=thing_name,
            topic=topic,
            payload=payload,
            qos=qos,
        )
    except RuntimeError as exc:
        console.print(f"[red]MQTT 5 publish failed:[/red] {exc}")
        raise click.Abort() from exc

    console.print(
        f"[green]Published[/green] {result.payload_bytes} bytes "
        f"to [bold]{result.topic}[/bold] as [bold]{result.client_id}[/bold]"
    )
