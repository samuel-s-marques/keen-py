import httpx
import asyncio
from holehe import core as holehe_core

from src.utils.print_utils import error, success
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

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET"))
        await self.holehe(target)

    async def holehe(self, target: str) -> None:
        output = []

        # pyrefly: ignore [missing-attribute]
        modules = holehe_core.import_submodules("holehe.modules")
        websites = holehe_core.get_functions(modules)

        client = httpx.AsyncClient(timeout=10)
        tasks = [website(target, client, output) for website in websites]

        # Run all module checks concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
        await client.aclose()

        # Holehe results (for parsing later) TODO: Parse results
        """
        {
            "name": "example",
            "rateLimit": false,
            "exists": true,
            "emailrecovery": "ex****e@gmail.com",
            "phoneNumber": "0*******78",
            "others": null
        }
        """

        # Display results (only registered ones)
        registered = [item["name"] for item in output if item.get("exists")]
        if registered:
            success(f"Email registered on: {', '.join(registered)}")
        else:
            error(f"No registrations found or target '{target}' is invalid.")
