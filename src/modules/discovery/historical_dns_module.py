import asyncio
import requests
import dns.resolver
from bs4 import BeautifulSoup
from rich.table import Table
from rich.console import Console

from src.utils.print_utils import info, success, warn
from src.utils.user_agents import UserAgents
from src.core.base_module import BaseModule
from src.modules.discovery.subdomain_module import SubdomainModule


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
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

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
        ht_data = await asyncio.to_thread(self._get_hackertarget_history, target)
        for entry in ht_data:
            ip_history_data.append(entry)
            historical_ips.add(entry["ip"])

        # Fetch ViewDNS IP History
        info("Fetching ViewDNS IP history...")
        vd_data = await asyncio.to_thread(self._get_viewdns_history, target)
        for entry in vd_data:
            ip_history_data.append(entry)
            historical_ips.add(entry["ip"])

        # Fetch SecurityTrails Data (if key is present)
        if api_key:
            info("Fetching SecurityTrails historical data...")
            st_data, st_subdomains = await asyncio.to_thread(
                self._get_securitytrails_data, target, api_key
            )
            for entry in st_data:
                ip_history_data.append(entry)
                historical_ips.add(entry["ip"])
            subdomains.update(st_subdomains)
        else:
            warn(
                "SecurityTrails API key not provided. Falling back to crt.sh for subdomain history."
            )
            crt_subdomains = await asyncio.to_thread(
                SubdomainModule().find_by_crt, target
            )
            subdomains.update(crt_subdomains)

        # Print Historical IPs
        if ip_history_data:
            # Sort by date if possible (very basic sort)
            ip_history_data.sort(key=lambda x: x.get("date", ""), reverse=True)
            table = Table(
                show_header=True,
                header_style="bold blue",
                title=f"Historical IP Records for {target}",
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )
            table.add_column("Date", justify="left", style="cyan", no_wrap=True)
            table.add_column("IP Address", justify="left", style="white")
            table.add_column("Source", justify="left", style="magenta")

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

            console = Console()
            console.print(table)
            success(f"Discovered {len(historical_ips)} unique historical IP addresses.")
        else:
            warn("No historical IP records found.")

        # Analyze Migrations
        info("Analyzing infrastructure migrations...")
        await self._analyze_migrations(historical_ips, target)

        # Check Abandoned Subdomains
        if subdomains:
            info(f"Checking {len(subdomains)} historical subdomains for abandonment...")
            await self._check_abandoned_subdomains(subdomains)
        else:
            warn("No subdomains found for abandonment analysis.")

    def _get_hackertarget_history(self, target: str) -> list[dict]:
        results = []
        try:
            r = requests.get(
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
        except Exception as _:
            pass
        return results

    def _get_viewdns_history(self, target: str) -> list[dict]:
        results = []
        try:
            url = f"https://viewdns.info/iphistory/?domain={target}"
            r = requests.get(url, timeout=15, headers={"User-Agent": UserAgents.get()})
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
        except Exception as _:
            pass
        return results

    def _get_securitytrails_data(
        self, target: str, api_key: str
    ) -> tuple[list[dict], set[str]]:
        history = []
        subdomains = set()
        headers = {"accept": "application/json", "APIKEY": api_key}

        # Get History
        try:
            r = requests.get(
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
            r = requests.get(
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
        # Get ASN info for up to 10 historical IPs to identify infrastructure changes
        ips_to_check = list(historical_ips)[:10]

        async def fetch_asn(ip):
            try:
                # Basic reverse DNS or Team Cymru approach
                import ipaddress

                addr = ipaddress.ip_address(ip)
                if addr.version == 4:
                    reversed_ip = ".".join(reversed(ip.split(".")))
                    query = f"{reversed_ip}.origin.asn.cymru.com"
                else:
                    return None

                answers = await asyncio.to_thread(dns.resolver.resolve, query, "TXT")
                data = str(answers[0]).strip('"').split(" | ")
                if len(data) >= 3:
                    asn = data[0].strip()
                    # Get provider name
                    name_query = f"AS{asn}.asn.cymru.com"
                    try:
                        name_answers = await asyncio.to_thread(
                            dns.resolver.resolve, name_query, "TXT"
                        )
                        name_data = str(name_answers[0]).strip('"').split(" | ")
                        provider = (
                            name_data[4].strip() if len(name_data) > 4 else "Unknown"
                        )
                        return {"ip": ip, "asn": asn, "provider": provider}
                    except Exception:
                        return {"ip": ip, "asn": asn, "provider": "Unknown"}
            except Exception:
                return None
            return None

        tasks = [fetch_asn(ip) for ip in ips_to_check]
        results = await asyncio.gather(*tasks)

        providers = set()
        for res in results:
            if res:
                asn_results.append(res)
                providers.add(res["provider"])

        if len(providers) > 1:
            warn(f"Multiple infrastructure providers detected: {', '.join(providers)}")
            table = Table(
                show_header=True,
                header_style="bold blue",
                title="Infrastructure Migrations",
            )
            table.add_column("Historical IP", style="cyan")
            table.add_column("ASN", style="magenta")
            table.add_column("Provider", style="green")
            for res in asn_results:
                table.add_row(res["ip"], res["asn"], res["provider"])
            Console().print(table)
        elif len(providers) == 1:
            info(f"Historically consistently hosted on: {list(providers)[0]}")

    async def _check_abandoned_subdomains(self, subdomains: set[str]) -> None:
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

        async def check_sub(sub):
            try:
                # Resolve DNS
                answers = await asyncio.to_thread(dns.resolver.resolve, sub, "A")
                ips = [str(a) for a in answers]

                # If it resolves, perform HTTP request to check for takeover signatures
                try:
                    r = await asyncio.to_thread(
                        requests.get,
                        f"http://{sub}",
                        timeout=5,
                        headers={"User-Agent": UserAgents.get()},
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

        # Check in batches
        import concurrent.futures

        tasks = [check_sub(sub) for sub in subdomains]

        # Limit concurrency to avoid flooding
        # Doing this manually with chunks
        chunk_size = 20
        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i : i + chunk_size]
            results = await asyncio.gather(*chunk)
            for res in results:
                if res:
                    vulnerable.append(res)

        if vulnerable:
            table = Table(
                show_header=True,
                header_style="bold blue",
                title="Potentially Abandoned / Vulnerable Subdomains",
                title_style="bold red",
                show_lines=True,
                expand=True,
            )
            table.add_column("Subdomain", style="red")
            table.add_column("Status", style="yellow")
            table.add_column("IPs", style="white")

            for sub, status, ips in vulnerable:
                table.add_row(sub, status, ", ".join(ips))

            Console().print(table)
            warn(
                f"Found {len(vulnerable)} potentially abandoned/vulnerable subdomains!"
            )
        else:
            success("No abandoned or vulnerable subdomains detected.")
