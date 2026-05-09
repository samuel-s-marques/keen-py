from typing import Any
import whois

from src.utils.print_utils import error
from src.core.base_module import BaseModule


class WhoisModule(BaseModule):
    metadata = {
        "name": "Whois",
        "description": "Retrieves registration details, expiration dates, and nameservers for a domain.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The domain name to lookup (e.g. google.com).",
                "domain",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        # Initialize options with default values
        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()

        await self.loading(
            f"Executing WHOIS query on {target}...", self.execute, target
        )

    async def execute(self, target: str) -> None:
        try:
            w: dict[str, Any] = whois.whois(target)

            for key, value in w.items():
                if value:
                    print(f"{key}: {value}")
        except Exception as e:
            error(f"WHOIS lookup failed: {str(e)}")
