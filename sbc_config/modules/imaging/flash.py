"""Flash helper — build host `dd` command lines."""

from __future__ import annotations

from pathlib import Path


def dd_argv(image: Path, device: str) -> list[str]:
    """Arguments for `dd` suitable for subprocess (run as root on the host)."""
    return [
        "dd",
        f"if={image.resolve()}",
        f"of={device}",
        "bs=4M",
        "status=progress",
        "conv=fsync",
    ]


def dd_shell(image: Path, device: str) -> str:
    """Single shell-friendly line (for copy-paste)."""
    parts = dd_argv(image, device)
    return " ".join(parts)
