"""``sbc iot install-greengrass`` — install Greengrass Nucleus using CDK PEMs."""

from __future__ import annotations

import os

from pathlib import Path

import click

from sbc_config.modules.iot.client import build_session
from sbc_config.modules.iot.defaults import (
    DEFAULT_GREENGRASS_TES_ROLE_ALIAS,
    HELLO_WORLD_THING_NAME,
    default_bundle_dir_for_thing,
    default_greengrass_install_root,
)
from sbc_config.modules.iot.greengrass_install import (
    NUCLEUS_VERSION_DEFAULT,
    deploy_greengrass_cli_component,
    greengrass_root_appears_installed,
    install_nucleus_from_bundle,
    stage_device_crypto,
)

ENV_TES_ALIAS = "SBC_IOT_GG_TES_ROLE_ALIAS"


@click.command("install-greengrass")
@click.option(
    "--thing-name",
    default=HELLO_WORLD_THING_NAME,
    show_default=True,
    metavar="NAME",
    help="IoT Thing name (must match `sbc iot fetch-credentials --thing-name`).",
)
@click.option(
    "--tes-role-alias",
    default=None,
    metavar="ALIAS",
    help=(
        "Greengrass token exchange IoT role alias. "
        f"Default: ${ENV_TES_ALIAS} env var, else {DEFAULT_GREENGRASS_TES_ROLE_ALIAS!r} "
        "(matches IotHelloStack when TES is CDK-managed)."
    ),
)
@click.option(
    "--bundle-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=None,
    metavar="DIR",
    help=(
        "Directory with thing-cert.pem, thing-private.key, cas/ (fetch-credentials "
        "output). Default: same as fetch-credentials ($SBC_IOT_FETCH_OUT_DIR or "
        "aws-iot-bundles/<--thing-name>)."
    ),
)
@click.option(
    "--greengrass-root",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=None,
    help=(
        "Greengrass root path on this machine (matches Nucleus layout). "
        "When omitted: $SBCC_GREENGRASS_ROOT if set (devcontainer supplies this "
        "for Docker IPC workloads), otherwise /greengrass/v2."
    ),
)
@click.option(
    "--nucleus-version",
    default=NUCLEUS_VERSION_DEFAULT,
    show_default=True,
    metavar="VER",
    help="Nucleus component version written into the partial config.",
)
@click.option(
    "--setup-system-service/--no-setup-system-service",
    default=False,
    help="Register systemd service (usually false in devcontainers).",
)
@click.option(
    "--foreground",
    is_flag=True,
    help=(
        "Without systemd: attach to the Nucleus JVM in this terminal (blocks). "
        "Default: spawn in the background and return after launch; logs in "
        "<--greengrass-root>/sbcc-nucleus-install.log."
    ),
)
@click.option(
    "--reinstall",
    is_flag=True,
    help=(
        "Re-run the Nucleus installer even when --greengrass-root already looks "
        "bootstrapped (packages/ or work/). Default: skip installer and only refresh "
        "PEMs from the bundle."
    ),
)
@click.option(
    "--zip-path",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    default=None,
    help="Reuse an existing greengrass-nucleus-*.zip instead of downloading.",
)
@click.option(
    "--deploy-cli",
    is_flag=True,
    help=(
        "After install, create a Greengrass cloud deployment for `aws.greengrass.Cli` "
        "(needs greengrassv2:CreateDeployment on the operator principal)."
    ),
)
@click.pass_context
def install_greengrass_command(
    ctx: click.Context,
    thing_name: str,
    tes_role_alias: str | None,
    bundle_dir: Path | None,
    greengrass_root: Path | None,
    nucleus_version: str,
    setup_system_service: bool,
    foreground: bool,
    reinstall: bool,
    zip_path: Path | None,
    deploy_cli: bool,
) -> None:
    """Install Greengrass Nucleus using PEMs from fetch-credentials (manual install path).

    Prerequisite: create the token exchange IAM role + IoT role alias and
    attach ``iot:AssumeRoleWithCertificate`` to the device's certificate policy
    (see ``docs/SBCC-INFRA-0003-greengrass-local-dev-loop.md``).

    ``--deploy-dev-tools`` only works with ``--provision true`` on the AWS installer,
    so this command uses the partial-config flow. Install the Greengrass CLI via
    ``--deploy-cli`` (cloud deployment) or the console.
    """
    if greengrass_root is None:
        greengrass_root = default_greengrass_install_root()

    bundle_eff = (
        bundle_dir
        if bundle_dir is not None
        else default_bundle_dir_for_thing(thing_name)
    )
    console = ctx.obj["console"]
    alias = (
        tes_role_alias
        or os.environ.get(ENV_TES_ALIAS)
        or DEFAULT_GREENGRASS_TES_ROLE_ALIAS
    )

    session = build_session(
        profile=ctx.obj.get("aws_profile"),
        region=ctx.obj.get("aws_region"),
    )
    iot = session.client("iot")

    console.print(
        f"[cyan]Greengrass[/cyan] target [bold]{greengrass_root}[/bold] "
        f"for thing [bold]{thing_name}[/bold]"
    )
    skip_install = greengrass_root_appears_installed(greengrass_root) and not reinstall
    try:
        if skip_install:
            console.print(
                "[yellow]Skipping[/yellow] Nucleus installer — this root already "
                f"looks bootstrapped ([bold]{greengrass_root}[/bold]). "
                "Pass [bold]--reinstall[/bold] to run the installer again. "
                "Refreshing device PEMs from bundle."
            )
            stage_device_crypto(bundle_dir=bundle_eff, greengrass_root=greengrass_root)
        else:
            install_nucleus_from_bundle(
                bundle_dir=bundle_eff,
                thing_name=thing_name,
                region=ctx.obj["aws_region"],
                tes_role_alias=alias,
                greengrass_root=greengrass_root,
                iot_client=iot,
                nucleus_version=nucleus_version,
                setup_system_service=setup_system_service,
                foreground=foreground,
                keep_download=zip_path,
            )
    except Exception as exc:
        console.print(f"[red]Install failed:[/red] {exc}")
        raise click.Abort() from exc

    if skip_install:
        console.print(
            "[green]Skipped installer — refreshed PEMs from bundle[/green] "
            "(existing Nucleus layout left as-is)."
        )
    else:
        console.print("[green]Nucleus installer finished successfully.[/green]")
    if skip_install:
        console.print(
            "[dim]If you changed Thing, TES alias, or region, use --reinstall or a "
            "fresh --greengrass-root.[/dim]"
        )
    elif not setup_system_service and not foreground:
        console.print(
            f"[dim]Nucleus JVM still running; installer log "
            f"{greengrass_root / 'sbcc-nucleus-install.log'}[/dim]"
        )
    console.print(
        "Verify: [bold]ls[/bold] "
        + str(greengrass_root)
        + " - expect config/, packages/, logs/"
    )

    if deploy_cli:
        console.print(
            "[cyan]Creating[/cyan] cloud deployment for [bold]aws.greengrass.Cli[/bold]…"
        )
        try:
            dep_id = deploy_greengrass_cli_component(
                session=session,
                thing_name=thing_name,
                region=ctx.obj["aws_region"],
                component_version=nucleus_version,
            )
        except Exception as exc:
            console.print(f"[red]create-deployment failed:[/red] {exc}")
            raise click.Abort() from exc
        console.print(f"[green]deploymentId[/green] [bold]{dep_id}[/bold]")
        console.print(
            "[dim]aws.greengrass.Cli installs on the device after Nucleus pulls the "
            "deployment — greengrass-cli appears under <greengrass-root>/bin when that "
            "finishes (see --greengrass-root / $SBCC_GREENGRASS_ROOT). "
            "If you skipped the installer, "
            "ensure a Nucleus JVM is still running (e.g. pgrep -af Greengrass.jar). "
            "Poll status:[/dim]"
        )
        console.print(
            f"[dim]  aws greengrassv2 get-deployment --deployment-id {dep_id}[/dim]"
        )
