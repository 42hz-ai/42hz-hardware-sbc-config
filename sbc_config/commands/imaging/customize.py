"""Preseed SSH and user on a Raspberry Pi OS image."""

from __future__ import annotations

from pathlib import Path

import click

from sbc_config.commands.imaging.feedback import notify_for_console
from sbc_config.modules.imaging import ImagingError, customize_image


def _read_password(password: str | None, password_file: Path | None) -> str:
    if password_file is not None:
        return password_file.read_text(encoding="utf-8").strip()
    if password is not None:
        return password
    return click.prompt(
        "Password for the initial user", hide_input=True, confirmation_prompt=True
    )


@click.command("customize")
@click.option(
    "--input",
    "input_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False, readable=True),
    required=True,
    help="Source .img or .img.xz (typically from `sbc imaging fetch`).",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    required=True,
    help="Writable output .img path (will be overwritten).",
)
@click.option(
    "--username",
    required=True,
    help=(
        "Linux login: must start with a letter; only a-z, digits, hyphens (RPi OS rule)."
    ),
)
@click.option(
    "--password",
    envvar="SBC_IMAGING_PASSWORD",
    default=None,
    help="Initial password (avoid on shared systems; prefer --password-file or prompt).",
)
@click.option(
    "--password-file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False, readable=True),
    default=None,
    help="Read initial password from file (single line, no trailing newline required).",
)
@click.option(
    "--boot-partition",
    default=None,
    help="Guest boot device (e.g. /dev/sda1); auto-detected if omitted.",
)
@click.option(
    "--wpa-supplicant",
    type=click.Path(path_type=Path, exists=True, dir_okay=False, readable=True),
    default=None,
    help="Optional wpa_supplicant.conf copied to the boot partition root.",
)
@click.option(
    "--hostname",
    default=None,
    help=(
        "System hostname (single DNS label, lower-case). Sets /etc/hostname on the image; "
        "omit to keep raspberrypi."
    ),
)
@click.pass_context
def customize_command(
    ctx: click.Context,
    input_path: Path,
    output: Path,
    username: str,
    password: str | None,
    password_file: Path | None,
    boot_partition: str | None,
    wpa_supplicant: Path | None,
    hostname: str | None,
) -> None:
    """Create ssh + userconf.txt on the FAT boot partition (headless SSH on first boot)."""
    console = ctx.obj["console"]
    secret = _read_password(password, password_file)
    if not secret:
        raise click.BadParameter("Password must not be empty")
    try:
        customize_image(
            input_path,
            output,
            username=username,
            password=secret,
            notify=notify_for_console(console),
            boot_partition=boot_partition,
            wpa_supplicant=wpa_supplicant,
            hostname=hostname,
        )
    except ImagingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.Abort() from exc


def headless_output_path(cache_dir: Path, xz_name: str) -> Path:
    """Map downloaded .img.xz name to `-headless.img` in cache."""
    base = xz_name.removesuffix(".xz")
    stem = Path(base).stem
    return cache_dir / f"{stem}-headless.img"
