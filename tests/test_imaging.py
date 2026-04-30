"""Tests for Raspberry Pi imaging helpers."""

from __future__ import annotations

import tempfile
import unittest

from pathlib import Path

from sbc_config.commands.imaging.customize import headless_output_path
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


if __name__ == "__main__":
    unittest.main()
