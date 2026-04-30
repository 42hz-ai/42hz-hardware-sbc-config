"""Pinned Raspberry Pi OS release metadata (YAML under imaging/)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


class PinnedRelease(BaseModel):
    """Fields from `imaging/pinned_release.yaml`."""

    model_config = ConfigDict(str_strip_whitespace=True)

    image_url: HttpUrl
    sha256_url: HttpUrl
    artifact_basename: str | None = None

    @field_validator("image_url", "sha256_url", mode="before")
    @classmethod
    def _coerce_url(cls, v: Any) -> Any:
        return v

    def xz_filename(self) -> str:
        if self.artifact_basename:
            return self.artifact_basename
        path = str(self.image_url.path).rstrip("/")
        return path.rsplit("/", maxsplit=1)[-1]


def load_pinned_release(path: Path) -> PinnedRelease:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"Release file must be a mapping: {path}"
        raise ValueError(msg)
    return PinnedRelease.model_validate(raw)
