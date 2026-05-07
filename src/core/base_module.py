from src.utils.print_utils import error
from tabulate import tabulate

from src.utils.print_utils import info


class BaseModule:
    """Base class for all modules.

    Attributes:
        info (dict): Dictionary containing module information.
        options (dict): Dictionary containing module options.
    """

    info = {
        "name": "Base",
        "description": "Base Module",
        "author": "Samuel Marques",
        "options": {},
    }

    def __init__(self) -> None:
        self.options = {}

    def set_option(self, key, value) -> bool:
        # Search for the key in a case-insensitive way
        for opt_key in self.info["options"]:
            if opt_key.lower() == key.lower():
                self.options[opt_key] = value
                return True
        return False

    def show_info(self) -> None:
        """Show information about the module."""
        info(f"Information for {self.info['name']}:")
        table = []

        for key, value in self.info.items():
            table.append([key.capitalize(), value])

        print(
            tabulate(
                table,
                headers=["Option", "Value"],
                tablefmt="grid",
                colalign=("left", "left"),
                missingval="N/A",
            )
            + "\n"
        )

    def print_options(self) -> None:
        info(f"Options for {self.info['name']}:")
        table = []

        for key, value in self.info["options"].items():
            table.append([key, value[0], value[1], value[2]])

        print(
            tabulate(
                table,
                headers=["Option", "Value", "Required", "Description"],
                tablefmt="grid",
                colalign=("left", "left", "left", "left"),
                missingval="N/A",
            )
            + "\n"
        )

    def run(self) -> None:
        """
        This method should be implemented by each module.
        """
        raise NotImplementedError("Each module must implement its own 'run' method.")

    def check_required_options(self) -> bool:
        """Check if all required options are set."""
        for key, value in self.info["options"].items():
            if value[1] and not self.options.get(key, None):
                error(f"Required option '{key}' is not set.")
                return False
        return True
