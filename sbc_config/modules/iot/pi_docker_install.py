"""Install Docker Engine (+ Compose v2 plugin) on a Pi over SSH.

Uses Docker's official convenience script at https://get.docker.com/ streamed
from the operator machine into ``sudo sh`` on the remote host, then optional
post-steps (``usermod``, verify, compose-plugin fallback).

The CDK Lambda must not import this module (SSH / operator-only).
"""

from __future__ import annotations

import shlex
import subprocess

GET_DOCKER_SCRIPT_URL: str = "https://get.docker.com/"

SSH_BASE: list[str] = ["ssh", "-o", "BatchMode=yes"]


def parse_ssh_login_user(ssh_target: str) -> str | None:
    """Return the login name if *ssh_target* is ``user@host``; else ``None``.

    Host-only targets (e.g. ``Host`` from ``~/.ssh/config``) yield ``None`` —
    callers must pass an explicit remote user.

    Uses a single ``@`` split (RFC: login name cannot contain ``@``).
    """
    if "@" not in ssh_target or ssh_target.startswith("@"):
        return None
    user, _sep, host = ssh_target.partition("@")
    if not user.strip() or not host.strip():
        return None
    return user.strip()


def effective_remote_user(*, ssh_target: str, remote_user: str | None) -> str:
    """Resolve the Pi account to add to the ``docker`` group."""
    if remote_user:
        return remote_user
    parsed = parse_ssh_login_user(ssh_target)
    if parsed:
        return parsed
    msg = (
        "Could not infer the Pi login user from the SSH target "
        f"{ssh_target!r} (no user@host form). Pass --remote-user."
    )
    raise ValueError(msg)


def dry_run_lines(
    *,
    ssh_target: str,
    login_user: str,
    add_docker_group: bool,
    skip_verify: bool,
) -> list[str]:
    """Human-readable summary of what ``run_install_via_ssh`` would do."""
    lines: list[str] = [
        "[dry-run] Would run:",
        f"  curl -fsSL {GET_DOCKER_SCRIPT_URL} \\",
        f'    | ssh -o BatchMode=yes {shlex.quote(ssh_target)} "sudo sh"',
        "  (streams Docker's convenience installer to the Pi — trust model: curl|sh)",
        "  Ref: https://get.docker.com/",
    ]
    lines.append("  ssh … 'sudo systemctl enable --now docker'  (idempotent)")
    if add_docker_group:
        quser = shlex.quote(login_user)
        lines.append(f"  ssh … 'sudo usermod -aG docker {quser}'")
    lines.append(
        "  On failure: optionally `sudo apt-get install -y docker-compose-plugin`."
    )
    if not skip_verify:
        lines += [
            "[dry-run] Then verify (unless --skip-verify):",
            "  ssh … sudo docker version",
            "  ssh … sudo docker compose version",
            "  ssh … sudo docker run --rm hello-world",
        ]
    return lines


def _ssh(
    ssh_target: str,
    remote_cmd: list[str],
    *,
    stdin: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [*SSH_BASE, ssh_target, *remote_cmd],
        input=stdin,
        capture_output=True,
        check=False,
    )


def run_install_via_ssh(
    ssh_target: str,
    *,
    remote_user: str | None = None,
    dry_run: bool = False,
    add_docker_group: bool = True,
    skip_verify: bool = False,
) -> tuple[list[str], list[subprocess.CompletedProcess[bytes]]]:
    """Run Docker install on *ssh_target*; return dry-run lines or post results.

    Raises:
        subprocess.CalledProcessError: When a remote step fails.
        ValueError: When *remote_user* cannot be determined.
    """
    login = effective_remote_user(ssh_target=ssh_target, remote_user=remote_user)

    if dry_run:
        return dry_run_lines(
            ssh_target=ssh_target,
            login_user=login,
            add_docker_group=add_docker_group,
            skip_verify=skip_verify,
        ), []

    curl = subprocess.run(
        ["curl", "-fsSL", GET_DOCKER_SCRIPT_URL],
        capture_output=True,
        check=True,
    )
    results: list[subprocess.CompletedProcess[bytes]] = []

    inst = _ssh(ssh_target, ["sudo", "sh"], stdin=curl.stdout)
    results.append(inst)
    if inst.returncode != 0:
        raise subprocess.CalledProcessError(
            inst.returncode,
            inst.args,
            output=inst.stdout,
            stderr=inst.stderr,
        )

    # Idempotent: ensure daemon after script.
    en = _ssh(ssh_target, ["sudo", "systemctl", "enable", "--now", "docker"])
    results.append(en)
    if en.returncode != 0:
        raise subprocess.CalledProcessError(
            en.returncode, en.args, en.stdout, en.stderr
        )

    if add_docker_group:
        ug = _ssh(ssh_target, ["sudo", "usermod", "-aG", "docker", login])
        results.append(ug)
        if ug.returncode != 0:
            raise subprocess.CalledProcessError(
                ug.returncode, ug.args, ug.stdout, ug.stderr
            )

    if skip_verify:
        return [], results

    dv = _ssh(ssh_target, ["sudo", "docker", "version"])
    results.append(dv)
    if dv.returncode != 0:
        raise subprocess.CalledProcessError(
            dv.returncode, dv.args, dv.stdout, dv.stderr
        )

    cv = _ssh(ssh_target, ["sudo", "docker", "compose", "version"])
    results.append(cv)
    if cv.returncode != 0:
        apt_u = _ssh(
            ssh_target,
            [
                "sudo",
                "sh",
                "-c",
                "apt-get update && apt-get install -y docker-compose-plugin",
            ],
        )
        results.append(apt_u)
        if apt_u.returncode != 0:
            raise subprocess.CalledProcessError(
                apt_u.returncode, apt_u.args, apt_u.stdout, apt_u.stderr
            )
        cv2 = _ssh(ssh_target, ["sudo", "docker", "compose", "version"])
        results.append(cv2)
        if cv2.returncode != 0:
            raise subprocess.CalledProcessError(
                cv2.returncode, cv2.args, cv2.stdout, cv2.stderr
            )

    hw = _ssh(ssh_target, ["sudo", "docker", "run", "--rm", "hello-world"])
    results.append(hw)
    if hw.returncode != 0:
        raise subprocess.CalledProcessError(
            hw.returncode, hw.args, hw.stdout, hw.stderr
        )

    return [], results
