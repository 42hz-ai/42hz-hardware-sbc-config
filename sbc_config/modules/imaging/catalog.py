"""Discover namespaced release definitions under imaging/releases/."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pydantic import BaseModel, ConfigDict, field_validator

from sbc_config.modules.imaging.paths import repo_root


class ReleaseIndex(BaseModel):
    """imaging/releases/index.yaml — declares the default release key."""

    model_config = ConfigDict(str_strip_whitespace=True)

    default: str

    @field_validator("default", mode="before")
    @classmethod
    def _strip_default(cls, v: Any) -> Any:
        return v


def releases_dir() -> Path:
    return repo_root() / "imaging" / "releases"


def release_index_path() -> Path:
    return releases_dir() / "index.yaml"


def load_release_index(path: Path | None = None) -> ReleaseIndex:
    idx_path = path if path is not None else release_index_path()
    raw = yaml.safe_load(idx_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"Release index must be a mapping: {idx_path}"
        raise ValueError(msg)
    return ReleaseIndex.model_validate(raw)


def release_definition_path(slug: str) -> Path:
    """imaging/releases/<slug>.yaml (slug must be basename-safe)."""
    if slug != Path(slug).name or "/" in slug or slug in (".", ".."):
        msg = f"Invalid release key: {slug!r}"
        raise ValueError(msg)
    return releases_dir() / f"{slug}.yaml"


def resolve_release_yaml(
    *,
    release: str | None,
    release_file: Path | None,
) -> Path:
    """
    Return the YAML path for a pin: explicit file, or imaging/releases/<key>.yaml.

    When `release` is None, uses `default` from imaging/releases/index.yaml.
    """
    if release is not None and release_file is not None:
        msg = "Pass at most one of --release and --release-file."
        raise ValueError(msg)
    if release_file is not None:
        return release_file
    index = load_release_index()
    slug = release if release is not None else index.default
    path = release_definition_path(slug)
    if not path.is_file():
        msg = (
            f"Release {slug!r} has no definition at {path}. "
            f"Add that file under imaging/releases/ or fix default in index.yaml."
        )
        raise FileNotFoundError(msg)
    return path


def list_release_slugs() -> list[str]:
    """Basenames under imaging/releases/*.yaml excluding index.yaml."""
    root = releases_dir()
    if not root.is_dir():
        return []
    names: list[str] = []
    for p in sorted(root.glob("*.yaml")):
        if p.name == "index.yaml":
            continue
        names.append(p.stem)
    return names
