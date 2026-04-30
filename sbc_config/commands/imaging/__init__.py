"""Imaging commands — fetch, customize, prepare, flash."""

from __future__ import annotations

from pathlib import Path

import click

from sbc_config.commands.imaging import customize, fetch, flash, prepare
from sbc_config.modules.imaging.paths import default_release_file


@click.group("imaging")
@click.option(
    "--release-file",
    type=click.Path(path_type=Path, dir_okay=False, readable=True),
    default=None,
    help="YAML with image_url and sha256_url (default: imaging/pinned_release.yaml).",
)
@click.pass_context
def imaging_group(ctx: click.Context, release_file: Path | None) -> None:
    """Download and preseed Raspberry Pi OS disk images (SSH + user)."""
    ctx.ensure_object(dict)
    path = release_file if release_file is not None else default_release_file()
    if not path.is_file():
        msg = f"Release file not found: {path}\nPass --release-file or add imaging/pinned_release.yaml."
        raise click.ClickException(msg)
    ctx.obj["release_file"] = path


imaging_group.add_command(fetch.fetch_command)
imaging_group.add_command(customize.customize_command)
imaging_group.add_command(prepare.prepare_command)
imaging_group.add_command(flash.flash_command)

__all__ = ["imaging_group"]
