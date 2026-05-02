"""Pi sync helpers — rsync wrappers for the ``sbc iot sync-to-pi`` command.

Pushes the operator's repo checkout and the PEM bundle directory to a
Raspberry Pi (or any SSH-accessible Linux host) over rsync + SSH.
"""

from __future__ import annotations

import subprocess

from pathlib import Path

from sbc_config.modules.iot.defaults import (
    SYNC_DEFAULT_BUNDLE_RELATIVE,
    SYNC_DEFAULT_REMOTE_BUNDLE,
    SYNC_DEFAULT_REMOTE_REPO,
    SYNC_RSYNC_EXCLUDES,
    resolve_pi_ssh,
)

# Remote path on the Pi host (expanded at use time).
REMOTE_REPO_DEFAULT: str = SYNC_DEFAULT_REMOTE_REPO
REMOTE_BUNDLE_DEFAULT: str = SYNC_DEFAULT_REMOTE_BUNDLE


def _rsync(
    source: str,
    destination: str,
    *,
    excludes: tuple[str, ...] = SYNC_RSYNC_EXCLUDES,
    dry_run: bool = False,
    extra_args: tuple[str, ...] = (),
    inherit_stdio: bool = False,
) -> subprocess.CompletedProcess[bytes | None]:
    """Run ``rsync -az --delete`` from *source* to *destination*.

    ``rsync`` and ``ssh`` must be on the caller's PATH.

    Args:
        source: Local source path (trailing ``/`` for content-only sync).
        destination: Remote destination (``user@host:path`` or local path).
        excludes: Patterns passed via ``--exclude``.
        dry_run: When ``True`` adds ``--dry-run`` so no files are transferred.
        extra_args: Any additional rsync flags.
        inherit_stdio: When ``True``, rsync inherits stdout/stderr (live
            ``--progress`` / ``-v`` output). When ``False``, output is captured.

    Returns:
        ``subprocess.CompletedProcess`` (stdout/stderr captured unless
        *inherit_stdio*).

    Raises:
        subprocess.CalledProcessError: When rsync exits non-zero.
    """
    cmd: list[str] = ["rsync", "-az", "--delete"]
    for pat in excludes:
        cmd += ["--exclude", pat]
    if dry_run:
        cmd.append("--dry-run")
    cmd.extend(extra_args)
    cmd += [source, destination]
    if inherit_stdio:
        return subprocess.run(cmd, check=True)
    return subprocess.run(cmd, capture_output=True, check=True)


def sync_repo(
    ssh_target: str | None,
    *,
    repo_root: Path | None = None,
    remote_repo: str = REMOTE_REPO_DEFAULT,
    excludes: tuple[str, ...] = SYNC_RSYNC_EXCLUDES,
    dry_run: bool = False,
    extra_args: tuple[str, ...] = (),
    inherit_stdio: bool = False,
) -> subprocess.CompletedProcess[bytes | None]:
    """Rsync the local repo checkout to the Pi.

    Syncs ``repo_root/`` (trailing slash → contents only) to
    ``ssh_target:remote_repo``.  Falls back to ``$SBC_IOT_PI_SSH`` when
    *ssh_target* is ``None``.

    Args:
        ssh_target: SSH target, e.g. ``hz42@192.168.8.122``.  ``None`` reads
            ``$SBC_IOT_PI_SSH``.
        repo_root: Local repo root directory.  Defaults to ``Path.cwd()``.
        remote_repo: Destination path on the Pi.
        excludes: Extra exclude patterns (merged with defaults).
        dry_run: Pass through to rsync.
        extra_args: Extra rsync flags (``-v``, ``--info=progress2``, …).
        inherit_stdio: Stream rsync to the terminal (use with ``-v`` / progress).

    Returns:
        ``subprocess.CompletedProcess`` from rsync.
    """
    target = resolve_pi_ssh(ssh_target)
    root = (repo_root or Path.cwd()).resolve()
    source = str(root) + "/"  # trailing / → sync contents, not directory
    # Do not Path.expanduser() here — that uses the *operator* machine's $HOME
    # (e.g. /root in a devcontainer) and becomes user@pi:/root/sbc-config, which
    # the Pi login cannot write. Rsync passes "~/…" to the remote for the SSH user.
    dest = f"{target}:{remote_repo}"
    return _rsync(
        source,
        dest,
        excludes=excludes,
        dry_run=dry_run,
        extra_args=extra_args,
        inherit_stdio=inherit_stdio,
    )


def sync_bundle(
    ssh_target: str | None,
    *,
    bundle_dir: Path | None = None,
    remote_bundle: str = REMOTE_BUNDLE_DEFAULT,
    excludes: tuple[str, ...] = SYNC_RSYNC_EXCLUDES,
    dry_run: bool = False,
    extra_args: tuple[str, ...] = (),
    inherit_stdio: bool = False,
) -> subprocess.CompletedProcess[bytes | None]:
    """Rsync the local PEM bundle to the Pi.

    Syncs ``bundle_dir/`` (trailing slash → contents only) to
    ``ssh_target:remote_bundle``.  Falls back to ``$SBC_IOT_PI_SSH`` when
    *ssh_target* is ``None``.

    Args:
        ssh_target: SSH target.  ``None`` reads ``$SBC_IOT_PI_SSH``.
        bundle_dir: Local PEM bundle directory.  Defaults to
            ``SYNC_DEFAULT_BUNDLE_RELATIVE`` relative to ``Path.cwd()``.
        remote_bundle: Destination path on the Pi for the PEM bundle.
        excludes: Rsync exclude patterns.
        dry_run: Pass through to rsync.
        extra_args: Extra rsync flags.
        inherit_stdio: Stream rsync to the terminal.

    Returns:
        ``subprocess.CompletedProcess`` from rsync.
    """
    target = resolve_pi_ssh(ssh_target)
    local_base = (
        bundle_dir
        if bundle_dir is not None
        else Path.cwd() / SYNC_DEFAULT_BUNDLE_RELATIVE
    )
    local_bundle = local_base.resolve()
    source = str(local_bundle) + "/"
    dest = f"{target}:{remote_bundle}"
    return _rsync(
        source,
        dest,
        excludes=excludes,
        dry_run=dry_run,
        extra_args=extra_args,
        inherit_stdio=inherit_stdio,
    )
