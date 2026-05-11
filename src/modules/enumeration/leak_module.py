from src.core.base_module import BaseModule


class LeakModule(BaseModule):
    metadata = {
        "name": "Leak_Check",
        "description": "Checks if credentials (username, email, phone number) have been leaked using various databases.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The target to check for leaks (email, username or phone number).",
                "",
            ],
            "TYPE": [
                "auto",
                False,
                "The type of the target (username, email, phone number, auto).",
                "",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        pass
