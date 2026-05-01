"""Fetch + customize in one step."""

from __future__ import annotations

import shlex

from pathlib import Path

import click

from rich.console import Console

from sbc_config.commands.imaging.customize import (
    _read_password,
    headless_output_path,
)
from sbc_config.commands.imaging.feedback import (
    byte_progress_for_console,
    notify_for_console,
)
from sbc_config.modules.imaging import (
    ImagingError,
    customize_image,
    dd_shell,
    default_cache_dir,
    download_xz,
    load_pinned_release,
)


def _print_prepare_next_steps(
    console: Console,
    img_out: Path,
    username: str,
    hostname: str | None,
) -> None:
    """Remind operators how to flash on a real host and connect after first boot."""
    img_q = shlex.quote(str(img_out.resolve()))
    ssh_label = hostname if hostname else "raspberrypi"
    dd_line = dd_shell(img_out, "/dev/sdX")
    console.print()
    console.print("[bold]Next steps (on a machine with an SD/USB reader)[/bold]")
    console.print(
        "  [dim]1. Identify the whole-disk device (e.g. lsblk, or diskutil list on macOS).[/dim]"
    )
    console.print(
        f"  2. Flash: [cyan]sbc imaging flash --image {img_q} --device /dev/sdX[/cyan]"
    )
    console.print(
        "     [dim](Copy the printed sudo dd line; verify of= is the reader, not a system disk.)[/dim]"
    )
    console.print(
        f"     [dim]Example dd: sudo {dd_line}[/dim]  [dim](replace /dev/sdX)[/dim]"
    )
    console.print(
        "     [dim]macOS: use of=/dev/rdiskN for speed. If dd says Resource busy, eject mounts only: "
        "sudo diskutil unmountDisk diskN (N matches rdiskN, e.g. rdisk4 → disk4). Close Finder windows on that disk.[/dim]"
    )
    console.print(
        "  3. Eject safely, boot the Pi, wait for first-boot (can take a few minutes)."
    )
    console.print(
        f"  4. SSH (same LAN; mDNS .local or your router's DHCP list): "
        f"[cyan]ssh {username}@{ssh_label}.local[/cyan]"
    )
    console.print(
        "     [dim]If .local does not resolve, use the Pi's IP: "
        f"ssh {username}@<ip>[/dim]"
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
@click.option(
    "--hostname",
    default=None,
    help=(
        "System hostname (single label, lower-case); omit to keep default raspberrypi on LAN."
    ),
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
    hostname: str | None,
    skip_checksum: bool,
    force: bool,
) -> None:
    """Download the pinned release, then write ssh + userconf (+ optional Wi-Fi) to the image."""
    console = ctx.obj["console"]
    release_file: Path = ctx.obj["release_file"]
    release = load_pinned_release(release_file)
    cache_dir = Path(cache_dir)
    xz_path = cache_dir / release.xz_filename()
    notify = notify_for_console(console)
    progress = byte_progress_for_console(console)
    download_xz(
        release,
        xz_path,
        notify=notify,
        progress=progress,
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
            notify=notify,
            boot_partition=boot_partition,
            wpa_supplicant=wpa_supplicant,
            hostname=hostname,
        )
    except ImagingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.Abort() from exc
    console.print(f"[green]Ready to flash:[/green] {img_out}")
    _print_prepare_next_steps(console, img_out, username, hostname)
