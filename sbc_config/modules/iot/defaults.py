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

DEFAULT_GREENGRASS_TES_ROLE_ALIAS: str = "sbcc-iot-hello-gg-tes"
"""IoT role alias for Greengrass v2 token exchange (TES) with ``IotHelloStack``.

Must match the stack default unless CDK context ``greengrassTokenExchangeRoleAlias``
or ``createGreengrassTokenExchangeRole: false`` changes the story. CLI
``install-greengrass`` uses this when ``--tes-role-alias`` and
``SBC_IOT_GG_TES_ROLE_ALIAS`` are unset.
"""

# ---------------------------------------------------------------------------
# Laptop-side paths (PEM bundle + repo root)
# ---------------------------------------------------------------------------

BUNDLE_PARENT_RELATIVE: Path = Path("aws-iot-bundles")
"""Parent directory (cwd-relative) for per-Thing PEM folders."""

SYNC_DEFAULT_BUNDLE_RELATIVE: Path = BUNDLE_PARENT_RELATIVE / HELLO_WORLD_THING_NAME
"""Default Pi bundle path relative to cwd: ``aws-iot-bundles/hw-pi-001``.

``sync_bundle(..., bundle_dir=None)`` uses this. The CLI resolves
``$SBC_IOT_FETCH_OUT_DIR`` or ``aws-iot-bundles/<--thing-name>`` at runtime.
"""


def default_bundle_dir_for_thing(thing_name: str) -> Path:
    """Default PEM directory for ``fetch-credentials`` / ``install-greengrass``.

    Priority: ``$SBC_IOT_FETCH_OUT_DIR`` > ``aws-iot-bundles/<thing_name>``
    (relative to cwd unless the env path is absolute).

    On-Pi or legacy flows: set ``SBC_IOT_FETCH_OUT_DIR=/etc/aws-iot`` or pass
    ``--out-dir`` / ``--bundle-dir`` explicitly.
    """
    raw = os.environ.get(ENV_FETCH_OUT_DIR)
    if raw:
        return Path(raw).expanduser()
    return BUNDLE_PARENT_RELATIVE / thing_name


# ---------------------------------------------------------------------------
# Pi-side remote paths (rsync remote spec; tilde expanded on the Pi)
# ---------------------------------------------------------------------------

SYNC_DEFAULT_REMOTE_REPO: str = "~/sbc-config"
"""Default remote repo path on the Pi (SSH login user's home).

Passed to rsync as ``user@host:~/sbc-config`` — expanded on the Pi, not locally.
"""

SYNC_DEFAULT_REMOTE_BUNDLE: str = "~/iot-data"
"""Default remote bundle dir on the Pi (SSH user's home).

Aligns with the compose.yaml volume mount: ``~/iot-data → /data/aws-iot``.
Tilde is expanded on the Pi by rsync/SSH, not via the operator's ``$HOME``.
"""

SYNC_RSYNC_EXCLUDES: tuple[str, ...] = (
    ".venv",
    ".git",
    ".cache/",
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
"""Env var override for the default PEM directory on the operator machine.

When set, ``fetch-credentials``, ``install-greengrass``, ``sync-to-pi`` (with
no ``--bundle-dir``), and ``mqtt-test`` use this path instead of
``aws-iot-bundles/<thing-name>``. Use an absolute path such as ``/etc/aws-iot``
on a Pi, or one shared dir if you intentionally reuse PEMs across Things.
"""

ENV_GREENGRASS_ROOT: str = "SBCC_GREENGRASS_ROOT"
"""Default Greengrass Nucleus root when ``install-greengrass`` omits ``--greengrass-root``.

The SBCC devcontainer sets this under the repo bind mount (``.sbcc/greengrass/v2``)
so Docker Engine can bind-mount the IPC socket for ``telemetry-publisher-docker``.
On the Pi / bare Linux cores, omit the variable to keep ``/greengrass/v2``."""

ENV_IOT_DATA_DIR: str = "IOT_DATA_DIR"
"""Env var set by ``iot-runner`` compose: bind mount root for PEMs (typically
``/data/aws-iot`` inside the container). ``mqtt-test`` prefers this default.
"""

ENV_SSH_PUBLIC_KEY: str = "SBC_IOT_SSH_PUBLIC_KEY"
"""Env var for the SSH **public** key path (``.pub``).

Used by ``sbc iot add-pi-ssh-key`` when ``--public-key`` is omitted and the usual
default files are absent under ``~/.ssh/``.
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


def default_greengrass_install_root() -> Path:
    """Return the default Greengrass tree for ``install-greengrass``.

    Priority: ``$SBCC_GREENGRASS_ROOT`` (non-empty string) >
    ``/greengrass/v2``.

    Expanded with ``expanduser()`` so tilde resolves when operators set HOME-style
    paths.
    """
    raw = os.environ.get(ENV_GREENGRASS_ROOT, "").strip()
    return Path(raw).expanduser() if raw else Path("/greengrass/v2")


def default_mqtt_bundle_dir(thing_name: str | None = None) -> Path:
    """Default PEM directory for ``mqtt-test`` (read paths under ``--out-dir``).

    ``$IOT_DATA_DIR`` wins (set in ``infra/docker/iot-runner/compose.yaml`` for
    the bind mount at ``/data/aws-iot``). Then ``$SBC_IOT_FETCH_OUT_DIR``.
    Otherwise ``aws-iot-bundles/<thing_name>`` when *thing_name* is set, else
    ``default_fetch_out_dir()`` (``/etc/aws-iot`` when no env).
    """
    raw = os.environ.get(ENV_IOT_DATA_DIR)
    if raw:
        return Path(raw).expanduser()
    raw_fetch = os.environ.get(ENV_FETCH_OUT_DIR)
    if raw_fetch:
        return Path(raw_fetch).expanduser()
    if thing_name:
        return BUNDLE_PARENT_RELATIVE / thing_name
    return default_fetch_out_dir()


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
