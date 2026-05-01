"""Tests for ``pi_docker_install`` and ``install-pi-docker`` helpers."""

from __future__ import annotations

import subprocess
import unittest

from unittest.mock import patch

from click.testing import CliRunner
from rich.console import Console

from sbc_config.commands.iot.install_pi_docker import install_pi_docker_command
from sbc_config.modules.iot.pi_docker_install import (
    GET_DOCKER_SCRIPT_URL,
    classify_install_failure_stderr,
    dry_run_lines,
    effective_remote_user,
    parse_ssh_login_user,
    run_install_via_ssh,
)


class TestParseSshLoginUser(unittest.TestCase):
    def test_user_host(self) -> None:
        self.assertEqual(parse_ssh_login_user("hz42@192.168.8.122"), "hz42")

    def test_trimmed_parts(self) -> None:
        self.assertEqual(parse_ssh_login_user("  u@h  "), "u")

    def test_host_only(self) -> None:
        self.assertIsNone(parse_ssh_login_user("raspberrypi.local"))

    def test_missing_user_or_host(self) -> None:
        self.assertIsNone(parse_ssh_login_user("@nohost"))
        self.assertIsNone(parse_ssh_login_user("noat"))


class TestEffectiveRemoteUser(unittest.TestCase):
    def test_explicit_wins(self) -> None:
        self.assertEqual(
            effective_remote_user(ssh_target="any", remote_user="bob"),
            "bob",
        )

    def test_inferred(self) -> None:
        self.assertEqual(
            effective_remote_user(ssh_target="alice@pi", remote_user=None),
            "alice",
        )

    def test_host_only_requires_explicit(self) -> None:
        with self.assertRaises(ValueError, msg="Pass --remote-user"):
            effective_remote_user(ssh_target="myalias", remote_user=None)


class TestDryRunLines(unittest.TestCase):
    def test_contains_get_docker_and_quote(self) -> None:
        lines = dry_run_lines(
            ssh_target="u@192.168.1.50",
            login_user="u",
            add_docker_group=True,
            skip_verify=False,
        )
        blob = "\n".join(lines)
        self.assertIn(GET_DOCKER_SCRIPT_URL.rstrip("/"), blob)
        self.assertIn("get.docker.com", blob)
        self.assertIn("usermod -aG docker", blob)


class TestRunInstallViaSshDryRun(unittest.TestCase):
    def test_dry_run_no_subprocess_side_effects(self) -> None:
        lines, results = run_install_via_ssh(
            "u@h",
            dry_run=True,
            add_docker_group=True,
            skip_verify=False,
        )
        self.assertTrue(any("curl" in ln for ln in lines))
        self.assertEqual(results, [])


class TestInstallPiDockerCli(unittest.TestCase):
    def test_invoke_dry_run(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            install_pi_docker_command,
            ["--dry-run", "--ssh", "tester@pi.local"],
            obj={"console": Console()},
            catch_exceptions=False,
        )
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("get.docker.com", result.output)


class TestRunInstallMocks(unittest.TestCase):
    """Happy path through install with mocked ``curl`` and ``ssh``."""

    def test_full_run_stubbed_ok(self) -> None:
        def fake_run(
            cmd: list[str],
            **kwargs: object,
        ) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        with patch(
            "sbc_config.modules.iot.pi_docker_install.subprocess.run",
            side_effect=fake_run,
        ):
            lines, results = run_install_via_ssh(
                "u@h",
                dry_run=False,
                add_docker_group=True,
                skip_verify=True,
            )
        self.assertEqual(lines, [])
        self.assertEqual(len(results), 3)


class TestClassifyInstallFailure(unittest.TestCase):
    def test_ssh_permission_denied_publickey(self) -> None:
        self.assertEqual(
            classify_install_failure_stderr(
                b"hz42@192.168.8.122: Permission denied (publickey,password).\r\n",
                None,
            ),
            "ssh_auth",
        )

    def test_ssh_auth_from_stdout(self) -> None:
        self.assertEqual(
            classify_install_failure_stderr(
                None,
                b"Permission denied (publickey).\r\n",
            ),
            "ssh_auth",
        )

    def test_unknown(self) -> None:
        self.assertIsNone(
            classify_install_failure_stderr(b"dpkg failed", None),
        )

    def test_host_not_known(self) -> None:
        self.assertEqual(
            classify_install_failure_stderr(
                b"Could not resolve hostname pi.local\r\n",
                None,
            ),
            "ssh_host",
        )


if __name__ == "__main__":
    unittest.main()
