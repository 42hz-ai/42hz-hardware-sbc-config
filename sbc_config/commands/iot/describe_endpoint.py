"""``sbc iot describe-endpoint`` — print the iot:Data-ATS endpoint host."""

from __future__ import annotations

import click

from sbc_config.modules.iot.client import build_session
from sbc_config.modules.iot.endpoint import (
    describe_credential_provider_endpoint,
    describe_data_ats_endpoint,
)


@click.command("describe-endpoint")
@click.option(
    "--credential-provider",
    is_flag=True,
    help="Print the IoT Credential Provider endpoint instead (Greengrass forward path).",
)
@click.pass_context
def describe_endpoint_command(
    ctx: click.Context,
    credential_provider: bool,
) -> None:
    """Resolve the AWS IoT Core endpoint host."""
    console = ctx.obj["console"]
    session = build_session(
        profile=ctx.obj.get("aws_profile"),
        region=ctx.obj.get("aws_region"),
    )
    iot = session.client("iot")
    try:
        if credential_provider:
            host = describe_credential_provider_endpoint(iot_client=iot)
            label = "Credential Provider"
        else:
            host = describe_data_ats_endpoint(iot_client=iot)
            label = "iot:Data-ATS"
    except Exception as exc:
        console.print(f"[red]DescribeEndpoint failed:[/red] {exc}")
        raise click.Abort() from exc
    console.print(f"[green]{label}[/green] [bold]{host}[/bold]")
