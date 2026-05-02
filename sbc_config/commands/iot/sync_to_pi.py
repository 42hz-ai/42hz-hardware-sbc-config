"""``sbc iot sync-to-pi`` — rsync repo + PEM bundle to a Raspberry Pi."""

from __future__ import annotations

import subprocess

from pathlib import Path

import click

from sbc_config.modules.iot.defaults import (
    ENV_PI_SSH,
    HELLO_WORLD_THING_NAME,
    SYNC_DEFAULT_REMOTE_BUNDLE,
    SYNC_DEFAULT_REMOTE_REPO,
    default_bundle_dir_for_thing,
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
    "--thing-name",
    default=HELLO_WORLD_THING_NAME,
    show_default=True,
    metavar="NAME",
    help=(
        "Used only when --bundle-dir is omitted: default bundle path is "
        "aws-iot-bundles/<NAME> or $SBC_IOT_FETCH_OUT_DIR."
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
    default=None,
    metavar="DIR",
    help=(
        "Local PEM bundle directory. Default: $SBC_IOT_FETCH_OUT_DIR or "
        "aws-iot-bundles/<--thing-name>. Relative paths use the current working directory."
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
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Rsync verbose: use once for -v, twice for -vv, three times for -vvv (live output).",
)
@click.option(
    "--progress/--no-progress",
    "show_progress",
    default=False,
    help="Show overall rsync transfer progress (--info=progress2; live on stderr).",
)
@click.pass_context
def sync_to_pi_command(
    ctx: click.Context,
    ssh: str | None,
    thing_name: str,
    repo_root: Path | None,
    remote_repo: str,
    bundle_dir: Path | None,
    remote_bundle: str,
    skip_repo: bool,
    skip_bundle: bool,
    dry_run: bool,
    verbose: int,
    show_progress: bool,
) -> None:
    """Rsync the repo checkout and PEM bundle to the Pi over SSH.

    Requires ``rsync`` and ``ssh`` on the operator's PATH.  The Pi must
    already have an SSH daemon running and accept the caller's key (or
    password).

    Typical first-time flow:

    \b
        export SBC_IOT_PI_SSH=hz42@192.168.8.122
        uv run sbc iot fetch-credentials --thing-name hw-pi-001
        uv run sbc iot sync-to-pi --dry-run   # preview
        uv run sbc iot sync-to-pi             # push
        uv run sbc iot sync-to-pi -v --progress   # live rsync file list + overall %
    """
    console = ctx.obj["console"]

    if skip_repo and skip_bundle:
        console.print(
            "[yellow]--skip-repo and --skip-bundle both set — nothing to do.[/yellow]"
        )
        raise click.Abort()

    def rsync_options() -> tuple[tuple[str, ...], bool]:
        extras: list[str] = []
        if show_progress:
            extras.append("--info=progress2")
        if verbose > 0:
            extras.append(f"-{'v' * min(verbose, 3)}")
        tup = tuple(extras)
        return tup, bool(tup)

    extra_args, inherit_stdio = rsync_options()

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
                extra_args=extra_args,
                inherit_stdio=inherit_stdio,
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
        bundle_src = (
            bundle_dir
            if bundle_dir is not None
            else default_bundle_dir_for_thing(thing_name)
        )
        effective_bundle = (
            (Path.cwd() / bundle_src).resolve()
            if not bundle_src.is_absolute()
            else bundle_src.resolve()
        )
        console.print(
            f"[cyan]Syncing bundle[/cyan]{dry_label} "
            f"[bold]{effective_bundle}/[/bold] → [bold]{ssh or '($SBC_IOT_PI_SSH)'}:{remote_bundle}[/bold]"
        )
        try:
            result = sync_bundle(
                ssh,
                bundle_dir=effective_bundle,
                remote_bundle=remote_bundle,
                dry_run=dry_run,
                extra_args=extra_args,
                inherit_stdio=inherit_stdio,
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
