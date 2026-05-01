"""Shared typing helpers for imaging modules (no CLI / Rich)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Literal

Notify = Callable[[Literal["info", "warn", "ok"], str], None]

# Yields a callable that advances the bar by n bytes/chunks.
ByteProgressContext = AbstractContextManager[Callable[[int], None]]
ByteProgressFactory = Callable[[str, int | None], ByteProgressContext]
