from holehe import core as holehe_core
from holehe import modules as holehe_modules

from src.utils.print_utils import error
from src.utils.validator import InputValidator
from src.core.base_module import BaseModule


class HoleheModule(BaseModule):
    metadata = {
        "name": "Holehe",
        "description": "Checks for email accounts on various platforms.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The target email to lookup.",
                "email",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    def run(self) -> None:
        if not self.pre_run():
            return

        print("oi")

        target: str = str(self.options.get("TARGET"))
        output = []

        # pyrefly: ignore [missing-attribute]
        modules = holehe_modules.import_submodules("holehe.modules")
        print(len(modules))
