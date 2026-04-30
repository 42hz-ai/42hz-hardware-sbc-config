"""Preseed boot partition (SSH, userconf) on a Raspberry Pi OS disk image."""

from __future__ import annotations

import lzma
import shutil
import subprocess
import tempfile

from pathlib import Path

from rich.console import Console


class ImagingError(RuntimeError):
    """Customization or tooling failure."""


def _which_or_raise(name: str) -> str:
    path = shutil.which(name)
    if not path:
        msg = (
            f"Required program {name!r} not found on PATH. "
            f"Install libguestfs-tools (virt-copy-in, guestfish) and openssl."
        )
        raise ImagingError(msg)
    return path


def resolve_boot_partition(image: Path) -> str:
    """Return guest device for the FAT boot partition (e.g. /dev/sda1)."""
    guestfish = _which_or_raise("guestfish")
    script = "run\nlist-filesystems\n"
    proc = subprocess.run(
        [guestfish, "--ro", "-a", str(image)],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        msg = f"guestfish failed: {proc.stderr.strip() or proc.stdout}"
        raise ImagingError(msg)
    vfat_dev: str | None = None
    for raw_line in proc.stdout.splitlines():
        stripped = raw_line.strip()
        if ": vfat" in stripped:
            dev, _, _ = stripped.partition(":")
            vfat_dev = dev.strip()
            break
    if not vfat_dev:
        msg = "Could not find a vfat (boot) partition in the image"
        raise ImagingError(msg)
    return vfat_dev


def build_userconf_line(username: str, password: str) -> str:
    """One line for /boot/userconf.txt: username:sha-512-crypt hash."""
    openssl = _which_or_raise("openssl")
    proc = subprocess.run(
        [openssl, "passwd", "-6", "-stdin"],
        input=(password + "\n").encode(),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode().strip() or "openssl failed"
        raise ImagingError(err)
    digest = proc.stdout.decode().strip()
    if not digest or not digest.startswith("$6$"):
        msg = "Unexpected openssl output for password hash"
        raise ImagingError(msg)
    return f"{username}:{digest}\n"


def materialize_raw_image(source: Path, output_img: Path, *, console: Console) -> Path:
    """Produce a writable `.img` at `output_img` from `.img` or `.img.xz` source."""
    output_img.parent.mkdir(parents=True, exist_ok=True)
    is_xz = source.suffix == ".xz" or source.name.endswith(".img.xz")
    if is_xz:
        console.print(f"[cyan]Decompressing[/cyan] {source.name} → {output_img.name}")
        with lzma.open(source, "rb") as src, output_img.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        return output_img
    if source.resolve() == output_img.resolve():
        return output_img
    shutil.copy2(source, output_img)
    console.print(f"[cyan]Copied[/cyan] {source.name} → {output_img.name}")
    return output_img


def copy_into_boot_partition(
    image: Path,
    boot_partition: str,
    files: dict[str, Path],
    *,
    console: Console,
) -> None:
    """Copy local files (guest basename -> local path) to `/` on the boot FAT partition."""
    virt_copy_in = _which_or_raise("virt-copy-in")
    for remote_name, local_path in files.items():
        if not local_path.is_file():
            msg = f"Missing local file for {remote_name}: {local_path}"
            raise ImagingError(msg)
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp) / remote_name
            staging.write_bytes(local_path.read_bytes())
            console.print(f"[cyan]Installing[/cyan] /{remote_name} on {boot_partition}")
            proc = subprocess.run(
                [
                    virt_copy_in,
                    "-a",
                    str(image),
                    "-m",
                    boot_partition,
                    str(staging),
                    "/",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                msg = (
                    proc.stderr.strip() or proc.stdout.strip() or "virt-copy-in failed"
                )
                raise ImagingError(msg)


def customize_image(
    source: Path,
    output: Path,
    *,
    username: str,
    password: str,
    console: Console,
    boot_partition: str | None = None,
    wpa_supplicant: Path | None = None,
) -> Path:
    """
    Write `ssh`, `userconf.txt`, and optional `wpa_supplicant.conf` onto the boot partition.

    `source` may be `.img` or `.img.xz`. The customized image is always written to `output`
    (decompressed or copied first, then modified in place).
    """
    img = materialize_raw_image(source, output, console=console)
    boot = boot_partition or resolve_boot_partition(img)
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        ssh_file = td_path / "ssh"
        ssh_file.write_bytes(b"")
        userconf = td_path / "userconf.txt"
        userconf.write_text(build_userconf_line(username, password), encoding="utf-8")
        files: dict[str, Path] = {"ssh": ssh_file, "userconf.txt": userconf}
        if wpa_supplicant is not None:
            if not wpa_supplicant.is_file():
                msg = f"wpa_supplicant.conf not found: {wpa_supplicant}"
                raise ImagingError(msg)
            files["wpa_supplicant.conf"] = wpa_supplicant
        copy_into_boot_partition(img, boot, files, console=console)
    console.print(f"[green]Customized[/green] {img}")
    return img
