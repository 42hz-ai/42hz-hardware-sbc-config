---
name: cli-structure
description: >-
  Well-structured CLIs for this repo — Click command groups under sbc_config/commands/
  mirrored by sbc_config/modules/. Use when adding commands, reorganizing the CLI, or
  when the user mentions CLI structure, command groups, or mirrored modules.
---

# CLI structure (sbc_config)

## Core Principle

**The `modules/` directory structure must mirror the `commands/` directory structure.** Each command group has a corresponding module group, maintaining the same hierarchy.

**Copier-generated layout:** The Python package is `sbc_config/` at the repository root (alongside `pyproject.toml`). The entry file is `sbc_config/cli.py` with console script `sbc` → `sbc_config.cli:main`.

## Package layout

**All commands and modules live under `sbc_config/`.** Entry point is `sbc_config/cli.py` using absolute imports (`from sbc_config.commands...`, `from sbc_config.modules...`).

## Project Structure

```
project_name/
├── cli.py                 # Main entry point (at root)
├── project/              # Package directory
│   ├── __init__.py
│   ├── commands/        # Command implementations
│   │   ├── __init__.py
│   │   ├── group1/
│   │   │   ├── __init__.py
│   │   │   └── command1.py
│   │   └── group2/
│   │       ├── __init__.py
│   │       └── command2.py
│   └── modules/        # Reusable business logic (mirrors command structure)
│       ├── __init__.py
│       ├── group1/       # Matches sbc_config/commands/group1/
│       │   ├── __init__.py
│       │   └── submodule/
│       │       ├── __init__.py
│       │       └── module1.py
│       └── group2/      # Matches sbc_config/commands/group2/
│           ├── __init__.py
│           └── submodule/
│               ├── __init__.py
│               └── module2.py
└── pyproject.toml
```

**Note:** The `project/` directory serves as the Python package. Ensure `pyproject.toml` includes `packages = ["sbc_config"]` in `[tool.hatch.build.targets.wheel]`.

**Structure Mapping:**

```
sbc_config/commands/hospitals/christus/backfill.py
    ↓ maps to ↓
sbc_config/modules/hospitals/christus/backfill.py

sbc_config/commands/hospitals/christus/validation/validate.py
    ↓ maps to ↓
sbc_config/modules/hospitals/christus/validation/validate.py
```

## Dependencies

**Required:**

- `click>=8.2.1` - CLI framework
- `rich>=13.7.0` - Terminal output formatting

**Recommended:**

- `pydantic` - Data validation
- `python-dotenv` - Environment variables

## Implementation Patterns

### 1. Main CLI Entry Point (`cli.py`)

**When `cli.py` is at root level (recommended):**

```python
#!/usr/bin/env python3
"""Project CLI - Command-line interface."""

import click
from rich.console import Console

from sbc_config.commands.group1 import group1_command
from sbc_config.commands.group2 import group2_command

console = Console()


@click.group()
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.option("--config-file", type=click.Path(exists=True), help="Config file path")
@click.pass_context
def cli(ctx, verbose, config_file):
    """Project CLI - [Brief description]."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config"] = load_config(config_file) if config_file else {}
    ctx.obj["service"] = ServiceClient(ctx.obj["config"])


# Register command groups
cli.add_command(group1_command)
cli.add_command(group2_command)


if __name__ == "__main__":
    cli(obj={})
```

**When `cli.py` is inside `project/` directory:**

```python
#!/usr/bin/env python3
"""Project CLI - Command-line interface."""

import click
from rich.console import Console

from .commands.group1 import group1_command
from .commands.group2 import group2_command

console = Console()


@click.group()
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.option("--config-file", type=click.Path(exists=True), help="Config file path")
@click.pass_context
def cli(ctx, verbose, config_file):
    """Project CLI - [Brief description]."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config"] = load_config(config_file) if config_file else {}
    ctx.obj["service"] = ServiceClient(ctx.obj["config"])


# Register command groups
cli.add_command(group1_command)
cli.add_command(group2_command)


if __name__ == "__main__":
    cli(obj={})
```

### 2. Command Group (`sbc_config/commands/group1/__init__.py`)

```python
#!/usr/bin/env python3
"""Group1 Commands - [Description]."""

import click

from . import command1, command2


@click.group("group1")
def group1_command():
    """Group1 commands - [Brief description]."""
    pass


# Register all subcommands
group1_command.add_command(command1.command1_func)
group1_command.add_command(command2.command2_func)
```

### 3. Individual Command (`sbc_config/commands/group1/command1.py`)

```python
#!/usr/bin/env python3
"""Command1 - [Description]."""

from typing import Optional
import click
from rich.console import Console
from rich.table import Table

from sbc_config.modules.group1 import ModuleClass1

console = Console()


@click.command("command1")
@click.option("--input", type=click.Path(exists=True), required=True, help="Input file path")
@click.option("--output", type=click.Path(), help="Output file path (optional)")
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
@click.pass_context
def command1_func(ctx, input: str, output: Optional[str], dry_run: bool):
    """Command1 - [Brief description]."""
    config = ctx.obj.get("config", {})
    verbose = ctx.obj.get("verbose", False)

    if verbose:
        console.print(f"[cyan]Processing:[/cyan] {input}")

    # Initialize module from corresponding module group
    module = ModuleClass1(config)

    try:
        result = module.process(input, output, dry_run=dry_run)

        # Display results using Rich
        table = Table(title="Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Status", "Success")
        table.add_row("Processed", str(result.count))
        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()
```

**Note:** If `cli.py` is also in `project/`, you can use relative imports: `from ...modules.group1 import ModuleClass1`

### 4. Module Group (`sbc_config/modules/group1/__init__.py`)

```python
"""Group1 Modules - Business logic for group1 commands."""

from .submodule import ModuleClass1, function1, function2

__all__ = ["ModuleClass1", "function1", "function2"]
```

### 5. Submodule (`sbc_config/modules/group1/submodule/__init__.py`)

```python
"""Submodule for Group1 - [Description]."""

from .module1 import ModuleClass1, function1
from .module2 import function2

__all__ = ["ModuleClass1", "function1", "function2"]
```

### 6. Individual Module (`sbc_config/modules/group1/submodule/module1.py`)

```python
"""Module1 - Business logic for [specific functionality]."""

from typing import Optional
from pathlib import Path


class ModuleClass1:
    """Class for processing data."""

    def __init__(self, config: dict):
        """Initialize with configuration."""
        self.config = config

    def process(self, input_path: str, output_path: Optional[str] = None, dry_run: bool = False):
        """Process input file."""
        # Business logic here
        pass


def function1(param: str) -> str:
    """Process parameter and return result."""
    # Function logic here
    return result
```

## Click Patterns

### Context Passing

```python
@click.pass_context
def command(ctx, ...):
    config = ctx.obj.get("config")
    service = ctx.obj.get("service")
```

### Options

```python
@click.option("--name", type=str, required=True, help="Name of the resource")
@click.option("--count", type=int, default=10, help="Number of items (default: 10)")
@click.option("--force", is_flag=True, help="Force operation without confirmation")
```

### Path Options

```python
@click.option(
    "--input-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    required=True,
    help="Input file path"
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path.cwd(),
    help="Output directory"
)
```

### Error Handling

```python
try:
    result = service.process()
except ValueError as e:
    console.print(f"[red]Error:[/red] {e}")
    raise click.Abort()
```

### Rich Output

```python
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

# Styled text
console.print("[green]Success![/green]")
console.print("[red]Error:[/red] Something went wrong")

# Tables
table = Table(title="Results")
table.add_column("Name", style="cyan")
table.add_column("Value", style="green")
table.add_row("Item 1", "100")
console.print(table)

# Progress bars
with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    console=console,
) as progress:
    task = progress.add_task("Processing...", total=None)
    # Do work
    progress.update(task, completed=True)
```

## Import Patterns

Commands import from their corresponding module group:

**When `cli.py` is at root (absolute imports):**

```python
# In sbc_config/commands/group1/command1.py
from sbc_config.modules.group1 import ModuleClass1, function1

# Or import from specific submodule
from sbc_config.modules.group1.submodule import ModuleClass1
```

**When `cli.py` is in `project/` (relative imports):**

```python
# In sbc_config/commands/group1/command1.py
from ...modules.group1 import ModuleClass1, function1

# Or import from specific submodule
from ...modules.group1.submodule import ModuleClass1
```

## Configuration (`pyproject.toml`)

```toml
[project]
name = "sbc-config"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "click>=8.2.1",
    "rich>=13.7.0",
    "pydantic>=2.6.0",
    "python-dotenv>=1.0.0",
]

[project.scripts]
# If cli.py is at root:
sbc-config = "cli:cli"
# OR if cli.py is in project/:
# sbc-config = "project.cli:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["sbc_config"]  # Important: specify the package directory
```

## Key Principles

1. **Separation of Concerns**: Commands handle CLI interaction, modules handle business logic
2. **Structure Mirroring**: Module structure must mirror command structure (`sbc_config/commands/group1/` → `sbc_config/modules/group1/`)
3. **Context Sharing**: Use `ctx.obj` for shared state (config, clients, etc.)
4. **Rich Output**: Always use Rich for user-facing output (never plain print)
5. **Error Handling**: Use `click.Abort()` for user-facing errors
6. **Type Hints**: Use type hints throughout
7. **Documentation**: Include docstrings for all commands and modules
8. **Modularity**: Organize commands into logical groups with matching module groups
9. **Testability**: Keep commands thin, delegate to modules
10. **Module Registration**: Use `__init__.py` files to register and export submodules

## Common Patterns

### Optional Imports

**When `cli.py` is at root:**

```python
try:
    from sbc_config.commands.optional import optional_group
except ImportError:
    optional_group = None

if optional_group:
    cli.add_command(optional_group)
```

**When `cli.py` is in `project/`:**

```python
try:
    from .commands.optional import optional_group
except ImportError:
    optional_group = None

if optional_group:
    cli.add_command(optional_group)
```

### Configuration Management

```python
import os
from pathlib import Path
from dotenv import load_dotenv

def load_config(config_file=None):
    """Load configuration from file and environment."""
    config = {}

    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file)

    if config_file:
        # Load config file logic
        pass

    config.update({
        "key": os.getenv("KEY", config.get("key", "default"))
    })

    return config
```

### Shared Service Initialization

```python
@click.group()
@click.pass_context
def cli(ctx):
    ctx.ensure_object(dict)
    config = ctx.obj.get("config", {})
    ctx.obj["database"] = DatabaseClient(config)
    ctx.obj["api"] = APIClient(config)
```

## Module Registration Pattern

1. **Group-level `__init__.py`** (`sbc_config/modules/group1/__init__.py`):

   - Import from submodules
   - Export public API via `__all__`

2. **Submodule-level `__init__.py`** (`sbc_config/modules/group1/submodule/__init__.py`):

   - Import from individual module files
   - Export public API via `__all__`

3. **Individual module files** (`sbc_config/modules/group1/submodule/module1.py`):
   - Contain actual implementation
   - No registration needed (handled by parent `__init__.py`)

## Module Organization and Shared Code

When module files grow large or contain multiple responsibilities, break them up to mirror the command structure. Use `shared.py` (or similar) for common functionality used across multiple commands in the same group.

### Breaking Up Large Modules

**Principle:** Each command should have a corresponding module file. If a single module file handles multiple commands, split it into separate files that mirror the command structure.

**Example Structure:**

```
sbc_config/modules/group1/
├── __init__.py          # Exports all public APIs
├── shared.py            # Common classes/functions used by multiple commands
├── command1.py          # Logic for command1 (mirrors commands/group1/command1.py)
├── command2.py          # Logic for command2 (mirrors commands/group1/command2.py)
└── command3.py          # Logic for command3 (mirrors commands/group1/command3.py)
```

### Using `shared.py` for Common Functionality

**When to use `shared.py`:**

- Classes or functions used by multiple commands in the same group
- Connection management, client initialization, or shared state
- Common utilities specific to the module group
- Base classes or interfaces

**Example `shared.py`:**

```python
"""Shared Module - Common functionality for group1 operations."""

from typing import Optional
from pathlib import Path


class BaseClient:
    """Base client for group1 operations."""

    def __init__(self, config: dict):
        """Initialize with configuration."""
        self.config = config
        self.connection = None

    def connect(self, endpoint: str) -> None:
        """Connect to service endpoint."""
        # Connection logic here
        pass

    def close(self) -> None:
        """Close connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
```

**Example module file (`command1.py`):**

```python
"""Command1 Module - Business logic for command1."""

from .shared import BaseClient


def process_command1(config: dict, input_path: str) -> dict:
    """Process data for command1."""
    client = BaseClient(config)
    client.connect(config["endpoint"])
    try:
        # Command1-specific logic
        result = client.process(input_path)
        return result
    finally:
        client.close()
```

**Example `__init__.py` exports:**

```python
"""Group1 Modules - Business logic for group1 commands."""

from .shared import BaseClient
from .command1 import process_command1
from .command2 import process_command2
from .command3 import process_command3

__all__ = [
    "BaseClient",
    "process_command1",
    "process_command2",
    "process_command3",
]
```

### Benefits of This Organization

1. **Single Responsibility**: Each module file focuses on one command's logic
2. **Maintainability**: Changes to one command don't affect others
3. **Testability**: Easier to test individual command logic in isolation
4. **Clarity**: Clear mapping between commands and their implementations
5. **Shared Code**: Common functionality is centralized in `shared.py`

### Guidelines

- **Keep modules focused**: Each module file should handle one command's business logic
- **Use `shared.py` sparingly**: Only for code genuinely shared across multiple commands
- **Mirror structure**: Module files should match command files in name and purpose
- **Export clearly**: Use `__init__.py` to provide a clean public API
- **Avoid deep nesting**: Prefer flat structure with `shared.py` over deeply nested submodules

## Testing

- Commands should be testable by calling them directly
- Use `click.testing.CliRunner` for testing CLI commands
- Keep business logic in modules (not in commands) for easier unit testing
- Mock external dependencies (AWS clients, file system, etc.)
