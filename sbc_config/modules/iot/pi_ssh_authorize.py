"""Append the operator's SSH public key to a Pi user's ``authorized_keys``.

Bootstrap flow: prefers ``ssh-copy-id`` (handles ``.ssh`` perms correctly). Falls
back to ``ssh`` + ``base64``-decoded line injection so stdin is left to OpenSSH
for password/passphrase prompts (no piped pubkey on stdin).

Lambda / CDK must not import this module.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess

from pathlib import Path

from sbc_config.modules.iot.defaults import ENV_SSH_PUBLIC_KEY

_FALLBACK_PUBLICS: tuple[str, ...] = (
    "id_ed25519.pub",
    "id_ecdsa.pub",
    "id_rsa.pub",
)


def default_public_key_path() -> Path | None:
    """First existing ``~/.ssh/*.pub`` from a fixed preference order."""
    dot_ssh = Path.home() / ".ssh"
    for name in _FALLBACK_PUBLICS:
        candidate = dot_ssh / name
        if candidate.is_file():
            return candidate
    return None


def resolve_public_key_path(explicit: Path | None) -> Path:
    """Return *explicit*, else ``$SBC_IOT_SSH_PUBLIC_KEY``, else detected default."""
    if explicit:
        p = explicit.expanduser()
        if not p.is_file():
            msg = f"SSH public key file not found: {p}"
            raise FileNotFoundError(msg)
        return p
    raw = os.environ.get(ENV_SSH_PUBLIC_KEY)
    if raw:
        p = Path(raw).expanduser()
        if not p.is_file():
            msg = f"${ENV_SSH_PUBLIC_KEY} file not found: {p}"
            raise FileNotFoundError(msg)
        return p
    found = default_public_key_path()
    if found:
        return found
    msg = (
        "Could not find a default public key (tried ~/.ssh/id_ed25519.pub, "
        "id_ecdsa.pub, id_rsa.pub). Pass --public-key or set "
        f"${ENV_SSH_PUBLIC_KEY}."
    )
    raise FileNotFoundError(msg)


def dry_run_commands(
    *,
    ssh_target: str,
    pub_key: Path,
    force_fallback: bool,
) -> list[str]:
    """Lines printed for ``--dry-run``."""
    use_copy_id = bool(shutil.which("ssh-copy-id")) and not force_fallback
    if use_copy_id:
        return [
            "[dry-run] Would run:",
            f"  ssh-copy-id -i {pub_key} {ssh_target}",
            "  (password / interactive prompts attach to your terminal)",
        ]
    text = pub_key.read_text(encoding="utf-8").strip()
    line = text.split("\n", maxsplit=1)[0].strip()
    snippet = line[:72] + ("…" if len(line) > 72 else "")
    return [
        "[dry-run] ssh-copy-id not on PATH (--force-append); would run:",
        "  ssh (interactive; password auth allowed)",
        "  remote: decode base64 line → grep -Fq in authorized_keys or append",
        f"  key (preview): {snippet}",
    ]


def append_via_ssh_shell(
    ssh_target: str, pub_key: Path
) -> subprocess.CompletedProcess[bytes]:
    """Append one pubkey line via ``ssh`` **without consuming stdin from a pipe.**

    Leaves stdio inheritance for OpenSSH prompts; key is transported as ASCII
    base64 in the remote shell snippet.
    """
    line = (
        pub_key.read_text(encoding="utf-8").strip().split("\n", maxsplit=1)[0].strip()
    )
    payload = base64.b64encode(line.encode("utf-8")).decode("ascii")
    # shell: LINE=$(echo "$b64" | base64 -d); … (base64 alphabet is POSIX-safe in double quotes)
    remote_snippet = (
        f'LINE=$(printf "%s" "$(echo "{payload}" | base64 -d)") && '
        'mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh" '
        '&& touch "$HOME/.ssh/authorized_keys" && chmod 600 "$HOME/.ssh/authorized_keys" '
        '&& { grep -Fxq -- "$LINE" "$HOME/.ssh/authorized_keys" '
        '|| printf "%s\\n" "$LINE" >> "$HOME/.ssh/authorized_keys"; }'
    )
    # Inherit stdin/stdout/stderr so password/passphrase prompts work.
    return subprocess.run(
        ["ssh", "-o", "BatchMode=no", ssh_target, "sh", "-c", remote_snippet],
        check=False,
    )


def authorize_pi_ssh(
    ssh_target: str,
    *,
    pub_key_path: Path,
    dry_run: bool = False,
    force_append: bool = False,
) -> tuple[list[str] | None, subprocess.CompletedProcess | None]:
    """Append ``pub_key_path`` on *ssh_target*.

    When ``dry_run``, returns printable lines instead of contacting the Pi.

    For real runs:

    * If ``ssh-copy-id`` exists and *force_append* is false — run it attached to
      the parent's stdio (**password prompts work**).

    * Otherwise — use :func:`append_via_ssh_shell` (**stdio inherited**).

    Returns:
        Dry-run lines, or ``(None, CompletedProcess)`` (*returncode* is set;
        stderr/stdout only when captured by tests mocking ``run``).

    Raises:
        FileNotFoundError: If public key missing (from :func:`resolve_public_key_path`).
    """
    pub = pub_key_path.expanduser().resolve()

    prefer_copy_id = shutil.which("ssh-copy-id") and not force_append

    if dry_run:
        return dry_run_commands(
            ssh_target=ssh_target,
            pub_key=pub,
            force_fallback=force_append,
        ), None

    if prefer_copy_id:
        proc = subprocess.run(
            ["ssh-copy-id", "-i", str(pub), ssh_target],
            check=False,
        )
        return None, proc

    proc = append_via_ssh_shell(ssh_target, pub)
    return None, proc
