from typing import Any
from src.utils.print_utils import warn, error, success
from src.utils.user_agents import UserAgents
from src.utils.validator import InputValidator
import httpx

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
                "email,phone,username",
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
            "RAPID_API_KEY": ["", False, "API Key for RapidAPI.", ""],
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

        all_leaks = []
        match target_type:
            case "username":
                lc = await self.loading(
                    f"Checking {target} on LeakCheck...", self.check_leak_check, target
                )
                bv = await self.loading(
                    f"Checking {target} on BreachVIP...", self.check_breachvip, target
                )
                dh = await self.loading(
                    f"Checking {target} on DeHashed...", self.check_dehashed, target
                )
                all_leaks.extend(lc or [])
                all_leaks.extend(bv or [])
                all_leaks.extend(dh or [])
            case "email":
                hb = await self.loading(
                    f"Checking {target} on HIBP...", self.check_HIBP, target
                )
                lc = await self.loading(
                    f"Checking {target} on LeakCheck...", self.check_leak_check, target
                )
                bv = await self.loading(
                    f"Checking {target} on BreachVIP...", self.check_breachvip, target
                )
                dh = await self.loading(
                    f"Checking {target} on DeHashed...", self.check_dehashed, target
                )
                all_leaks.extend(hb or [])
                all_leaks.extend(lc or [])
                all_leaks.extend(bv or [])
                all_leaks.extend(dh or [])
            case "phone":
                lc = await self.loading(
                    f"Checking {target} on LeakCheck...", self.check_leak_check, target
                )
                bv = await self.loading(
                    f"Checking {target} on BreachVIP...", self.check_breachvip, target
                )
                dh = await self.loading(
                    f"Checking {target} on DeHashed...", self.check_dehashed, target
                )
                all_leaks.extend(lc or [])
                all_leaks.extend(bv or [])
                all_leaks.extend(dh or [])
            case _:
                error(
                    "Invalid type. Please choose one of 'username', 'email', 'phone', or 'auto'."
                )
                return

        await self._save_results(target, {"type": target_type, "leaks": all_leaks})

    async def check_HIBP(self, target: str) -> list[dict]:
        if not InputValidator.is_valid_email(target):
            error(f"Invalid email address: {target}")
            return []

        api_key = self.options.get("HIBP_APIKEY")

        if not api_key:
            warn("API Key not found for Have I Been Pwned. Skipping API verification.")
            return []

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                r = await client.get(
                    f"https://haveibeenpwned.com/api/v3/breachedAccount/{target}",
                    headers={"User-Agent": "keen-py/1.0.0", "hibp-api-key": api_key},
                )

            if r.status_code != 200:
                error(f"{target} not found in any data breach.")
                return []

            breaches = r.json()
            output_results = []
            for breach in breaches:
                print(f"[{target}] was found in {breach['Name']} data breach")
                output_results.append(
                    {
                        "source": "HIBP",
                        "breach_name": breach.get("Name"),
                        "date": breach.get("BreachDate"),
                        "categories": breach.get("DataClasses", []),
                        "extra_info": {},
                    }
                )
            return output_results

        except Exception as e:
            error(f"Error checking Have I Been Pwned: {e}")
            return []

    async def check_breachvip(self, target: str) -> list[dict]:
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

            async with httpx.AsyncClient(follow_redirects=True) as client:
                r = await client.post(
                    "https://breach.vip/api/search", headers=headers, json=payload
                )

                if r.status_code == 403:
                    warn("BreachVIP returned 403. Attempting via proxy...")
                    r = await client.post(
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
                return []

            if r.status_code != 200:
                error(f"Error checking BreachVIP: {res.get('error', 'Unknown Error')}")
                return []

            results = res.get("results", [])
            output_results = []
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
                output_results.append(
                    {
                        "source": "BreachVIP",
                        "breach_name": source,
                        "date": None,
                        "categories": (
                            [categories] if isinstance(categories, str) else categories
                        ),
                        "extra_info": {
                            k: v
                            for k, v in result.items()
                            if k not in ["source", "categories"] and v
                        },
                    }
                )
            return output_results
        except Exception as e:
            error(f"Error checking BreachVIP: {e}")
            return []

    async def check_leak_check(self, target: str) -> list[dict]:
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

            async with httpx.AsyncClient(follow_redirects=True) as client:
                r = await client.get(url, headers=headers)

            if r.status_code == 403:
                error("Limit exceeded for LeakCheck. Try again later.")
                return []

            if r.status_code != 200:
                error(f"Error checking LeakCheck: {r.status_code}")
                return []

            res = r.json()

            if not res.get("success"):
                error(f"Error checking LeakCheck: {res.get('message')}")
                return []

            output_results = []
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
                    output_results.append(
                        {
                            "source": "LeakCheck",
                            "breach_name": name,
                            "date": date,
                            "categories": fields,
                            "extra_info": {},
                        }
                    )

            else:
                results: list[dict] = res.get("sources", [])
                for result in results:
                    name = result.get("name", "Unknown")
                    date = result.get("date", "Unknown")

                    success(f"{target} was found in {name} data breach at {date}")
                    output_results.append(
                        {
                            "source": "LeakCheck",
                            "breach_name": name,
                            "date": date,
                            "categories": [],
                            "extra_info": {},
                        }
                    )
            return output_results

        except Exception as e:
            error(f"Error checking LeakCheck: {e}")
            return []

    async def check_dehashed(self, target: str) -> list[dict]:
        api_key = self.options.get("DEHASHED_APIKEY")

        if not api_key:
            warn("API Key not found for DeHashed. Skipping API verification.")
            return []

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
            async with httpx.AsyncClient(follow_redirects=True) as client:
                r = await client.post(
                    "https://api.dehashed.com/v2/search", headers=headers, json=payload
                )
            res = r.json()

            if r.status_code != 200:
                error(f"Error checking DeHashed: {res.get('error', 'Unknown Error')}")
                return []

            entries = res.get("entries", [])

            if not entries:
                return []

            output_results = []
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

                output_results.append(
                    {
                        "source": "DeHashed",
                        "breach_name": database,
                        "date": None,
                        "categories": [
                            field for field in display_fields if entry.get(field)
                        ],
                        "extra_info": {
                            field: entry.get(field)
                            for field in display_fields
                            if entry.get(field)
                        },
                    }
                )
            return output_results

        except Exception as e:
            error(f"Error checking DeHashed: {e}")
            return []

    async def check_breach_directory(self, target: str) -> list[dict]:
        return []

    async def _save_results(self, target: str, results: dict) -> None:
        import uuid

        target_type = results.get("type", "email")
        leaks = results.get("leaks", [])

        # Primary Target Node Construction
        stix2_target: dict = {}
        misp_target: dict = {}

        if target_type == "email":
            STIX_EMAIL_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa2")
            target_uuid = uuid.uuid5(STIX_EMAIL_NAMESPACE, target)
            stix2_target = {
                "type": "email-addr",
                "id": f"email-addr--{target_uuid}",
                "spec_version": "2.1",
                "value": target,
            }
            misp_target = {
                "type": "email-dst",
                "value": target,
            }
            primary_node = {
                "type": "email-addr",
                "value": target,
                "metadata": {
                    "stix2": stix2_target,
                    "misp": misp_target,
                    "leaks_count": len(leaks),
                },
            }
        elif target_type == "phone":
            STIX_PHONE_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa1")
            target_uuid = uuid.uuid5(STIX_PHONE_NAMESPACE, target)
            stix2_target = {
                "type": "x-phone-number",
                "id": f"x-phone-number--{target_uuid}",
                "spec_version": "2.1",
                "value": target,
            }
            misp_target = {
                "type": "phone-number",
                "value": target,
            }
            primary_node = {
                "type": "x-phone-number",
                "value": target,
                "metadata": {
                    "stix2": stix2_target,
                    "misp": misp_target,
                    "leaks_count": len(leaks),
                },
            }
        else:  # username
            STIX_ACCOUNT_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa6")
            target_uuid = uuid.uuid5(STIX_ACCOUNT_NAMESPACE, f"username:{target}")
            stix2_target = {
                "type": "user-account",
                "id": f"user-account--{target_uuid}",
                "spec_version": "2.1",
                "account_login": target,
                "account_type": "username",
            }
            misp_target = {
                "type": "text",
                "value": target,
            }
            primary_node = {
                "type": "user-account",
                "value": f"username:{target}",
                "metadata": {
                    "stix2": stix2_target,
                    "misp": misp_target,
                    "leaks_count": len(leaks),
                },
            }

        nodes: list[dict[str, Any]] = [primary_node]
        edges: list[dict[str, Any]] = []

        # Map Leak Nodes
        STIX_BREACH_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa8")
        for leak in leaks:
            breach_name = leak.get("breach_name", "Unknown")
            source = leak.get("source", "Unknown")
            date = leak.get("date")
            categories = leak.get("categories", [])
            extra_info = leak.get("extra_info", {})

            # Standard STIX 2.1 custom observable for a data breach
            breach_uuid = uuid.uuid5(STIX_BREACH_NAMESPACE, f"{source}:{breach_name}")
            stix2_breach = {
                "type": "x-data-breach",
                "id": f"x-data-breach--{breach_uuid}",
                "spec_version": "2.1",
                "name": breach_name,
                "description": f"Target was compromised in {breach_name} breach (reported by {source})",
                "source": source,
                "breach_date": date,
                "categories": categories,
            }

            misp_breach = {
                "type": "leak-source",
                "value": f"{source} ({breach_name})",
            }

            breach_node = {
                "type": "x-data-breach",
                "value": f"{source}:{breach_name}",
                "metadata": {
                    "stix2": stix2_breach,
                    "misp": misp_breach,
                    "breach_date": date,
                },
            }

            if breach_node not in nodes:
                nodes.append(breach_node)

            source_val = (
                target if target_type in ["email", "phone"] else f"username:{target}"
            )
            edges.append(
                {
                    "source": source_val,
                    "target": f"{source}:{breach_name}",
                    "relationship": "compromised-in",
                    "metadata": {
                        "categories": categories,
                        "extra_info": extra_info,
                    },
                }
            )

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
