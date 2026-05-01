"""Imaging commands — fetch, customize, prepare, flash."""

from __future__ import annotations

from pathlib import Path

import click

from sbc_config.commands.imaging import customize, fetch, flash, prepare
from sbc_config.modules.imaging.catalog import (
    list_release_slugs,
    load_release_index,
    resolve_release_yaml,
)


@click.group("imaging")
@click.option(
    "--release",
    "-r",
    "release_key",
    default=None,
    metavar="KEY",
    help="Release id (imaging/releases/<KEY>.yaml). Default: value of `default` in imaging/releases/index.yaml.",
)
@click.option(
    "--release-file",
    type=click.Path(path_type=Path, dir_okay=False, readable=True),
    default=None,
    help="Use this YAML pin instead of imaging/releases/ (mutually exclusive with --release).",
)
@click.pass_context
def imaging_group(
    ctx: click.Context,
    release_key: str | None,
    release_file: Path | None,
) -> None:
    """Download and preseed Raspberry Pi OS disk images (SSH + user)."""
    ctx.ensure_object(dict)
    if release_key is not None and release_file is not None:
        raise click.UsageError("Use at most one of --release and --release-file.")
    try:
        path = resolve_release_yaml(release=release_key, release_file=release_file)
    except FileNotFoundError as exc:
        idx_hint = ""
        try:
            idx = load_release_index()
            avail = ", ".join(list_release_slugs()) or "(no release YAML files yet)"
            idx_hint = f"\nIndex default is {idx.default!r}. Known keys: {avail}."
        except OSError, ValueError, FileNotFoundError:
            pass
        raise click.ClickException(f"{exc}{idx_hint}") from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    ctx.obj["release_file"] = path


imaging_group.add_command(fetch.fetch_command)
imaging_group.add_command(customize.customize_command)
imaging_group.add_command(prepare.prepare_command)
imaging_group.add_command(flash.flash_command)

__all__ = ["imaging_group"]
