"""``sbc iot list-orphan-certs`` — audit certs not attached to any Thing."""

from __future__ import annotations

import click

from rich.table import Table

from sbc_config.modules.iot.client import build_session
from sbc_config.modules.iot.lifecycle import (
    delete_certificate,
    list_orphan_certificates,
)


@click.command("list-orphan-certs")
@click.option(
    "--policy-name",
    default=None,
    metavar="NAME",
    help="Filter to certs that are also attached to this policy.",
)
@click.option(
    "--delete",
    is_flag=True,
    help="Detach and delete each orphan (idempotent; prompts unless --yes).",
)
@click.option(
    "--force-delete",
    is_flag=True,
    help="Pass forceDelete=True to DeleteCertificate (use with --delete).",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt before --delete.",
)
@click.pass_context
def list_orphan_certs_command(
    ctx: click.Context,
    policy_name: str | None,
    delete: bool,
    force_delete: bool,
    yes: bool,
) -> None:
    """List (and optionally tear down) certificates with no Thing attachment."""
    console = ctx.obj["console"]
    session = build_session(
        profile=ctx.obj.get("aws_profile"),
        region=ctx.obj.get("aws_region"),
    )
    iot = session.client("iot")

    try:
        orphans = list_orphan_certificates(iot_client=iot, policy_name=policy_name)
    except Exception as exc:
        console.print(f"[red]ListCertificates failed:[/red] {exc}")
        raise click.Abort() from exc

    if not orphans:
        console.print("[green]No orphan certificates.[/green]")
        return

    table = Table(title=f"Orphan certificates ({len(orphans)})")
    table.add_column("Certificate ID", style="cyan")
    table.add_column("Status")
    table.add_column("Created")
    table.add_column("Attached policies", style="yellow")
    for cert in orphans:
        table.add_row(
            cert.certificate_id,
            cert.status,
            cert.creation_date or "-",
            ", ".join(cert.attached_policies) or "(none)",
        )
    console.print(table)

    if not delete:
        return

    if not yes:
        click.confirm(
            f"Detach + delete {len(orphans)} orphan certificate(s)?",
            abort=True,
        )

    for cert in orphans:
        console.print(f"[cyan]Deleting[/cyan] {cert.certificate_id}")
        try:
            delete_certificate(
                cert.certificate_id,
                iot_client=iot,
                force_delete=force_delete,
            )
        except Exception as exc:
            console.print(f"[red]Failed[/red] to delete {cert.certificate_id}: {exc}")
    console.print("[green]Done.[/green]")
