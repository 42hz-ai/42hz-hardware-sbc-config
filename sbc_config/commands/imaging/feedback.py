"""Rich-backed hooks for imaging commands (CLI layer only)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Literal

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TransferSpeedColumn,
)

from sbc_config.modules.imaging.types import ByteProgressFactory, Notify


def notify_for_console(console: Console) -> Notify:
    """Map semantic levels to Rich styles (used by imaging modules)."""

    def _emit(level: Literal["info", "warn", "ok"], message: str) -> None:
        style = {"info": "cyan", "warn": "yellow", "ok": "green"}[level]
        console.print(f"[{style}]{message}[/{style}]")

    return _emit


def byte_progress_for_console(console: Console) -> ByteProgressFactory:
    """Build a byte-progress context manager wired to Rich."""

    @contextmanager
    def _factory(label: str, total: int | None):
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task(label, total=total)

            def advance(n: int) -> None:
                progress.update(task_id, advance=n)

            yield advance

    return _factory
