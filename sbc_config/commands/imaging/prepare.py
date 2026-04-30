"""Fetch + customize in one step."""

from __future__ import annotations

from pathlib import Path

import click

from sbc_config.commands.imaging.customize import (
    _read_password,
    headless_output_path,
)
from sbc_config.modules.imaging import (
    ImagingError,
    customize_image,
    default_cache_dir,
    download_xz,
    load_pinned_release,
)


@click.command("prepare")
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=default_cache_dir,
    show_default="repo .cache/imaging",
    help="Directory for download and customized .img.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Customized .img path (default: <cache-dir>/<release>-headless.img).",
)
@click.option("--username", required=True, help="Linux login name.")
@click.option(
    "--password",
    envvar="SBC_IMAGING_PASSWORD",
    default=None,
)
@click.option(
    "--password-file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False, readable=True),
    default=None,
)
@click.option(
    "--boot-partition",
    default=None,
    help="Guest boot device; auto-detected if omitted.",
)
@click.option(
    "--wpa-supplicant",
    type=click.Path(path_type=Path, exists=True, dir_okay=False, readable=True),
    default=None,
)
@click.option("--skip-checksum", is_flag=True)
@click.option("--force", is_flag=True)
@click.pass_context
def prepare_command(
    ctx: click.Context,
    cache_dir: Path,
    output: Path | None,
    username: str,
    password: str | None,
    password_file: Path | None,
    boot_partition: str | None,
    wpa_supplicant: Path | None,
    skip_checksum: bool,
    force: bool,
) -> None:
    """Download the pinned release, then write ssh + userconf (+ optional Wi-Fi) to the image."""
    console = ctx.obj["console"]
    release_file: Path = ctx.obj["release_file"]
    release = load_pinned_release(release_file)
    cache_dir = Path(cache_dir)
    xz_path = cache_dir / release.xz_filename()
    download_xz(
        release,
        xz_path,
        console=console,
        skip_checksum=skip_checksum,
        force=force,
    )
    img_out = (
        output
        if output is not None
        else headless_output_path(cache_dir, release.xz_filename())
    )
    secret = _read_password(password, password_file)
    if not secret:
        raise click.BadParameter("Password must not be empty")
    try:
        customize_image(
            xz_path,
            img_out,
            username=username,
            password=secret,
            console=console,
            boot_partition=boot_partition,
            wpa_supplicant=wpa_supplicant,
        )
    except ImagingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.Abort() from exc
    console.print(f"[green]Ready to flash:[/green] {img_out}")
