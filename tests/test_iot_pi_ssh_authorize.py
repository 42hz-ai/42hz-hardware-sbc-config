"""Tests for SSH public-key bootstrap on the Pi."""

from __future__ import annotations

import subprocess
import tempfile
import unittest

from pathlib import Path
from unittest.mock import MagicMock, patch

from sbc_config.modules.iot.pi_ssh_authorize import (
    authorize_pi_ssh,
    dry_run_commands,
    resolve_public_key_path,
)


class TestResolvePublicKey(unittest.TestCase):
    def test_explicit_path(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pub", delete=False) as f:
            f.write(b"ssh-ed25519 AAAAC3 test@test\n")
            name = Path(f.name)
        try:
            self.assertEqual(resolve_public_key_path(name), name.expanduser())
        finally:
            name.unlink()


class TestDryRun(unittest.TestCase):
    def test_ssh_copy_id_line_when_binary_present(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pub", delete=False) as f:
            f.write(b"ssh-rsa AAAAB pretend\n")
            pub = Path(f.name)
        try:

            def _which(_cmd: str) -> str | None:
                return "/usr/bin/ssh-copy-id"

            with patch(
                "sbc_config.modules.iot.pi_ssh_authorize.shutil.which",
                _which,
            ):
                lines = dry_run_commands(
                    ssh_target="u@pi",
                    pub_key=pub,
                    force_fallback=False,
                )
            self.assertTrue(any("ssh-copy-id" in ln for ln in lines))
        finally:
            pub.unlink()

    def test_fallback_when_no_ssh_copy_id(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pub", delete=False) as f:
            f.write(b"ssh-ed25519 AAAAC3Nx short\n")
            pub = Path(f.name)
        try:
            with patch(
                "sbc_config.modules.iot.pi_ssh_authorize.shutil.which",
                return_value=None,
            ):
                lines = dry_run_commands(
                    ssh_target="u@pi",
                    pub_key=pub,
                    force_fallback=False,
                )
            blob = "\n".join(lines)
            self.assertIn("base64", blob.lower())
        finally:
            pub.unlink()


class TestAuthorizePiSshMocks(unittest.TestCase):
    """Avoid real SSH; stub ``subprocess.run``."""

    @patch("sbc_config.modules.iot.pi_ssh_authorize.subprocess.run")
    def test_force_append_invokes_ssh(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ssh", "dummy"],
            returncode=0,
        )
        with tempfile.NamedTemporaryFile(suffix=".pub", delete=False) as f:
            f.write(b"ssh-ed25519 AAAAC3N za\n")
            pub = Path(f.name)
        try:
            _, proc = authorize_pi_ssh(
                "u@h",
                pub_key_path=pub,
                dry_run=False,
                force_append=True,
            )
            mock_run.assert_called_once()
            self.assertEqual(proc.returncode, 0)
            args_list = mock_run.call_args[0][0]
            self.assertEqual(args_list[0], "ssh")
            self.assertIn("-o", args_list)
            script = args_list[-1]
            self.assertIn("base64", script)
            self.assertIn("authorized_keys", script)
        finally:
            pub.unlink()
