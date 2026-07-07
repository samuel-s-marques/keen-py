import asyncio

import dns.resolver
from bs4 import BeautifulSoup

from src.core.base_module import BaseModule
from src.modules.discovery.subdomain_module import SubdomainModule
from src.utils.print_utils import info, success, warn
from src.utils.user_agents import UserAgents


class HistoricalDnsModule(BaseModule):
    metadata = {
        "name": "Historical_DNS",
        "description": "Analyzes historical DNS data to identify old records, infrastructure changes, and abandoned subdomains.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The domain name to analyze (e.g., google.com).",
                "domain",
            ],
            "SECURITYTRAILS_API_KEY": [
                "",
                False,
                "API Key for SecurityTrails to get more comprehensive historical data.",
                "",
            ],
            "MIGRATION_MAX_IPS": [
                "10",
                False,
                "Max historical IPs to analyze for infrastructure migrations.",
                "",
            ],
        },
    }

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()
        api_key: str = str(self.options.get("SECURITYTRAILS_API_KEY")).strip()

        await self.loading(
            f"Gathering historical DNS data for {target}...",
            self.execute,
            target,
            api_key,
        )

    async def execute(self, target: str, api_key: str) -> None:
        historical_ips = set()
        ip_history_data = []  # List of dicts: {'ip': ip, 'date': date, 'source': source}
        subdomains = set()

        # Fetch HackerTarget IP History
        info("Fetching HackerTarget IP history...")
        ht_data = await self._get_hackertarget_history(target)
        for entry in ht_data:
            ip_history_data.append(entry)
            historical_ips.add(entry["ip"])

        # Fetch ViewDNS IP History
        info("Fetching ViewDNS IP history...")
        vd_data = await self._get_viewdns_history(target)
        for entry in vd_data:
            ip_history_data.append(entry)
            historical_ips.add(entry["ip"])

        # Fetch SecurityTrails Data (if key is present)
        if api_key:
            info("Fetching SecurityTrails historical data...")
            st_data, st_subdomains = await self._get_securitytrails_data(
                target, api_key
            )
            for entry in st_data:
                ip_history_data.append(entry)
                historical_ips.add(entry["ip"])
            subdomains.update(st_subdomains)
        else:
            warn(
                "SecurityTrails API key not provided. Falling back to crt.sh for subdomain history."
            )
            crt_subdomains = await SubdomainModule().find_by_crt(target)
            subdomains.update(crt_subdomains)

        # Print Historical IPs
        if ip_history_data:
            # Sort by date if possible (very basic sort)
            ip_history_data.sort(key=lambda x: x.get("date", ""), reverse=True)
            table = self.results_table(
                title=f"Historical IP Records for {target}",
                columns=["Date", "IP Address", "Source"],
            )

            # Avoid duplicates in display
            seen = set()
            for entry in ip_history_data:
                key = (entry["ip"], entry["date"])
                if key not in seen:
                    table.add_row(
                        str(entry.get("date", "Unknown")),
                        str(entry.get("ip", "")),
                        str(entry.get("source", "")),
                    )
                    seen.add(key)

            self.render(table)
            success(f"Discovered {len(historical_ips)} unique historical IP addresses.")
        else:
            warn("No historical IP records found.")

        # Analyze Migrations
        info("Analyzing infrastructure migrations...")
        await self._analyze_migrations(historical_ips, target)

        # Check Abandoned Subdomains
        vulnerable_subs = []
        if subdomains:
            info(f"Checking {len(subdomains)} historical subdomains for abandonment...")
            vulnerable_subs = await self._check_abandoned_subdomains(subdomains)
        else:
            warn("No subdomains found for abandonment analysis.")

        # Save results
        results_dict = {
            "ip_history": ip_history_data,
            "subdomains": list(subdomains),
            "vulnerable_subdomains": vulnerable_subs,
        }
        await self._save_results(target, results_dict)

    async def _get_hackertarget_history(self, target: str) -> list[dict]:
        results = []
        try:
            async with self.get_http_client() as client:
                r = await client.get(
                    f"https://api.hackertarget.com/iphistory/?q={target}",
                    timeout=15,
                    headers={"User-Agent": UserAgents.get()},
                )
                if r.status_code == 200 and "error" not in r.text.lower():
                    lines = r.text.strip().split("\n")
                    for line in lines:
                        parts = line.split(",")
                        if len(parts) >= 2:
                            ip = parts[0].strip()
                            # HackerTarget returns: ip, target
                            # Unfortunately, it doesn't always give dates in this endpoint.
                            results.append(
                                {"ip": ip, "date": "Unknown", "source": "HackerTarget"}
                            )
        except Exception:
            pass
        return results

    async def _get_viewdns_history(self, target: str) -> list[dict]:
        results = []
        try:
            url = f"https://viewdns.info/iphistory/?domain={target}"
            async with self.get_http_client() as client:
                r = await client.get(
                    url, timeout=15, headers={"User-Agent": UserAgents.get()}
                )
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    # Find the table containing the history
                    tables = soup.find_all("table", border="1")
                    if tables:
                        history_table = tables[0]
                        rows = history_table.find_all("tr")[1:]  # Skip header
                        for row in rows:
                            cols = row.find_all("td")
                            if len(cols) >= 4:
                                ip = cols[0].text.strip()
                                # location = cols[1].text.strip()
                                # owner = cols[2].text.strip()
                                date = cols[3].text.strip()
                                results.append(
                                    {"ip": ip, "date": date, "source": "ViewDNS"}
                                )
        except Exception:
            pass
        return results

    async def _get_securitytrails_data(
        self, target: str, api_key: str
    ) -> tuple[list[dict], set[str]]:
        history = []
        subdomains = set()
        headers = {"accept": "application/json", "APIKEY": api_key}

        async with self.get_http_client() as client:
            # Get History
            try:
                r = await client.get(
                    f"https://api.securitytrails.com/v1/history/{target}/dns/a",
                    headers=headers,
                    timeout=20,
                )
                if r.status_code == 200:
                    data = r.json()
                    records = data.get("records", [])
                    for record in records:
                        values = record.get("values", [])
                        for val in values:
                            ip = val.get("ip")
                            first_seen = record.get("first_seen", "Unknown")
                            if ip:
                                history.append(
                                    {
                                        "ip": ip,
                                        "date": first_seen,
                                        "source": "SecurityTrails",
                                    }
                                )
            except Exception:
                pass

            # Get Subdomains
            try:
                r = await client.get(
                    f"https://api.securitytrails.com/v1/domain/{target}/subdomains?children_only=false",
                    headers=headers,
                    timeout=20,
                )
                if r.status_code == 200:
                    data = r.json()
                    subs = data.get("subdomains", [])
                    for sub in subs:
                        subdomains.add(f"{sub}.{target}")
            except Exception:
                pass

        return history, subdomains

    async def _analyze_migrations(self, historical_ips: set, target: str) -> None:
        """Analyze IPs to determine different ASNs/Providers to infer migrations."""
        if not historical_ips:
            return

        asn_results = []
        # Get ASN info for a bounded number of historical IPs to identify changes.
        try:
            migration_max = max(1, int(self.options.get("MIGRATION_MAX_IPS") or 10))
        except (ValueError, TypeError):
            migration_max = 10
        ips_to_check = list(historical_ips)[:migration_max]

        from src.utils.asn import lookup_asn

        results = await self.gather_bounded(
            [lookup_asn(ip) for ip in ips_to_check], limit=10
        )

        providers = set()
        for res in results:
            if res and not isinstance(res, Exception):
                asn_results.append(res)
                providers.add(res["provider"])

        if len(providers) > 1:
            warn(f"Multiple infrastructure providers detected: {', '.join(providers)}")
            table = self.results_table(
                title="Infrastructure Migrations",
                columns=["Historical IP", "ASN", "Provider"],
            )
            for res in asn_results:
                table.add_row(res["ip"], res["asn"], res["provider"])
            self.render(table)
        elif len(providers) == 1:
            info(f"Historically consistently hosted on: {list(providers)[0]}")

    async def _check_abandoned_subdomains(
        self, subdomains: set[str]
    ) -> list[tuple[str, str, list[str]]]:
        """Actively check subdomains for NXDOMAIN or specific 404/Takeover patterns."""
        vulnerable = []

        # Takeover signatures
        signatures = [
            "NoSuchBucket",
            "There is no app configured at that hostname",
            "No Such Account",
            "You're Almost There",
            "a GitHub Pages site here",
            "project not found",
            "Domain mapping upgrade for this domain not found",
            "The site you were looking for couldn't be found",
            "The specified bucket does not exist",
        ]

        async def check_sub(client, sub):
            try:
                # Resolve DNS
                answers = await asyncio.to_thread(dns.resolver.resolve, sub, "A")
                ips = [str(a) for a in answers]

                # If it resolves, perform HTTP request to check for takeover signatures
                try:
                    r = await client.get(
                        f"http://{sub}",
                        timeout=5,
                        headers={"User-Agent": UserAgents.get()},
                        follow_redirects=True,
                    )
                    content = r.text
                    for sig in signatures:
                        if sig in content:
                            return (sub, f"Potential Takeover (Found '{sig}')", ips)

                    if r.status_code == 404:
                        return (sub, "Resolves but returns 404", ips)
                except Exception:
                    # Connection error, might be internal or abandoned service
                    pass

            except dns.resolver.NXDOMAIN:
                # If NXDOMAIN, check if it has a CNAME
                try:
                    cname_answers = await asyncio.to_thread(
                        dns.resolver.resolve, sub, "CNAME"
                    )
                    cnames = [str(c) for c in cname_answers]
                    return (sub, f"Dangling CNAME: {', '.join(cnames)}", [])
                except Exception:
                    pass
            except Exception:
                pass
            return None

        # Check with bounded concurrency to avoid flooding.
        async with self.get_http_client() as client:
            results = await self.gather_bounded(
                [check_sub(client, sub) for sub in subdomains], limit=20
            )
            for res in results:
                if res and not isinstance(res, Exception):
                    vulnerable.append(res)

        if vulnerable:
            table = self.results_table(
                title="Potentially Abandoned / Vulnerable Subdomains",
                columns=["Subdomain", "Status", "IPs"],
            )

            for sub, status, ips in vulnerable:
                table.add_row(sub, status, ", ".join(ips))

            self.render(table)
            warn(
                f"Found {len(vulnerable)} potentially abandoned/vulnerable subdomains!"
            )
        else:
            success("No abandoned or vulnerable subdomains detected.")

        return vulnerable

    async def _save_results(self, target: str, results: dict) -> None:
        from src.core.result_builder import NodeFactory, ResultBuilder

        ip_history = results.get("ip_history", [])
        subdomains = results.get("subdomains", [])
        vulnerable_subs = results.get("vulnerable_subdomains", [])

        builder = ResultBuilder()
        builder.add_node(
            NodeFactory.domain(
                target,
                historical_ips_count=len(set(x["ip"] for x in ip_history)),
                historical_subdomains_count=len(subdomains),
                vulnerable_subdomains_count=len(vulnerable_subs),
            )
        )

        # Create lookup dictionary for vulnerable subdomain statuses
        vuln_lookup = {}
        for sub, status, ips in vulnerable_subs:
            vuln_lookup[sub.lower()] = {
                "status": status,
                "ips": ips,
                "vulnerable": True,
            }

        # Map Historical Subdomains
        for sub in subdomains:
            sub_cleaned = sub.strip().lower()
            if not sub_cleaned:
                continue

            vuln_info = vuln_lookup.get(
                sub_cleaned, {"vulnerable": False, "status": None, "ips": []}
            )

            sub_node = NodeFactory.domain(
                sub_cleaned,
                takeover_vulnerable=vuln_info["vulnerable"],
                takeover_status=vuln_info["status"],
                vulnerable_ips=vuln_info["ips"],
                historical=True,
            )
            # Add extended STIX2 fields for vulnerability info
            sub_node["metadata"]["stix2"]["x_vulnerable_takeover"] = vuln_info[
                "vulnerable"
            ]
            sub_node["metadata"]["stix2"]["x_takeover_status"] = vuln_info["status"]

            builder.add_node(sub_node)
            builder.add_edge(target, sub_cleaned, "has-subdomain")

        # Map Historical IP Addresses
        for ip_entry in ip_history:
            ip_val = ip_entry.get("ip")
            date_val = ip_entry.get("date", "Unknown")
            source_val = ip_entry.get("source", "Unknown")

            if not ip_val:
                continue

            builder.add_node(NodeFactory.ip(ip_val, historical=True))

            record_str = f"{date_val} ({source_val})"

            # Check if edge already exists and append to metadata
            existing_edge = next(
                (
                    e
                    for e in builder._edges
                    if e["source"] == target
                    and e["target"] == ip_val
                    and e["relationship"] == "historically-resolved-to"
                ),
                None,
            )

            if existing_edge:
                if record_str not in existing_edge["metadata"]["historical_records"]:
                    existing_edge["metadata"]["historical_records"].append(record_str)
            else:
                builder.add_edge(
                    target,
                    ip_val,
                    "historically-resolved-to",
                    metadata={
                        "historical_records": [record_str],
                    },
                )

        await self.post_run(builder.build())
