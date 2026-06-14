from src.utils.print_utils import warn, error, success
from src.utils.user_agents import UserAgents
from src.utils.validator import InputValidator

from src.core.base_module import BaseModule


class LeakModule(BaseModule):
    metadata = {
        "name": "Leak_Check",
        "description": "Checks if credentials (username, email, phone) have been leaked using various databases.",
        "author": "Samuel Marques",
        "version": "1.1.0",
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
        tasks = []
        match target_type:
            case "username":
                tasks = [
                    self.loading(
                        f"Checking {target} on LeakCheck...",
                        self.check_leak_check,
                        target,
                    ),
                    self.loading(
                        f"Checking {target} on BreachVIP...",
                        self.check_breachvip,
                        target,
                    ),
                    self.loading(
                        f"Checking {target} on DeHashed...", self.check_dehashed, target
                    ),
                    self.loading(
                        f"Checking {target} on BreachDirectory...",
                        self.check_breach_directory,
                        target,
                    ),
                ]
            case "email":
                tasks = [
                    self.loading(
                        f"Checking {target} on HIBP...", self.check_HIBP, target
                    ),
                    self.loading(
                        f"Checking {target} on LeakCheck...",
                        self.check_leak_check,
                        target,
                    ),
                    self.loading(
                        f"Checking {target} on BreachVIP...",
                        self.check_breachvip,
                        target,
                    ),
                    self.loading(
                        f"Checking {target} on DeHashed...", self.check_dehashed, target
                    ),
                    self.loading(
                        f"Checking {target} on BreachDirectory...",
                        self.check_breach_directory,
                        target,
                    ),
                    self.loading(
                        f"Checking {target} on ProxyNova...",
                        self.check_proxynova,
                        target,
                    ),
                ]
            case "phone":
                tasks = [
                    self.loading(
                        f"Checking {target} on LeakCheck...",
                        self.check_leak_check,
                        target,
                    ),
                    self.loading(
                        f"Checking {target} on BreachVIP...",
                        self.check_breachvip,
                        target,
                    ),
                    self.loading(
                        f"Checking {target} on DeHashed...", self.check_dehashed, target
                    ),
                ]
            case _:
                error(
                    "Invalid type. Please choose one of 'username', 'email', 'phone', or 'auto'."
                )
                return

        if tasks:
            import asyncio

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    all_leaks.extend(res)
                elif isinstance(res, Exception):
                    error(f"Error checking provider: {str(res)}")

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
            async with self.get_http_client(follow_redirects=True) as client:
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

            async with self.get_http_client(follow_redirects=True) as client:
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

            async with self.get_http_client(follow_redirects=True) as client:
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
            async with self.get_http_client(follow_redirects=True) as client:
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
        api_key = self.options.get("RAPID_API_KEY")

        if not api_key:
            warn("API Key not found for BreachDirectory.")
            return []

        try:
            headers: dict = {
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": "breachdirectory.p.rapidapi.com",
                "Content-Type": "application/json",
            }
            params: dict = {"term": target, "func": "auto"}

            async with self.get_http_client(follow_redirects=True) as client:
                r = await client.get(
                    "https://breachdirectory.p.rapidapi.com/",
                    headers=headers,
                    params=params,
                )
            res = r.json()

            if r.status_code != 200 or res.get("success") is not True:
                error(
                    f"Error checking BreachDirectory: {res.get('error', 'Unknown Error')}.\nStatus: {r.status_code}"
                )
                return []

            results = res.get("result", [])

            output = []

            def process_result(item: dict) -> list[dict]:
                processed = []
                sources = item.get("sources", [])
                if not sources:
                    sources = ["Unknown"]

                extra_info = {}
                for field in ["password", "sha1", "hash"]:
                    if item.get(field):
                        extra_info[field] = item[field]

                for source in sources:
                    extra_data = [f"{k}: {v}" for k, v in extra_info.items()]
                    extra_str = (
                        f" - Extra info: {', '.join(extra_data)}" if extra_data else ""
                    )
                    success(f"{target} was found in {source} data breach{extra_str}")

                    processed.append(
                        {
                            "source": "BreachDirectory",
                            "breach_name": source,
                            "date": None,
                            "categories": [],
                            "extra_info": extra_info.copy(),
                        }
                    )
                return processed

            import asyncio
            from concurrent.futures import ThreadPoolExecutor

            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor() as pool:
                tasks = [
                    loop.run_in_executor(pool, process_result, item) for item in results
                ]
                if tasks:
                    batch_results = await asyncio.gather(*tasks)
                    for sublist in batch_results:
                        output.extend(sublist)

            return output
        except Exception as e:
            error(f"Error checking BreachDirectory: {e}")
            return []

    async def check_proxynova(self, target: str) -> list:
        if len(target) < 5:
            warn("ProxyNova: Target is too short.")
            return []

        try:
            headers: dict = {
                "Content-Type": "application/json",
                "User-Agent": UserAgents.get(),
            }

            async with self.get_http_client(follow_redirects=True) as client:
                r = await client.get(
                    f"https://api.proxynova.com/comb?query={target}&start=0&limit=20",
                    headers=headers,
                )
            res = r.json()

            if r.status_code != 200:
                error(
                    f"Error checking ProxyNova: {res.get('message', 'Unknown Error')}.\nStatus: {r.status_code}"
                )
                return []

            results = res.get("result", [])

            output = []

            # Proxynova only returns email:password
            for item in results:
                email = item.get("email")
                password = item.get("password")

                if not email or not password:
                    continue

                # Proxynova usually returns different domains for the same target
                if email != target:
                    continue

                success(f"{email}:{password} was found in ProxyNova data breach")

                output.append(
                    {
                        "source": "ProxyNova",
                        "breach_name": "Unknown",
                        "date": None,
                        "categories": [],
                        "extra_info": {"email": email, "password": password},
                    }
                )

            return output
        except Exception as e:
            error(f"Error checking ProxyNova: {e}")
            return []

    async def _save_results(self, target: str, results: dict) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory, STIXNamespaces
        from src.core.pattern_extractor import PatternExtractor

        target_type = results.get("type", "email")
        leaks = results.get("leaks", [])

        builder = ResultBuilder()

        # Primary target node
        match target_type:
            case "email":
                builder.add_node(NodeFactory.email(target, leaks_count=len(leaks)))
            case "phone":
                builder.add_node(NodeFactory.phone(target, leaks_count=len(leaks)))
            case _:
                builder.add_node(
                    NodeFactory.user_account(
                        f"username:{target}",
                        leaks_count=len(leaks),
                    )
                )
                # Override stix2 specifics for username
                primary = builder._nodes[-1]
                primary["metadata"]["stix2"]["account_login"] = target
                primary["metadata"]["stix2"]["account_type"] = "username"
                primary["metadata"]["misp"] = {"type": "text", "value": target}

        source_val = (
            target if target_type in ["email", "phone"] else f"username:{target}"
        )

        # Breach nodes + edges
        for leak in leaks:
            breach_name = leak.get("breach_name", "Unknown")
            source = leak.get("source", "Unknown")
            date = leak.get("date")
            categories = leak.get("categories", [])
            extra_info = leak.get("extra_info", {})

            breach_val = f"{source}:{breach_name}"

            builder.add_node(
                NodeFactory.custom(
                    "x-data-breach",
                    breach_val,
                    namespace=STIXNamespaces.BREACH,
                    stix2_extra={
                        "name": breach_name,
                        "description": f"Target was compromised in {breach_name} breach (reported by {source})",
                        "source": source,
                        "breach_date": date,
                        "categories": categories,
                    },
                    misp_type="leak-source",
                    misp_value=f"{source} ({breach_name})",
                    breach_date=date,
                )
            )

            builder.add_edge(
                source_val,
                breach_val,
                "compromised-in",
                metadata={
                    "categories": categories,
                    "extra_info": extra_info,
                },
            )

            # Extract patterns from extra_info
            PatternExtractor.extract_and_link(builder, breach_val, extra_info)

        await self.post_run(builder.build())
