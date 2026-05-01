"""Repository-relative paths for imaging workflows."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Directory containing `pyproject.toml` (checked out repository root)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    msg = "Could not find repository root (pyproject.toml)"
    raise RuntimeError(msg)


def default_cache_dir() -> Path:
    return repo_root() / ".cache" / "imaging"
