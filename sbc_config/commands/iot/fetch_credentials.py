"""``sbc iot fetch-credentials`` — pull PEM bundle + CA1-CA4 to disk."""

from __future__ import annotations

from pathlib import Path

import click

from sbc_config.modules.iot.client import build_session
from sbc_config.modules.iot.credentials import (
    AMAZON_ROOT_CA_URLS,
    ENDPOINT_FILENAME,
    fetch_secret_bundle,
    write_bundle_to_disk,
)
from sbc_config.modules.iot.defaults import (
    HELLO_WORLD_THING_NAME,
    default_fetch_out_dir,
)
from sbc_config.modules.iot.endpoint import describe_data_ats_endpoint


def _default_secret_name(thing_name: str) -> str:
    return f"iot/things/{thing_name}/credentials"


@click.command("fetch-credentials")
@click.option(
    "--thing-name",
    default=HELLO_WORLD_THING_NAME,
    show_default=True,
    metavar="NAME",
    help="IoT Thing name (the secret defaults to iot/things/<NAME>/credentials).",
)
@click.option(
    "--secret-id",
    default=None,
    metavar="ID_OR_ARN",
    help="Override the Secrets Manager id (default derived from --thing-name).",
)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=default_fetch_out_dir,
    show_default="$SBC_IOT_FETCH_OUT_DIR or /etc/aws-iot",
    help=(
        "Target directory for thing-cert.pem, thing-private.key, cas/. "
        "Override via $SBC_IOT_FETCH_OUT_DIR (e.g. 'aws-iot-bundle' for laptop use)."
    ),
)
@click.option(
    "--skip-cas",
    is_flag=True,
    help=(
        "Don't download Amazon Root CA1-4 (use when CAs are already present "
        "or air-gapped pre-staging is in use)."
    ),
)
@click.option(
    "--no-overwrite",
    is_flag=True,
    help="Refuse to overwrite an existing cert/key file.",
)
@click.option(
    "--print-endpoint",
    is_flag=True,
    help="Also resolve and print the iot:Data-ATS endpoint.",
)
@click.pass_context
def fetch_credentials_command(
    ctx: click.Context,
    thing_name: str,
    secret_id: str | None,
    out_dir: Path,
    skip_cas: bool,
    no_overwrite: bool,
    print_endpoint: bool,
) -> None:
    """Download cert + private key from Secrets Manager and lay them out on disk."""
    console = ctx.obj["console"]
    session = build_session(
        profile=ctx.obj.get("aws_profile"),
        region=ctx.obj.get("aws_region"),
    )
    secrets = session.client("secretsmanager")
    iot = session.client("iot")
    secret_id = secret_id or _default_secret_name(thing_name)
    console.print(f"[cyan]Fetching[/cyan] secret [bold]{secret_id}[/bold]")
    try:
        bundle = fetch_secret_bundle(secret_id, secrets_client=secrets)
    except Exception as exc:
        console.print(f"[red]GetSecretValue failed:[/red] {exc}")
        raise click.Abort() from exc

    if bundle.thing_name != thing_name:
        console.print(
            "[yellow]Warning:[/yellow] secret thingName "
            f"{bundle.thing_name!r} != --thing-name {thing_name!r}"
        )

    written = write_bundle_to_disk(
        bundle,
        out_dir,
        download_cas=not skip_cas,
        overwrite=not no_overwrite,
    )
    console.print(f"[green]Wrote[/green] cert      → {written['certificate']}")
    console.print(
        f"[green]Wrote[/green] key       → {written['private_key']} (mode 0600)"
    )
    if "endpoint" in written:
        console.print(
            f"[green]Wrote[/green] endpoint  → {written['endpoint']} "
            f"({ENDPOINT_FILENAME}; read by Pi entrypoint)"
        )
    if "cas_dir" in written:
        ca_count = len(AMAZON_ROOT_CA_URLS)
        console.print(
            f"[green]Wrote[/green] CA bundle → {written['cas_dir']} "
            f"(Amazon Root CA1-CA{ca_count})"
        )

    if print_endpoint:
        try:
            host = describe_data_ats_endpoint(iot_client=iot)
        except Exception as exc:
            console.print(f"[yellow]DescribeEndpoint failed:[/yellow] {exc}")
        else:
            console.print(f"[green]iot:Data-ATS[/green] [bold]{host}[/bold]")
