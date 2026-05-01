"""IoT command group — operator entry point for AWS IoT Core hello world.

Commands here all share the same shape:

* ``--profile`` / ``--region`` flow into a single boto3 ``Session`` (defaults
  honour ``AWS_PROFILE`` and ``us-west-2``).
* Heavy lifting lives in ``sbc_config.modules.iot``; the CDK custom-resource
  Lambda imports the same modules (single source of truth for cert lifecycle).
"""

from __future__ import annotations

import click

from sbc_config.commands.iot import (
    decommission_thing,
    describe_endpoint,
    fetch_credentials,
    list_orphan_certs,
    mqtt_test,
    sync_to_pi,
)
from sbc_config.modules.iot.client import DEFAULT_REGION


@click.group("iot")
@click.option(
    "--profile",
    default=None,
    envvar="AWS_PROFILE",
    metavar="NAME",
    help="AWS CLI profile (defaults to $AWS_PROFILE; canonical: spikes-sitewise).",
)
@click.option(
    "--region",
    default=DEFAULT_REGION,
    show_default=True,
    metavar="REGION",
    help="AWS region for IoT + Secrets Manager calls.",
)
@click.pass_context
def iot_group(ctx: click.Context, profile: str | None, region: str) -> None:
    """AWS IoT Core operator commands (hello world + decommission helpers)."""
    ctx.ensure_object(dict)
    ctx.obj["aws_profile"] = profile
    ctx.obj["aws_region"] = region


iot_group.add_command(describe_endpoint.describe_endpoint_command)
iot_group.add_command(fetch_credentials.fetch_credentials_command)
iot_group.add_command(mqtt_test.mqtt_test_command)
iot_group.add_command(sync_to_pi.sync_to_pi_command)
iot_group.add_command(decommission_thing.decommission_thing_command)
iot_group.add_command(list_orphan_certs.list_orphan_certs_command)


__all__ = ["iot_group"]
