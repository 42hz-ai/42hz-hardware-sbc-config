"""Root CLI — Click command groups; logic lives in sbc_config/modules/."""

from __future__ import annotations

import click

from rich.console import Console

from sbc_config.commands.hello import hello_group


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """SBC Config — hardware domain"""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["console"] = Console()


cli.add_command(hello_group)


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
