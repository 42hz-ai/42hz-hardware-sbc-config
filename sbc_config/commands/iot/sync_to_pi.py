"""``sbc iot sync-to-pi`` — rsync repo + PEM bundle to a Raspberry Pi."""

from __future__ import annotations

import subprocess

from pathlib import Path

import click

from sbc_config.modules.iot.defaults import (
    ENV_PI_SSH,
    SYNC_DEFAULT_BUNDLE_RELATIVE,
    SYNC_DEFAULT_REMOTE_BUNDLE,
    SYNC_DEFAULT_REMOTE_REPO,
)
from sbc_config.modules.iot.pi_sync import sync_bundle, sync_repo


@click.command("sync-to-pi")
@click.option(
    "--ssh",
    default=None,
    metavar="USER@HOST",
    envvar=ENV_PI_SSH,
    show_default=f"${ENV_PI_SSH}",
    help=(
        f"SSH target for the Pi (e.g. hz42@192.168.8.122). "
        f"Falls back to ${ENV_PI_SSH} when omitted."
    ),
)
@click.option(
    "--repo-root",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True, exists=True),
    default=None,
    metavar="DIR",
    help="Local repo root to sync (default: current working directory).",
)
@click.option(
    "--remote-repo",
    default=SYNC_DEFAULT_REMOTE_REPO,
    show_default=True,
    metavar="PATH",
    help="Destination path for the repo on the Pi.",
)
@click.option(
    "--bundle-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=SYNC_DEFAULT_BUNDLE_RELATIVE,
    show_default=True,
    metavar="DIR",
    help=(
        "Local PEM bundle directory (cert, key, cas/, endpoint.txt). "
        "Relative paths are resolved against the current working directory."
    ),
)
@click.option(
    "--remote-bundle",
    default=SYNC_DEFAULT_REMOTE_BUNDLE,
    show_default=True,
    metavar="PATH",
    help="Destination path for the PEM bundle on the Pi (becomes /data/aws-iot in container).",
)
@click.option(
    "--skip-repo",
    is_flag=True,
    help="Skip syncing the repo — push bundle only.",
)
@click.option(
    "--skip-bundle",
    is_flag=True,
    help="Skip syncing the PEM bundle — push repo only.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Pass --dry-run to rsync: show what would transfer without moving files.",
)
@click.pass_context
def sync_to_pi_command(
    ctx: click.Context,
    ssh: str | None,
    repo_root: Path | None,
    remote_repo: str,
    bundle_dir: Path,
    remote_bundle: str,
    skip_repo: bool,
    skip_bundle: bool,
    dry_run: bool,
) -> None:
    """Rsync the repo checkout and PEM bundle to the Pi over SSH.

    Requires ``rsync`` and ``ssh`` on the operator's PATH.  The Pi must
    already have an SSH daemon running and accept the caller's key (or
    password).

    Typical first-time flow:

    \b
        export SBC_IOT_PI_SSH=hz42@192.168.8.122
        export SBC_IOT_FETCH_OUT_DIR=aws-iot-bundle
        uv run sbc iot fetch-credentials
        uv run sbc iot sync-to-pi --dry-run   # preview
        uv run sbc iot sync-to-pi             # push
    """
    console = ctx.obj["console"]

    if skip_repo and skip_bundle:
        console.print(
            "[yellow]--skip-repo and --skip-bundle both set — nothing to do.[/yellow]"
        )
        raise click.Abort()

    dry_label = " [yellow](dry-run)[/yellow]" if dry_run else ""

    if not skip_repo:
        effective_root = (repo_root or Path.cwd()).resolve()
        console.print(
            f"[cyan]Syncing repo[/cyan]{dry_label} "
            f"[bold]{effective_root}/[/bold] → [bold]{ssh or '($SBC_IOT_PI_SSH)'}:{remote_repo}[/bold]"
        )
        try:
            result = sync_repo(
                ssh,
                repo_root=repo_root,
                remote_repo=remote_repo,
                dry_run=dry_run,
            )
            if result.stdout:
                console.print(result.stdout.decode(errors="replace"))
        except ValueError as exc:
            console.print(f"[red]SSH target error:[/red] {exc}")
            raise click.Abort() from exc
        except subprocess.CalledProcessError as exc:
            console.print(
                f"[red]rsync (repo) failed:[/red] {exc.stderr.decode(errors='replace')}"
            )
            raise click.Abort() from exc
        console.print("[green]Repo synced.[/green]")

    if not skip_bundle:
        effective_bundle = (
            (Path.cwd() / bundle_dir).resolve()
            if not bundle_dir.is_absolute()
            else bundle_dir
        )
        console.print(
            f"[cyan]Syncing bundle[/cyan]{dry_label} "
            f"[bold]{effective_bundle}/[/bold] → [bold]{ssh or '($SBC_IOT_PI_SSH)'}:{remote_bundle}[/bold]"
        )
        try:
            result = sync_bundle(
                ssh,
                bundle_dir=bundle_dir if bundle_dir.is_absolute() else None,
                remote_bundle=remote_bundle,
                dry_run=dry_run,
            )
            if result.stdout:
                console.print(result.stdout.decode(errors="replace"))
        except ValueError as exc:
            console.print(f"[red]SSH target error:[/red] {exc}")
            raise click.Abort() from exc
        except subprocess.CalledProcessError as exc:
            console.print(
                f"[red]rsync (bundle) failed:[/red] {exc.stderr.decode(errors='replace')}"
            )
            raise click.Abort() from exc
        console.print("[green]Bundle synced.[/green]")

    if dry_run:
        console.print("[yellow]Dry-run complete — no files transferred.[/yellow]")
