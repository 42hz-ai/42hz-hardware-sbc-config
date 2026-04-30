"""Hello command group."""

import click

from .greet import greet_command


@click.group("hello")
def hello_group() -> None:
    """Hello commands."""


hello_group.add_command(greet_command)

__all__ = ["hello_group"]
