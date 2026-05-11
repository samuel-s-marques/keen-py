from typing import Any
from typing import Callable
from typing import Literal
from rich.console import Console
from rich.table import Table

from src.utils.validator import InputValidator
from src.utils.print_utils import error


class BaseModule:
    """Base class for all modules.

    Attributes:
        metadata (dict): Dictionary containing module metadata.
        options (dict): Dictionary containing module options.
    """

    metadata = {
        "name": "Base",
        "description": "Base Module",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {},
    }

    def __init__(self) -> None:
        from loguru import logger
        self.options = {}
        self.logger = logger.bind(module=self.metadata["name"])

    def set_option(self, key: str, value) -> bool:
        # Search for the key in a case-insensitive way
        for opt_key in self.metadata["options"]:
            if opt_key.lower() == key.lower():
                # Strip quotes if the value is a string
                if isinstance(value, str):
                    value = value.strip("\"'")
                self.options[opt_key] = value
                return True
        return False

    def show_metadata(self) -> None:
        """Show information about the module."""
        table = Table(
            show_header=True,
            header_style="bold blue",
            title="Module Information",
            title_style="bold cyan",
            show_lines=True,
            expand=True,
        )

        table.add_column("Property", justify="left", style="cyan", no_wrap=True)
        table.add_column("Value", justify="left", style="white")

        for key, value in self.metadata.items():
            if key == "options":
                continue
            table.add_row(key.capitalize(), str(value))

        console: Console = Console()
        console.print(table)

    def print_options(self) -> None:
        """Show the module options."""
        table = Table(
            show_header=True,
            header_style="bold blue",
            title="Module Options",
            title_style="bold cyan",
            show_lines=True,
            expand=True,
        )

        table.add_column("Option", justify="left", style="cyan", no_wrap=True)
        table.add_column("Current Value", justify="left", style="white")
        table.add_column("Required", justify="center", style="magenta")
        table.add_column("Description", justify="left", style="white")

        for key, value in self.metadata["options"].items():
            # value = [default, required, description, validator]
            required: Literal["Yes", "No"] = "Yes" if value[1] else "No"
            current_value = self.options.get(key, value[0])
            table.add_row(key, str(current_value), required, str(value[2]))

        console: Console = Console()
        console.print(table)

    async def run(self) -> None:
        """
        This method should be implemented by each module.
        """
        raise NotImplementedError("Each module must implement its own 'run' method.")

    def check_required_options(self) -> bool:
        """Check if all required options are set."""
        for key, value in self.metadata["options"].items():
            if value[1] and not self.options.get(key, None):
                error(f"Required option '{key}' is not set.")
                return False
        return True

    def validate_options(self) -> bool:
        """Check if the module options are valid."""
        for key, value in self.metadata["options"].items():
            validator = value[3]
            option_value: str = str(self.options.get(key, None))

            if validator and not InputValidator.VALIDATORS[validator](option_value):
                error(f"Invalid value for {key.upper()}. It should be a {validator}.")
                return False
        return True

    def pre_run(self) -> bool:
        """Pre-run checks."""
        if not self.check_required_options():
            return False

        if not self.validate_options():
            return False

        return True

    async def loading(self, title: str, task: Callable, *args, **kwargs) -> Any:
        """Show loading animation."""
        with Console().status(f"[bold green]{title}") as status:
            result: Any = await task(*args, **kwargs)
            status.update(f"[bold green]{title}")
            return result
