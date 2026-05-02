"""Tests for Pi runner additions: endpoint.txt sidecar and pi_sync helpers."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from pathlib import Path
from unittest.mock import MagicMock, patch

from sbc_config.modules.iot.credentials import (
    ENDPOINT_FILENAME,
    SecretBundle,
    write_bundle_to_disk,
)
from sbc_config.modules.iot.defaults import (
    HELLO_WORLD_THING_NAME,
    SYNC_DEFAULT_BUNDLE_RELATIVE,
    resolve_pi_ssh,
)
from sbc_config.modules.iot.pi_sync import sync_bundle, sync_repo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BUNDLE_WITH_ENDPOINT = SecretBundle(
    thing_name="hw-pi-001",
    certificate_id="abc",
    certificate_arn="arn:aws:iot:us-west-2:123:cert/abc",
    certificate_pem="-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----\n",
    private_key="-----BEGIN RSA PRIVATE KEY-----\nFAKE\n-----END RSA PRIVATE KEY-----\n",
    iot_data_endpoint="abc123.iot.us-west-2.amazonaws.com",
)

_BUNDLE_WITHOUT_ENDPOINT = SecretBundle(
    thing_name="hw-pi-001",
    certificate_id="abc",
    certificate_arn="arn:aws:iot:us-west-2:123:cert/abc",
    certificate_pem="-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----\n",
    private_key="-----BEGIN RSA PRIVATE KEY-----\nFAKE\n-----END RSA PRIVATE KEY-----\n",
    iot_data_endpoint=None,
)


# ---------------------------------------------------------------------------
# Endpoint sidecar
# ---------------------------------------------------------------------------


class TestEndpointSidecar(unittest.TestCase):
    """write_bundle_to_disk writes endpoint.txt iff iot_data_endpoint is set."""

    def test_endpoint_txt_written_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            written = write_bundle_to_disk(
                _BUNDLE_WITH_ENDPOINT, out_dir, download_cas=False
            )

            endpoint_path = out_dir / ENDPOINT_FILENAME
            self.assertIn("endpoint", written)
            self.assertEqual(written["endpoint"], endpoint_path)
            self.assertTrue(endpoint_path.exists())
            content = endpoint_path.read_text(encoding="utf-8").strip()
            self.assertEqual(content, "abc123.iot.us-west-2.amazonaws.com")
            self.assertEqual(oct(endpoint_path.stat().st_mode & 0o777), oct(0o644))

    def test_endpoint_txt_absent_when_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            written = write_bundle_to_disk(
                _BUNDLE_WITHOUT_ENDPOINT, out_dir, download_cas=False
            )

            self.assertNotIn("endpoint", written)
            self.assertFalse((out_dir / ENDPOINT_FILENAME).exists())

    def test_endpoint_txt_strips_whitespace(self) -> None:
        bundle = SecretBundle(
            thing_name="hw-pi-001",
            certificate_id="abc",
            certificate_arn="arn:aws:iot:us-west-2:123:cert/abc",
            certificate_pem="FAKE",
            private_key="FAKE",
            iot_data_endpoint="  spaces.iot.us-west-2.amazonaws.com  \n",
        )
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            write_bundle_to_disk(bundle, out_dir, download_cas=False)
            content = (out_dir / ENDPOINT_FILENAME).read_text(encoding="utf-8").strip()
            self.assertEqual(content, "spaces.iot.us-west-2.amazonaws.com")


# ---------------------------------------------------------------------------
# defaults.py
# ---------------------------------------------------------------------------


class TestDefaults(unittest.TestCase):
    def test_hello_world_thing_name(self) -> None:
        self.assertEqual(HELLO_WORLD_THING_NAME, "hw-pi-001")

    def test_sync_default_bundle_relative(self) -> None:
        self.assertEqual(SYNC_DEFAULT_BUNDLE_RELATIVE, Path("aws-iot-bundle"))

    def test_resolve_pi_ssh_explicit(self) -> None:
        self.assertEqual(resolve_pi_ssh("pi@10.0.0.1"), "pi@10.0.0.1")

    def test_resolve_pi_ssh_from_env(self) -> None:
        with patch.dict("os.environ", {"SBC_IOT_PI_SSH": "hz42@192.168.8.122"}):
            self.assertEqual(resolve_pi_ssh(None), "hz42@192.168.8.122")

    def test_resolve_pi_ssh_missing_raises(self) -> None:
        env_without_ssh = {k: v for k, v in os.environ.items() if k != "SBC_IOT_PI_SSH"}
        with patch.dict("os.environ", env_without_ssh, clear=True):
            with self.assertRaises(ValueError, msg="should raise when no ssh target"):
                resolve_pi_ssh(None)


# ---------------------------------------------------------------------------
# pi_sync.py
# ---------------------------------------------------------------------------


class TestPiSync(unittest.TestCase):
    """Verify rsync is called with the right source / dest patterns."""

    def _make_completed(self) -> subprocess.CompletedProcess[bytes]:
        cp: subprocess.CompletedProcess[bytes] = MagicMock(
            spec=subprocess.CompletedProcess
        )
        cp.stdout = b""
        cp.returncode = 0
        return cp

    @patch("sbc_config.modules.iot.pi_sync.subprocess.run")
    def test_sync_repo_builds_correct_dest(self, mock_run: MagicMock) -> None:
        mock_run.return_value = self._make_completed()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            sync_repo("user@host", repo_root=repo, remote_repo="~/sbc-config")

        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "rsync")
        source = args[-2]
        dest = args[-1]
        self.assertTrue(
            source.endswith("/"), "source should end with / for content-only sync"
        )
        self.assertEqual(
            dest,
            "user@host:~/sbc-config",
            "remote ~ must not be expanded with operator $HOME (devcontainer is /root)",
        )

    @patch("sbc_config.modules.iot.pi_sync.subprocess.run")
    def test_verbose_and_progress_forwarded(self, mock_run: MagicMock) -> None:
        mock_run.return_value = self._make_completed()
        with tempfile.TemporaryDirectory() as td:
            sync_repo(
                "user@host",
                repo_root=Path(td),
                extra_args=("--info=progress2", "-vv"),
                inherit_stdio=True,
            )

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("--info=progress2", args)
        self.assertIn("-vv", args)
        kwargs = mock_run.call_args[1]
        self.assertNotIn("capture_output", kwargs)

    @patch("sbc_config.modules.iot.pi_sync.subprocess.run")
    def test_sync_bundle_builds_correct_dest(self, mock_run: MagicMock) -> None:
        mock_run.return_value = self._make_completed()
        with tempfile.TemporaryDirectory() as td:
            bundle = Path(td)
            sync_bundle("user@host", bundle_dir=bundle, remote_bundle="~/iot-data")

        args = mock_run.call_args[0][0]
        dest = args[-1]
        self.assertEqual(dest, "user@host:~/iot-data")

    @patch("sbc_config.modules.iot.pi_sync.subprocess.run")
    def test_dry_run_flag_injected(self, mock_run: MagicMock) -> None:
        mock_run.return_value = self._make_completed()
        with tempfile.TemporaryDirectory() as td:
            sync_repo("u@h", repo_root=Path(td), dry_run=True)

        args = mock_run.call_args[0][0]
        self.assertIn("--dry-run", args)

    @patch("sbc_config.modules.iot.pi_sync.subprocess.run")
    def test_excludes_present(self, mock_run: MagicMock) -> None:
        mock_run.return_value = self._make_completed()
        with tempfile.TemporaryDirectory() as td:
            sync_repo("u@h", repo_root=Path(td))

        args = mock_run.call_args[0][0]
        self.assertIn("--exclude", args)
        self.assertIn(".venv", args)
        self.assertIn(".git", args)
        self.assertIn(".cache/", args)

    def test_sync_repo_raises_without_ssh_target(self) -> None:
        env_without_ssh = {k: v for k, v in os.environ.items() if k != "SBC_IOT_PI_SSH"}
        with patch.dict("os.environ", env_without_ssh, clear=True):
            with self.assertRaises(ValueError):
                sync_repo(None)


if __name__ == "__main__":
    unittest.main()
