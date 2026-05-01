"""Download a pinned Raspberry Pi OS .img.xz."""

from __future__ import annotations

from pathlib import Path

import click

from sbc_config.commands.imaging.feedback import (
    byte_progress_for_console,
    notify_for_console,
)
from sbc_config.modules.imaging import (
    default_cache_dir,
    download_xz,
    load_pinned_release,
)


@click.command("fetch")
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=default_cache_dir,
    show_default="repo .cache/imaging",
    help="Directory for the downloaded .img.xz.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Exact output path (defaults to <cache-dir>/<artifact name>).",
)
@click.option(
    "--skip-checksum",
    is_flag=True,
    help="Do not verify SHA-256 (not recommended).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Re-download even if a verified file already exists.",
)
@click.pass_context
def fetch_command(
    ctx: click.Context,
    cache_dir: Path,
    output: Path | None,
    skip_checksum: bool,
    force: bool,
) -> None:
    """Download the pinned release (see `sbc imaging --help`) and verify checksum."""
    console = ctx.obj["console"]
    release_file: Path = ctx.obj["release_file"]
    release = load_pinned_release(release_file)
    cache_dir = Path(cache_dir)
    dest = output if output is not None else cache_dir / release.xz_filename()
    notify = notify_for_console(console)
    progress = byte_progress_for_console(console)
    download_xz(
        release,
        dest,
        notify=notify,
        progress=progress,
        skip_checksum=skip_checksum,
        force=force,
    )
