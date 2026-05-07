from src.utils.print_utils import info
import whois

from src.utils.print_utils import error
from src.core.base_module import BaseModule


class WhoisModule(BaseModule):
    def __init__(self) -> None:
        super().__init__()
        self.info = {
            "name": "Whois",
            "description": "Retrieves registration details, expiration dates, and nameservers for a domain.",
            "author": "Samuel Marques",
            "options": {
                "TARGET": ["", True, "The domain name to lookup (e.g. google.com)."],
            },
        }

        # Initialize options with default values
        self.options = {k: v[0] for k, v in self.info["options"].items()}

    def run(self):
        target = self.options.get("TARGET")

        if not target:
            error("TARGET option is required.")
            return None

        try:
            w = whois.whois(target)

            for key, value in w.items():
                if value:
                    print(f"{key}: {value}")

            return w
        except Exception as e:
            error(f"WHOIS lookup failed: {str(e)}")
