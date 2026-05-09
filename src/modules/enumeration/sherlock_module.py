import subprocess
from utils.print_utils import info
from utils.print_utils import error
from core.base_module import BaseModule


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

    def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET"))
        self.sherlock(target)

    def sherlock(self, target: str, timeout: str = "5"):
        cmd = [
            "python",
            "vendors/sherlock/sherlock_project/sherlock.py",
            target,
            "--timeout",
            timeout,
        ]

        info(f"Lauching external Sherlock process for {target}...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            error("Sherlock process failed to execute.")
            return

        print(result.stdout)
