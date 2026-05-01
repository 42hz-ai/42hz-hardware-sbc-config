"""Print or run `dd` to write a prepared image to removable media."""

from __future__ import annotations

import os
import subprocess
import sys

from pathlib import Path

import click

from sbc_config.modules.imaging import dd_argv, dd_shell


@click.command("flash")
@click.option(
    "--image",
    type=click.Path(path_type=Path, exists=True, dir_okay=False, readable=True),
    required=True,
    help="Prepared .img (e.g. from `sbc imaging prepare`).",
)
@click.option(
    "--device",
    type=str,
    envvar="SBC_FLASH_DEVICE",
    default=None,
    help="Block device (e.g. /dev/sdb). Use env SBC_FLASH_DEVICE to avoid typos.",
)
@click.option(
    "--execute",
    is_flag=True,
    help="Run dd as root (requires CAP; normally run on the host, not in a container).",
)
@click.pass_context
def flash_command(
    ctx: click.Context, image: Path, device: str | None, execute: bool
) -> None:
    """Show the dd command to flash an image (or run it with --execute)."""
    console = ctx.obj["console"]
    if not device:
        raise click.UsageError("Pass --device or set SBC_FLASH_DEVICE (e.g. /dev/sdb).")
    line = dd_shell(image, device)
    console.print(
        "[bold]Flash command (verify OF= is your SD/USB reader, not a system disk):[/bold]"
    )
    console.print(f"  sudo {line}")
    if sys.platform == "darwin":
        console.print(
            "[dim]If dd: Resource busy → sudo diskutil unmountDisk diskN "
            "(N from /dev/rdiskN, e.g. rdisk4 → disk4). Then retry dd.[/dim]"
        )
    if not execute:
        console.print(
            "[dim]Re-run with --execute to run dd from this environment (still needs root).[/dim]"
        )
        return
    if os.geteuid() != 0:
        console.print("[red]--execute requires root (euid 0).[/red]")
        raise click.Abort()
    argv = dd_argv(image, device)
    console.print(f"[cyan]Running:[/cyan] {' '.join(argv)}")
    subprocess.run(argv, check=True)
