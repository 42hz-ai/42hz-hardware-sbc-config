#!/usr/bin/env python3
"""Configure Git globals for the devcontainer.

Standalone script: uses system Python and Docker-installed click/rich only — no
`uv run` or project package required (runs before `uv sync` / local venv).
"""

from __future__ import annotations

import subprocess

from dataclasses import dataclass

import click

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

DEFAULT_EMAIL = "timothy.sabat@gmail.com"
DEFAULT_NAME = "tsabat"

GIT_DEFAULTS: dict[str, str] = {
    "init.defaultBranch": "main",
    "core.editor": "vim",
    "diff.tool": "vimdiff",
    "merge.tool": "vimdiff",
    "difftool.prompt": "false",
    "merge.conflictstyle": "diff3",
    "alias.d": "difftool",
    "commit.verbose": "true",
    "commit.status": "true",
}


@dataclass
class GitUserInfo:
    email: str | None
    name: str | None

    @property
    def is_configured(self) -> bool:
        return bool(self.email) and bool(self.name)


def _git_config_get(key: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "config", "--global", key],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def _git_config_set(key: str, value: str) -> None:
    subprocess.run(["git", "config", "--global", key, value], check=True)


def get_user_info() -> GitUserInfo:
    return GitUserInfo(
        email=_git_config_get("user.email"),
        name=_git_config_get("user.name"),
    )


def set_user_info(*, email: str | None = None, name: str | None = None) -> None:
    if email:
        _git_config_set("user.email", email)
    if name:
        _git_config_set("user.name", name)


def apply_defaults(overrides: dict[str, str] | None = None) -> dict[str, str]:
    settings = {**GIT_DEFAULTS, **(overrides or {})}
    for key, value in settings.items():
        _git_config_set(key, value)
    return settings


def _interview_user_info(console: Console) -> None:
    info = get_user_info()

    if info.is_configured:
        console.print()
        console.print(
            Panel(
                f"[bold]Email:[/bold] {info.email}\n[bold]Name:[/bold]  {info.name}",
                title="Git identity already configured",
                border_style="green",
            )
        )
        return

    console.print()
    note = Text.assemble(
        ("Note: ", "bold"),
        "This is only required if you use Git from the command line.\n",
        "If you only use Git through a GUI client, you can skip this.",
    )
    console.print(Panel(note, border_style="yellow"))

    if not Confirm.ask("[green]Configure Git user info?[/green]", default=True):
        console.print("[dim]Skipping Git user configuration[/dim]")
        return

    email = info.email
    name = info.name

    if not email:
        email = Prompt.ask(
            "[green]Git email address[/green]",
            default=DEFAULT_EMAIL,
        )
    else:
        console.print(f"  Email already set: [cyan]{email}[/cyan]")

    if not name:
        name = Prompt.ask("[green]Git user name[/green]", default=DEFAULT_NAME)
    else:
        console.print(f"  Name already set:  [cyan]{name}[/cyan]")

    set_user_info(email=email, name=name)
    console.print("[bold green]User identity saved.[/bold green]")


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--defaults-only",
    is_flag=True,
    help="Skip user-info interview; apply tool defaults only",
)
def main(defaults_only: bool) -> None:
    """Configure Git globals (user info, editor, diff/merge tools)."""
    console = Console()

    console.print()
    console.print(
        Panel(
            "[bold]Git Configuration[/bold]\n"
            "Sets user identity, editor, diff/merge tools, and sane defaults.",
            border_style="blue",
        )
    )

    if not defaults_only:
        _interview_user_info(console)

    settings = apply_defaults()

    console.print()
    table = Table(title="Applied defaults", border_style="dim")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    for key, value in settings.items():
        table.add_row(key, value)
    console.print(table)

    console.print()
    console.print("[bold green]Git configuration complete.[/bold green]")


if __name__ == "__main__":
    main()
