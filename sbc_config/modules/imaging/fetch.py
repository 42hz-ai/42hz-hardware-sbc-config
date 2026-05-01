"""Download and verify Raspberry Pi OS disk images."""

from __future__ import annotations

import hashlib
import re

from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote

import requests

from sbc_config.modules.imaging.release_spec import PinnedRelease
from sbc_config.modules.imaging.types import ByteProgressFactory, Notify


def _sha256_file_payload(content: str, expected_filename: str) -> str:
    """Extract hex digest from Raspberry Pi .sha256 sidecar (first word on line matching the file)."""
    expected_name = Path(expected_filename).name
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        digest, name_field = parts[0], parts[-1]
        name_field = name_field.removeprefix("*")
        if name_field == expected_name and re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            return digest.lower()
    msg = f"No SHA-256 line found for {expected_name!r} in checksum file"
    raise ValueError(msg)


def expected_sha256_hex(
    release: PinnedRelease, *, session: requests.Session | None = None
) -> str:
    sess = session or requests.Session()
    sha_uri = str(release.sha256_url)
    response = sess.get(sha_uri, timeout=120)
    response.raise_for_status()
    return _sha256_file_payload(response.text, release.xz_filename())


def verify_xz_sha256(xz_path: Path, expected_hex: str) -> None:
    digest = hashlib.sha256()
    with xz_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest().lower()
    if actual != expected_hex.lower():
        msg = f"SHA-256 mismatch for {xz_path}: expected {expected_hex}, got {actual}"
        raise ValueError(msg)


def download_xz(
    release: PinnedRelease,
    dest: Path,
    *,
    notify: Notify | None = None,
    progress: ByteProgressFactory | None = None,
    skip_checksum: bool = False,
    force: bool = False,
    session: requests.Session | None = None,
) -> Path:
    """Download the `.img.xz` to `dest` and verify if not skipped."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    sess = session or requests.Session()
    expected_hex: str | None = None
    if not skip_checksum:
        if notify:
            notify("info", "Fetching checksum…")
        expected_hex = expected_sha256_hex(release, session=sess)

    if dest.exists() and not force and expected_hex is not None:
        try:
            verify_xz_sha256(dest, expected_hex)
        except ValueError:
            if notify:
                notify("warn", "Cached image failed verification; re-downloading.")
        else:
            if notify:
                notify("ok", f"Up to date: {dest}")
            return dest

    url = str(release.image_url)
    if notify:
        notify("info", f"Downloading {url}")
    response = sess.get(url, stream=True, timeout=120)
    response.raise_for_status()
    total = int(response.headers.get("content-length", "0") or 0)

    digest = hashlib.sha256()
    tmp = dest.with_suffix(dest.suffix + ".partial")
    label = unquote(Path(release.image_url.path).name)

    def _write_stream(advance: Callable[[int], None] | None) -> None:
        with tmp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                handle.write(chunk)
                digest.update(chunk)
                if advance is not None:
                    advance(len(chunk))

    if progress is not None:
        with progress(label, total or None) as advance:
            _write_stream(advance)
    else:
        _write_stream(None)

    if expected_hex is not None:
        actual = digest.hexdigest().lower()
        if actual != expected_hex.lower():
            tmp.unlink(missing_ok=True)
            msg = f"Download SHA-256 mismatch: expected {expected_hex}, got {actual}"
            raise ValueError(msg)

    tmp.replace(dest)
    if notify:
        notify("ok", f"Wrote {dest}")
    return dest
