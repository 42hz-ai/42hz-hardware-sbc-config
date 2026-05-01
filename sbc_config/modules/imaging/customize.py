"""Preseed boot partition (SSH, userconf) on a Raspberry Pi OS disk image."""

from __future__ import annotations

import lzma
import re
import shlex
import shutil
import subprocess
import tempfile

from pathlib import Path

from sbc_config.modules.imaging.types import Notify


class ImagingError(RuntimeError):
    """Customization or tooling failure."""


# Single DNS label (typical LAN / mDNS names). Allows digits at start (unlike RPi OS *username*).
_LINUX_HOSTNAME_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def validate_linux_hostname_label(hostname: str) -> None:
    """
    Hostname for `virt-customize` / mDNS-style discovery (one label, lower-case).

    Letters, digits, hyphens; no leading or trailing hyphen; max 63 characters.
    """
    if _LINUX_HOSTNAME_LABEL_RE.fullmatch(hostname) is None:
        msg = (
            f"Hostname {hostname!r} is invalid. Use one label: lower-case letters, "
            "digits, interior hyphens only; 1-63 characters; no leading/trailing hyphen. "
            "Examples: 42hzpi, pi-worker-1."
        )
        raise ImagingError(msg)


# Raspberry Pi OS first-boot userconf: same rules as the on-device wizard (rptl.io/newuser).
_PI_OS_USERNAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


def validate_rpi_os_username(username: str) -> None:
    """
    Enforce Raspberry Pi OS rules for the initial account (userconf.txt).

    Must start with a letter; only lower-case letters, digits, and hyphens; max 32 chars.
    """
    if _PI_OS_USERNAME_RE.fullmatch(username) is None:
        msg = (
            f"Username {username!r} is invalid for Raspberry Pi OS. "
            "It must start with a letter and contain only lower-case letters, digits, "
            "and hyphens (max 32 characters). Example: hz42, tim, admin-pi."
        )
        raise ImagingError(msg)


def _which_or_raise(name: str) -> str:
    path = shutil.which(name)
    if not path:
        msg = (
            f"Required program {name!r} not found on PATH. "
            f"Install libguestfs-tools (guestfish, virt-customize) and openssl."
        )
        raise ImagingError(msg)
    return path


def apply_hostname_virt_customize(
    image: Path,
    hostname: str,
    *,
    notify: Notify | None = None,
) -> None:
    """Set system hostname on the image root filesystem (libguestfs virt-customize)."""
    validate_linux_hostname_label(hostname)
    virt_customize = _which_or_raise("virt-customize")
    if notify:
        notify("info", f"Setting hostname to {hostname!r} (virt-customize)")
    proc = subprocess.run(
        [virt_customize, "-a", str(image), f"--hostname={hostname}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        msg = (
            proc.stderr.strip()
            or proc.stdout.strip()
            or "virt-customize --hostname failed"
        )
        raise ImagingError(msg)


def xz_decompressed_cache_path(xz_path: Path) -> Path:
    """`release.img.xz` -> `release.img` next to the archive."""
    if not (xz_path.suffix == ".xz" or xz_path.name.endswith(".img.xz")):
        msg = f"Not an xz disk image path: {xz_path}"
        raise ValueError(msg)
    return xz_path.with_name(xz_path.name.removesuffix(".xz"))


def is_xz_disk_image(path: Path) -> bool:
    return path.suffix == ".xz" or path.name.endswith(".img.xz")


def ensure_raw_disk_image(source: Path, *, notify: Notify | None = None) -> Path:
    """
    Return a local `.img` path: pass-through for `.img`, or cached decompress for `.xz`.

    Cache is `<same-dir>/<basename-without-.xz>.img`. It is rebuilt when missing or older
    than the `.xz` (mtime).
    """
    if not is_xz_disk_image(source):
        return source
    cache_img = xz_decompressed_cache_path(source)
    cache_img.parent.mkdir(parents=True, exist_ok=True)
    stale = (not cache_img.is_file()) or (
        cache_img.stat().st_mtime < source.stat().st_mtime
    )
    if stale:
        if notify:
            notify("info", f"Decompressing {source.name} → {cache_img.name}")
        with lzma.open(source, "rb") as src, cache_img.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    elif notify:
        notify(
            "info",
            f"Using cached {cache_img.name} (up to date with {source.name})",
        )
    return cache_img


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


def _materialize_customize_target(
    raw: Path,
    output: Path,
    *,
    notify: Notify | None,
) -> Path:
    """Ensure `output` is a writable copy of `raw` when paths differ."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if raw.resolve() == output.resolve():
        return output
    shutil.copy2(raw, output)
    if notify:
        notify("info", f"Copied {raw.name} → {output.name}")
    return output


def apply_boot_preseed_guestfish(
    image: Path,
    boot_partition: str,
    files: dict[str, Path],
    *,
    notify: Notify | None = None,
) -> None:
    """
    Copy all boot preseed files in one guestfish session (one appliance boot).

    ``files`` maps guest basename (e.g. ``ssh``) to a local path; files are copied to ``/``
    on the FAT boot filesystem.

    A ``copy-in`` of a *directory* creates ``/<that-directory's-basename>/…`` on the guest,
    not a flat copy into ``/``. Multiple sources in one ``copy-in`` line are also fragile.
    We therefore emit **one** ``copy-in <file> /`` per entry so each basename lands on the
    boot volume root (``/ssh``, ``/userconf.txt``, …).
    """
    for remote_name, local_path in files.items():
        if not local_path.is_file():
            msg = f"Missing local file for {remote_name}: {local_path}"
            raise ImagingError(msg)
    guestfish = _which_or_raise("guestfish")
    img_abs = str(image.resolve())
    script_lines: list[str] = ["run", f"mount {boot_partition} /"]
    for name in sorted(files, key=str):
        lp = shlex.quote(str(files[name].resolve()))
        script_lines.append(f"copy-in {lp} /")
    script_lines.append("umount /")
    script = "\n".join(script_lines)
    if notify:
        notify(
            "info",
            f"Installing boot preseed ({len(files)} files, single guestfish session)",
        )
    proc = subprocess.run(
        [guestfish, "--rw", "-a", img_abs],
        input=script + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        msg = (
            proc.stderr.strip()
            or proc.stdout.strip()
            or "guestfish boot preseed failed"
        )
        raise ImagingError(msg)


def customize_image(
    source: Path,
    output: Path,
    *,
    username: str,
    password: str,
    notify: Notify | None = None,
    boot_partition: str | None = None,
    wpa_supplicant: Path | None = None,
    hostname: str | None = None,
) -> Path:
    """
    Write `ssh`, `userconf.txt`, and optional `wpa_supplicant.conf` onto the boot partition.

    Optionally set the system hostname via a second ``virt-customize`` run (updates
    ``/etc/hosts`` correctly; batched boot injection uses only one ``guestfish`` run).

    `source` may be `.img` or `.img.xz`. For `.xz`, a shared cache `*.img` is kept next to
    the archive and only rebuilt when the `.xz` is newer. Customization is applied to
    `output` (a copy when using the cache, so the cached `.img` stays pristine).
    """
    validate_rpi_os_username(username)
    raw = ensure_raw_disk_image(source, notify=notify)
    if is_xz_disk_image(source) and raw.resolve() == output.resolve():
        raise ImagingError(
            "Output must not be the cached .img next to the .xz (that file is shared). "
            "Use a distinct path, e.g. *-headless.img."
        )
    img = _materialize_customize_target(raw, output, notify=notify)
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
        apply_boot_preseed_guestfish(img, boot, files, notify=notify)
    if hostname:
        apply_hostname_virt_customize(img, hostname, notify=notify)
    if notify:
        notify("ok", f"Customized {img}")
    return img
