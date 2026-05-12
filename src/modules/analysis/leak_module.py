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
            "HIBP_APIKEY": ["", False, "API Key for Have I Been Pwned.", ""],
            "LEAKCHECK_APIKEY": ["", False, "API Key for LeakCheck.", ""],
            "DEHASHED_APIKEY": ["", False, "API Key for DeHashed.", ""],
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
                await self.loading(
                    f"Checking {target} on BreachVIP...", self.check_breachvip, target
                )
                await self.loading(
                    f"Checking {target} on DeHashed...", self.check_dehashed, target
                )
            case "email":
                await self.loading(
                    f"Checking {target} on HIBP...", self.check_HIBP, target
                )
                await self.loading(
                    f"Checking {target} on LeakCheck...", self.check_leak_check, target
                )
                await self.loading(
                    f"Checking {target} on BreachVIP...", self.check_breachvip, target
                )
                await self.loading(
                    f"Checking {target} on DeHashed...", self.check_dehashed, target
                )
            case "phone":
                await self.loading(
                    f"Checking {target} on LeakCheck...", self.check_leak_check, target
                )
                await self.loading(
                    f"Checking {target} on BreachVIP...", self.check_breachvip, target
                )
                await self.loading(
                    f"Checking {target} on DeHashed...", self.check_dehashed, target
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

    async def check_breachvip(self, target: str) -> None:
        try:
            payload: dict = {
                "term": target,
                "fields": ["username", "email", "phone"],
                "categories": [],
                "wildcard": False,
                "case_sensitive": False,
            }
            headers = {
                "User-Agent": UserAgents.get(),
                "Content-Type": "application/json",
            }

            r = requests.post(
                "https://breach.vip/api/search", headers=headers, json=payload
            )

            if r.status_code == 403:
                warn("BreachVIP returned 403. Attempting via proxy...")
                r = requests.post(
                    "https://swolesome.pages.dev/api/proxy",
                    headers=headers,
                    json=payload,
                )

            try:
                res = r.json()
            except ValueError:
                error(
                    f"Error checking BreachVIP: Invalid JSON response (Status {r.status_code})"
                )
                return

            if r.status_code != 200:
                error(f"Error checking BreachVIP: {res.get('error', 'Unknown Error')}")
                return

            results = res.get("results", [])
            for result in results:
                source = result.get("source", "Unknown")
                categories = result.get("categories", "Unknown")

                extra_data = []
                for k, v in result.items():
                    if k not in ["source", "categories"] and v:
                        extra_data.append(f"{k}: {v}")

                extra_str = (
                    f" - Extra info: {', '.join(extra_data)}" if extra_data else ""
                )

                success(
                    f"{target} was found in {source} data breach with {categories} categories{extra_str}"
                )
        except Exception as e:
            error(f"Error checking BreachVIP: {e}")

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

    async def check_dehashed(self, target: str) -> None:
        api_key = self.options.get("DEHASHED_APIKEY")

        if not api_key:
            warn("API Key not found for DeHashed. Skipping API verification.")
            return

        try:
            payload: dict = {
                "query": target,
                "page": 1,
                "size": 25,
                "wildcard": False,
                "regex": False,
                "de_dupe": True,
            }
            headers = {
                "DeHashed-Api-Key": api_key,
                "Content-Type": "application/json",
            }
            r = requests.post(
                "https://api.dehashed.com/v2/search", headers=headers, data=payload
            )
            res = r.json()

            if r.status_code != 200:
                error(f"Error checking DeHashed: {res.get('error', 'Unknown Error')}")
                return

            entries = res.get("entries", [])

            if not entries:
                return

            for entry in entries:
                database = entry.get("database_name", "Unknown")

                # Fields to show from DeHashed response
                display_fields = [
                    "email",
                    "username",
                    "password",
                    "hashed_password",
                    "name",
                    "phone",
                    "address",
                    "ip_address",
                    "dob",
                ]

                details = []
                for field in display_fields:
                    value = entry.get(field)
                    if value:
                        if isinstance(value, list):
                            clean_values = [str(v) for v in value if v]
                            if clean_values:
                                details.append(
                                    f"{field.replace('_', ' ').title()}: {', '.join(clean_values)}"
                                )
                        else:
                            details.append(
                                f"{field.replace('_', ' ').title()}: {value}"
                            )

                details_str = " | ".join(details)
                success(f"[{database}] {details_str}")

        except Exception as e:
            error(f"Error checking DeHashed: {e}")
