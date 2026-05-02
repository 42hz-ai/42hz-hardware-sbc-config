"""Tests for ``sbc_config.modules.iot.greengrass_install``."""

from __future__ import annotations

import tempfile
import unittest

from pathlib import Path
from unittest.mock import MagicMock

from sbc_config.modules.iot.greengrass_install import (
    _wait_for_detached_nucleus_launch,
    greengrass_root_appears_installed,
)


class TestGreengrassRootAppearsInstalled(unittest.TestCase):
    def test_false_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertFalse(greengrass_root_appears_installed(root))

    def test_false_when_only_device_pems(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "device.pem.crt").write_text("x", encoding="utf-8")
            self.assertFalse(greengrass_root_appears_installed(root))

    def test_true_when_packages_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "packages").mkdir(parents=True)
            self.assertTrue(greengrass_root_appears_installed(root))

    def test_true_when_work_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "work").mkdir(parents=True)
            self.assertTrue(greengrass_root_appears_installed(root))


class TestDetachedNucleusLaunch(unittest.TestCase):
    def test_returns_when_log_contains_marker(self) -> None:
        proc = MagicMock()
        proc.poll.return_value = None
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "install.log"
            log_path.write_text(
                "Setup\nLaunched Nucleus successfully\n", encoding="utf-8"
            )
            _wait_for_detached_nucleus_launch(proc, log_path, timeout_s=5.0)

    def test_raises_when_process_exits_before_marker(self) -> None:
        proc = MagicMock()
        proc.poll.return_value = 1
        proc.terminate = MagicMock()
        proc.wait = MagicMock()
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "install.log"
            log_path.write_text("early failure\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                _wait_for_detached_nucleus_launch(proc, log_path, timeout_s=5.0)


if __name__ == "__main__":
    unittest.main()
