import subprocess
import asyncio

from src.utils.print_utils import info
from src.utils.print_utils import error
from src.core.base_module import BaseModule


class SherlockModule(BaseModule):
    metadata = {
        "name": "Sherlock",
        "description": "Searches for a username on the internet, using the Sherlock tool.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The target to lookup (username, name, domain, etc).",
                "",
            ]
        },
    }

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET"))
        await self.sherlock(target)

    async def sherlock(self, target: str, timeout: str = "5"):
        cmd: list[str] = [
            "python",
            "vendors/sherlock/sherlock_project/sherlock.py",
            target,
            "--timeout",
            timeout,
        ]

        info(f"Lauching external Sherlock process for {target}...")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error("Sherlock process failed to execute.")
            return

        print(stdout.decode("utf-8"))
