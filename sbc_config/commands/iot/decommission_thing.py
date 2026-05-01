"""``sbc iot decommission-thing`` — operator wrapper around lifecycle.decommission_thing."""

from __future__ import annotations

import click

from rich.table import Table

from sbc_config.modules.iot.client import build_session
from sbc_config.modules.iot.defaults import HELLO_WORLD_THING_NAME
from sbc_config.modules.iot.lifecycle import decommission_thing


def _default_secret_name(thing_name: str) -> str:
    return f"iot/things/{thing_name}/credentials"


@click.command("decommission-thing")
@click.option(
    "--thing-name",
    default=HELLO_WORLD_THING_NAME,
    show_default=True,
    metavar="NAME",
    help=(
        "IoT Thing to detach + tear down. "
        f"[bold red]WARNING:[/bold red] default '{HELLO_WORLD_THING_NAME}' targets "
        "the hello-world Thing — always verify before omitting this flag."
    ),
)
@click.option(
    "--policy-name",
    default=None,
    metavar="NAME",
    help="IoT policy attached to the cert. Default: enumerate via ListAttachedPolicies.",
)
@click.option(
    "--secret-id",
    default=None,
    metavar="ID_OR_ARN",
    help="Secrets Manager id (default derived from --thing-name).",
)
@click.option(
    "--keep-secret",
    is_flag=True,
    help="Skip DeleteSecret (keeps PEM bundle for forensic copy).",
)
@click.option(
    "--force-delete",
    is_flag=True,
    help="Pass forceDelete=True to DeleteCertificate (rarely needed; not blind-force).",
)
@click.option(
    "--recovery-window-days",
    type=click.IntRange(7, 30),
    default=7,
    show_default=True,
    help="DeleteSecret RecoveryWindowInDays (7-30).",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt.",
)
@click.pass_context
def decommission_thing_command(
    ctx: click.Context,
    thing_name: str,
    policy_name: str | None,
    secret_id: str | None,
    keep_secret: bool,
    force_delete: bool,
    recovery_window_days: int,
    yes: bool,
) -> None:
    """Detach principal/policy, deactivate cert, delete cert + secret (idempotent)."""
    console = ctx.obj["console"]
    secret_id = secret_id or _default_secret_name(thing_name)

    console.print(f"[bold red]Decommission[/bold red] thing=[bold]{thing_name}[/bold]")
    console.print(f"  policy:  {policy_name or '(auto-detect)'}")
    console.print(f"  secret:  {secret_id} ({'KEEP' if keep_secret else 'DELETE'})")
    console.print(
        f"  cert:    {'forceDelete=True' if force_delete else 'forceDelete=False'}"
    )
    if not yes:
        click.confirm("Proceed?", abort=True)

    session = build_session(
        profile=ctx.obj.get("aws_profile"),
        region=ctx.obj.get("aws_region"),
    )
    iot = session.client("iot")
    sm = session.client("secretsmanager")

    try:
        result = decommission_thing(
            thing_name,
            policy_name=policy_name,
            secret_id=secret_id,
            iot_client=iot,
            secrets_client=sm,
            keep_secret=keep_secret,
            force_delete_certificate=force_delete,
            recovery_window_days=recovery_window_days,
        )
    except Exception as exc:
        console.print(f"[red]Decommission failed:[/red] {exc}")
        raise click.Abort() from exc

    table = Table(title=f"Decommission summary — {thing_name}")
    table.add_column("Action", style="cyan")
    table.add_column("Resources", style="green")
    table.add_row("Detached principals", _join(result.detached_principals))
    table.add_row("Detached policies", _join(result.detached_policies))
    table.add_row("Inactivated certs", _join(result.inactivated_certificates))
    table.add_row("Deleted certs", _join(result.deleted_certificates))
    table.add_row(
        "Secret",
        result.deleted_secret or ("kept" if result.secret_kept else "(no secret-id)"),
    )
    table.add_row("Skipped (not-found)", _join(result.not_found))
    console.print(table)


def _join(items: list[str]) -> str:
    return "\n".join(items) if items else "(none)"
