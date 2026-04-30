from __future__ import annotations

import pathlib

from typing import Final, Self, Type

import yaml

from pydantic import BaseModel as PydanticBaseModel
from rich.console import Console
from rich.style import Style

HEADER_STYLE: Final[Style] = Style(color="green", bold=True)
COMMENT_STYLE: Final[Style] = Style(color="#4C535D", italic=True)
ERROR_STYLE: Final[Style] = Style(color="red", bold=True)

CONSOLE: Final[Console] = Console()


class BaseModel(PydanticBaseModel):
    def to_yaml(self: Self, path: pathlib.Path) -> None:
        """Export model to yaml file."""
        with open(path, "w", encoding="utf-8") as file:
            file.write(
                yaml.safe_dump(
                    self.model_dump(),
                    indent=2,
                    encoding="utf-8",
                    sort_keys=False,
                ).decode()
            )

    @classmethod
    def from_yaml(cls: Type[Self], path: pathlib.Path) -> Self:
        """Read model from yaml file."""
        with open(path, "r", encoding="utf-8") as file:
            return cls.model_validate(yaml.safe_load(file))

    model_config = {
        "str_strip_whitespace": True,
        "extra": "forbid",
        "validate_assignment": True,
        "populate_by_name": True,
        "validate_default": True,
    }
