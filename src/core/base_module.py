from tabulate import tabulate

from src.utils.print_utils import info


class BaseModule:
    """Base class for all modules.

    Attributes:
        info (dict): Dictionary containing module information.
        options (dict): Dictionary containing module options.
    """

    def __init__(self) -> None:
        self.info = {
            "name": "Base",
            "description": "Base Module",
            "author": "Samuel Marques",
            "options": {},
        }
        self.options = {}

    def set_option(self, key, value) -> bool:
        if key in self.info["options"]:
            self.options[key] = value
            return True
        return False

    def print_options(self) -> None:
        info(f"Options for {self.info['name']}:")
        table = []

        for key, value in self.info["options"].items():
            table.append([key, value[0], value[1], value[2]])

        print(
            tabulate(
                table,
                headers=["Option", "Value", "Required", "Description"],
                tablefmt="pretty",
            )
            + "\n"
        )

    def run(self) -> None:
        """
        This method should be implemented by each module.
        """
        raise NotImplementedError("Each module must implement its own 'run' method.")
