"""Hello-world IoT spike defaults.

Constants and environment-variable keys shared by the ``sbc iot`` CLI
commands for the ``IotHelloStack`` hello-world flow (SBCC-INFRA-0001).

IMPORTANT: This module is CLI + test only.  The CDK custom-resource Lambda
(``infra/cdk/lambda/provision_device/``) must NOT import it — the Lambda
asset is built from stdlib + boto3 only.
"""

from __future__ import annotations

import os

from pathlib import Path

from sbc_config.modules.iot.credentials import DEFAULT_OUT_DIR as _DEFAULT_OUT_DIR

# ---------------------------------------------------------------------------
# Thing / stack defaults
# ---------------------------------------------------------------------------

HELLO_WORLD_THING_NAME: str = "hw-pi-001"
"""Default IoT Thing name matching ``IotHelloStack`` / INFRA-0001."""

# ---------------------------------------------------------------------------
# Laptop-side paths (PEM bundle + repo root)
# ---------------------------------------------------------------------------

SYNC_DEFAULT_BUNDLE_RELATIVE: Path = Path("aws-iot-bundle")
"""Bundle directory relative to cwd on the operator laptop.

Both ``fetch-credentials --out-dir`` and ``sync-to-pi --bundle-dir``
default to this so they stay aligned without extra flags.
"""

# ---------------------------------------------------------------------------
# Pi-side remote paths (expanduser at use time)
# ---------------------------------------------------------------------------

SYNC_DEFAULT_REMOTE_REPO: str = "~/sbc-config"
"""Default remote repo path on the Pi host (expand with Path.expanduser)."""

SYNC_DEFAULT_REMOTE_BUNDLE: str = "~/iot-data"
"""Default remote bundle dir on the Pi host (expand with Path.expanduser).

Aligns with the compose.yaml volume mount: ``~/iot-data → /data/aws-iot``.
"""

SYNC_RSYNC_EXCLUDES: tuple[str, ...] = (
    ".venv",
    ".git",
    "infra/cdk/cdk.out",
    "__pycache__",
    "*.pyc",
)
"""Rsync exclude patterns applied by ``sync-to-pi`` to both repo + bundle."""

# ---------------------------------------------------------------------------
# Environment variable keys
# ---------------------------------------------------------------------------

ENV_PI_SSH: str = "SBC_IOT_PI_SSH"
"""Env var for the SSH target (e.g. ``hz42@192.168.8.122``).

When ``sync-to-pi --ssh`` is omitted, this variable is consulted.
Missing without ``--ssh`` → error that names this key.
"""

ENV_FETCH_OUT_DIR: str = "SBC_IOT_FETCH_OUT_DIR"
"""Env var for the ``fetch-credentials`` output directory.

When set, used as the default ``--out-dir`` value on the operator laptop,
overriding the system default (``/etc/aws-iot``) without requiring an
explicit flag.  Set to ``aws-iot-bundle`` in a dev shell profile to keep
credentials out of ``/etc``.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def default_fetch_out_dir() -> Path:
    """Return the effective default ``--out-dir`` for ``fetch-credentials``.

    Priority: ``$SBC_IOT_FETCH_OUT_DIR`` > ``DEFAULT_OUT_DIR`` (/etc/aws-iot).
    The ``/etc/aws-iot`` fallback keeps backward compat with on-Pi sudo flows
    documented in INFRA-0001.
    """
    raw = os.environ.get(ENV_FETCH_OUT_DIR)
    return Path(raw).expanduser() if raw else _DEFAULT_OUT_DIR


def resolve_pi_ssh(explicit: str | None) -> str:
    """Return the SSH target, preferring the explicit CLI arg then the env var.

    Raises ``ValueError`` with a helpful message when neither is provided.
    """
    if explicit:
        return explicit
    from_env = os.environ.get(ENV_PI_SSH)
    if from_env:
        return from_env
    msg = (
        f"--ssh is required when ${ENV_PI_SSH} is not set. "
        f"Example: export {ENV_PI_SSH}=hz42@192.168.8.122"
    )
    raise ValueError(msg)
