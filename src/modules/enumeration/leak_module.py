from src.utils.print_utils import warn, error, success
from src.utils.user_agents import UserAgents
from src.utils.validator import InputValidator
import requests

from src.core.base_module import BaseModule


class LeakModule(BaseModule):
    metadata = {
        "name": "Leak_Check",
        "description": "Checks if credentials (username, email, phone) have been leaked using various databases.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The target to check for leaks (email, username or phone).",
                "",
            ],
            "TYPE": [
                "auto",
                False,
                "The type of the target (username, email, phone, auto).",
                "",
            ],
            # TODO: Add automatic API key management
            "HIBP_APIKEY": ["", False, "API Key for Have I Been Pwned.", ""],
            "LEAKCHECK_APIKEY": ["", False, "API Key for LeakCheck.", ""],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()
        target_type: str = str(self.options.get("TYPE")).lower()

        if target_type not in ["username", "email", "phone", "auto"]:
            error(
                "Invalid type. Please choose one of 'username', 'email', 'phone', or 'auto'."
            )
            return

        if target_type == "auto":
            if InputValidator.is_valid_email(target):
                target_type = "email"
            elif InputValidator.is_valid_phone_number(target):
                target_type = "phone"
            else:
                target_type = "username"

        match target_type:
            case "username":
                await self.loading(
                    f"Checking {target} on LeakCheck...", self.check_leak_check, target
                )
            case "email":
                await self.loading(
                    f"Checking {target} on HIBP...", self.check_HIBP, target
                )
                await self.loading(
                    f"Checking {target} on LeakCheck...", self.check_leak_check, target
                )
            case "phone":
                await self.loading(
                    f"Checking {target} on LeakCheck...", self.check_leak_check, target
                )
            case _:
                error(
                    "Invalid type. Please choose one of 'username', 'email', 'phone', or 'auto'."
                )
                return

    async def check_HIBP(self, target: str) -> None:
        if not InputValidator.is_valid_email(target):
            error(f"Invalid email address: {target}")
            return

        api_key = self.options.get("HIBP_APIKEY")

        if not api_key:
            warn("API Key not found for Have I Been Pwned. Skipping API verification.")
            return None

        try:
            r = requests.get(
                f"https://haveibeenpwned.com/api/v3/breachedAccount/{target}",
                headers={"User-Agent": "keen-py/1.0.0", "hibp-api-key": api_key},
            )

            if r.status_code != 200:
                error(f"{target} not found in any data breach.")
                return

            breaches = r.json()

            for breach in breaches:
                print(f"[{target}] was found in {breach['Name']} data breach")

        except Exception as e:
            error(f"Error checking Have I Been Pwned: {e}")

    async def check_leak_check(self, target: str) -> None:
        api_key = self.options.get("LEAKCHECK_APIKEY")

        if not api_key:
            warn("API Key not found for LeakCheck. Using public API.")

        try:
            headers = {
                "User-Agent": UserAgents.get(),
                "Accept": "application/json",
            }

            if api_key:
                headers["X-API-Key"] = api_key

            url = f"https://leakcheck.io/api/public?check={target}"

            if api_key:
                url = f"https://leakcheck.io/api/v2/query/{target}"

            r = requests.get(url, headers=headers)

            if r.status_code == 403:
                error("Limit exceeded for LeakCheck. Try again later.")
                return

            if r.status_code != 200:
                error(f"Error checking LeakCheck: {r.status_code}")
                return

            res = r.json()

            if not res.get("success"):
                error(f"Error checking LeakCheck: {res.get('message')}")
                return

            if api_key:
                results: list[dict] = res.get("result", [])
                for result in results:
                    source = result.get("source", {})
                    name = source.get("name", "Unknown")
                    date = source.get("breach_date", "Unknown")

                    fields = result.get("fields", [])
                    fields_str = (
                        f" - Leaked fields: {', '.join(fields)}" if fields else ""
                    )

                    success(
                        f"{target} was found in {name} data breach at {date}{fields_str}"
                    )

            else:
                results: list[dict] = res.get("sources", [])
                for result in results:
                    name = result.get("name", "Unknown")
                    date = result.get("date", "Unknown")

                    success(f"{target} was found in {name} data breach at {date}")

        except Exception as e:
            error(f"Error checking LeakCheck: {e}")
