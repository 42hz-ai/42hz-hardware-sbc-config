"""Tests for Raspberry Pi imaging helpers."""

from __future__ import annotations

import lzma
import shlex
import tempfile
import unittest

from pathlib import Path
from unittest.mock import MagicMock, patch

from sbc_config.commands.imaging.customize import headless_output_path
from sbc_config.modules.imaging.catalog import (
    list_release_slugs,
    load_release_index,
    resolve_release_yaml,
)
from sbc_config.modules.imaging.customize import (
    ImagingError,
    apply_boot_preseed_guestfish,
    ensure_raw_disk_image,
    validate_linux_hostname_label,
    validate_rpi_os_username,
    xz_decompressed_cache_path,
)
from sbc_config.modules.imaging.fetch import _sha256_file_payload
from sbc_config.modules.imaging.release_spec import load_pinned_release


class Sha256PayloadTests(unittest.TestCase):
    def test_parses_two_field_line(self) -> None:
        digest = "a" * 64
        content = f"{digest}  my-lite.img.xz\n"
        got = _sha256_file_payload(content, "my-lite.img.xz")
        self.assertEqual(got, digest.lower())

    def test_parses_asterisk_form(self) -> None:
        digest = "b" * 64
        content = f"{digest} *2026-04-21-raspios-trixie-arm64-lite.img.xz\n"
        got = _sha256_file_payload(
            content,
            "2026-04-21-raspios-trixie-arm64-lite.img.xz",
        )
        self.assertEqual(got, digest.lower())


class UsernameValidationTests(unittest.TestCase):
    def test_accepts_letter_first(self) -> None:
        validate_rpi_os_username("hz42")
        validate_rpi_os_username("a")
        validate_rpi_os_username("admin-pi")

    def test_rejects_leading_digit(self) -> None:
        with self.assertRaises(ImagingError):
            validate_rpi_os_username("42hz")


class HostnameValidationTests(unittest.TestCase):
    def test_hostname_allows_leading_digit(self) -> None:
        validate_linux_hostname_label("42hzpi")
        validate_linux_hostname_label("a")

    def test_hostname_rejects_leading_hyphen(self) -> None:
        with self.assertRaises(ImagingError):
            validate_linux_hostname_label("-bad")

    def test_hostname_rejects_trailing_hyphen(self) -> None:
        with self.assertRaises(ImagingError):
            validate_linux_hostname_label("bad-")


class PinnedReleaseTests(unittest.TestCase):
    def test_loads_yaml(self) -> None:
        text = """
image_url: "https://example.com/image.img.xz"
sha256_url: "https://example.com/image.img.xz.sha256"
artifact_basename: "custom.img.xz"
"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pinned.yaml"
            path.write_text(text, encoding="utf-8")
            pr = load_pinned_release(path)
            self.assertEqual(pr.xz_filename(), "custom.img.xz")


class HeadlessNameTests(unittest.TestCase):
    def test_headless_suffix(self) -> None:
        p = headless_output_path(
            Path("/cache"),
            "2026-04-21-raspios-trixie-arm64-lite.img.xz",
        )
        self.assertEqual(
            p,
            Path("/cache") / "2026-04-21-raspios-trixie-arm64-lite-headless.img",
        )


class DecompressCacheTests(unittest.TestCase):
    def test_cache_path_replaces_xz_suffix(self) -> None:
        self.assertEqual(
            xz_decompressed_cache_path(Path("dir/a.img.xz")),
            Path("dir/a.img"),
        )

    def test_second_ensure_skips_decompress_when_fresh(self) -> None:
        payload = b"fake-disk-bytes"
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            xz_path = tdir / "disk.img.xz"
            xz_path.write_bytes(lzma.compress(payload))
            calls: list[str] = []

            def notify(level: str, message: str) -> None:
                calls.append(f"{level}:{message}")

            ensure_raw_disk_image(xz_path, notify=notify)
            cache = tdir / "disk.img"
            mtime_after_first = cache.stat().st_mtime_ns
            ensure_raw_disk_image(xz_path, notify=notify)
            self.assertEqual(cache.read_bytes(), payload)
            self.assertEqual(cache.stat().st_mtime_ns, mtime_after_first)
            self.assertTrue(
                any("Using cached disk.img" in c for c in calls),
                msg=calls,
            )


class BootPreseedGuestfishTests(unittest.TestCase):
    def test_copy_in_one_line_per_file_not_directory(self) -> None:
        """Regression: directory copy-in nests; one line per file lands basenames on /."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            img = td_path / "disk.img"
            img.write_bytes(b"\0" * 4096)
            ssh_p = td_path / "ssh"
            uc_p = td_path / "userconf.txt"
            ssh_p.write_bytes(b"")
            uc_p.write_text("user:$6$x\n", encoding="utf-8")
            files = {"ssh": ssh_p, "userconf.txt": uc_p}
            with (
                patch(
                    "sbc_config.modules.imaging.customize.shutil.which",
                    return_value="/bin/guestfish",
                ),
                patch(
                    "sbc_config.modules.imaging.customize.subprocess.run",
                ) as run,
            ):
                run.return_value = MagicMock(returncode=0, stderr="", stdout="")
                apply_boot_preseed_guestfish(img, "/dev/sda1", files)
        script = run.call_args[1]["input"]
        copy_lines = [ln for ln in script.splitlines() if ln.startswith("copy-in ")]
        self.assertEqual(len(copy_lines), 2)
        stems = set()
        for line in copy_lines:
            tok = shlex.split(line)
            self.assertEqual(tok[0], "copy-in")
            self.assertEqual(tok[-1], "/")
            self.assertEqual(len(tok), 3)
            stems.add(Path(tok[1]).name)
        self.assertEqual(stems, {"ssh", "userconf.txt"})


class ReleaseCatalogTests(unittest.TestCase):
    def test_index_default_matches_repo_pin(self) -> None:
        idx = load_release_index()
        self.assertEqual(idx.default, "trixie-2026-04-21-lite-arm64")

    def test_resolve_default_release_path(self) -> None:
        path = resolve_release_yaml(release=None, release_file=None)
        self.assertTrue(path.is_file())
        self.assertIn("raspios-trixie-arm64-lite", path.read_text(encoding="utf-8"))

    def test_list_slugs_includes_trixie_pin(self) -> None:
        self.assertIn("trixie-2026-04-21-lite-arm64", list_release_slugs())

    def test_resolve_mutually_exclusive_args(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            phantom = Path(td) / "custom.yaml"
            phantom.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                resolve_release_yaml(
                    release="trixie-2026-04-21-lite-arm64",
                    release_file=phantom,
                )


if __name__ == "__main__":
    unittest.main()
