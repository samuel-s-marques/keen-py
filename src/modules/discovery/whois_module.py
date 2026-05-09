import whois

from utils.print_utils import error
from core.base_module import BaseModule


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

    def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()

        try:
            w: whois.WhoisEntry = whois.whois(target)

            for key, value in w.items():
                if value:
                    print(f"{key}: {value}")

            return w
        except Exception as e:
            error(f"WHOIS lookup failed: {str(e)}")
