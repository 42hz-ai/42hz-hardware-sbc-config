"""Greet command — CLI surface; logic lives in modules/."""

from __future__ import annotations

import click

from sbc_config.modules.hello.greeting import build_greeting
from sbc_config.utils import HEADER_STYLE


@click.command("greet")
@click.option("--name", "-n", default="world", help="Name to greet")
@click.pass_context
def greet_command(ctx: click.Context, name: str) -> None:
    """Print a greeting."""
    console = ctx.obj["console"]
    console.print(build_greeting(name), style=HEADER_STYLE)
