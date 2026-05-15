import asyncio
from src.utils.user_agents import UserAgents
import httpx
import re
import concurrent.futures
import socket
import os
import dns.resolver
import dns.zone
import dns.query

from src.utils.print_utils import error, info
from src.core.base_module import BaseModule


class SubdomainModule(BaseModule):
    metadata = {
        "name": "Subdomain_Enum",
        "description": "Discovers subdomains of a target domain.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The domain name to lookup (e.g. google.com).",
                "domain",
            ],
            "METHOD": [
                "all",
                False,
                "Method to use (bruteforce, dns, passive, all).",
                "",
            ],
            "WORDLIST": [
                "",
                False,
                "Path to wordlist file.",
                "",
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
        method: str = str(self.options.get("METHOD")).lower()

        if method not in ["all", "dns", "bruteforce", "passive"]:
            error(
                "Invalid method. Please choose one of 'all', 'dns', 'bruteforce', or 'passive'."
            )
            return

        subdomains: set[str] = set()

        try:
            if method == "all":
                # Run DNS and Bruteforce in threads, Passive as async
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    dns_task = asyncio.to_thread(self._find_by_dns, target)
                    brute_task = asyncio.to_thread(self._find_by_bruteforce, target)
                    passive_task = self._find_by_passive(target)

                    results = await asyncio.gather(dns_task, brute_task, passive_task)
                    for result in results:
                        if result:
                            subdomains |= result
            elif method == "dns":
                subdomains = await self.loading(
                    f"Executing DNS subdomain discovery on {target}...",
                    self._find_by_dns,
                    target,
                )
            elif method == "bruteforce":
                subdomains = await self.loading(
                    f"Executing bruteforce subdomain discovery on {target}...",
                    self._find_by_bruteforce,
                    target,
                )
            elif method == "passive":
                subdomains = await self.loading(
                    f"Executing passive subdomain discovery on {target}...",
                    self._find_by_passive,
                    target,
                )

            info(f"Found {len(subdomains)} subdomains:")
            for subdomain in subdomains:
                print(subdomain)

            # Trigger save results
            results_dict = {"subdomains": list(subdomains)}
            await self._save_results(target, results_dict)
        except Exception as e:
            error(f"Error: {str(e)}")
            return

    async def find_by_crt(self, target: str) -> set[str]:
        """Get subdomains from crt.sh free API."""
        subdomains: set[str] = set()

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://crt.sh/?q=%25.{target}&output=json",
                    timeout=60,
                    headers={"User-Agent": UserAgents.get()},
                )

                if r.status_code != 200:
                    return set()

                certs = r.json()

                for cert in certs:
                    name: str = cert.get("name_value", "")
                    for line in name.split("\n"):
                        line: str = line.strip().lower()
                        if line and "*" not in line:
                            subdomains.add(line)

        except Exception:
            pass

        return subdomains

    def _find_by_dns(self, target: str) -> set[str]:
        """Find subdomains using DNS techniques (AXFR, SRV)."""
        subdomains: set[str] = set()

        # Zone Transfer (AXFR)
        try:
            ns_answers = dns.resolver.resolve(target, "NS")
            for ns in ns_answers:
                ns_str = str(ns.target).rstrip(".")
                try:
                    # Attempt AXFR
                    xfr = dns.query.xfr(ns_str, target, timeout=10)
                    zone = dns.zone.from_xfr(xfr)
                    if zone:
                        for name, node in zone.nodes.items():
                            hostname = (
                                f"{name}.{target}" if str(name) != "@" else target
                            )
                            subdomains.add(hostname.rstrip("."))
                except Exception:
                    pass
        except Exception:
            pass

        # Common SRV records
        srv_records = [
            "_sip._tcp",
            "_sip._udp",
            "_sip._tls",
            "_autodiscover._tcp",
            "_xmpp-server._tcp",
            "_xmpp-client._tcp",
            "_ldap._tcp",
            "_gc._msdcs",
            "_kerberos._tcp",
            "_kpasswd._tcp",
            "_vlmcs._tcp",
            "_jabber._tcp",
            "_h323ls._udp",
            "_h323cs._tcp",
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(self._check_srv, f"{srv}.{target}"): srv
                for srv in srv_records
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        subdomains |= result
                except Exception:
                    pass

        return subdomains

    def _check_srv(self, srv_target: str) -> set:
        """Helper to check a specific SRV record."""
        found = set()
        try:
            answers = dns.resolver.resolve(srv_target, "SRV")
            for rdata in answers:
                hostname = str(rdata.target).rstrip(".")
                found.add(hostname)
        except Exception:
            pass
        return found

    def _find_by_bruteforce(self, target: str) -> set:
        """Get values from wordlist and check if the subdomain exists."""
        wordlist_path = self.options.get("WORDLIST")

        if not wordlist_path or not os.path.exists(wordlist_path):
            error(
                "Wordlist is required and must be a valid file for bruteforce method."
            )
            return set()

        subdomains = set()

        try:
            with open(wordlist_path, "r", encoding="utf-8", errors="ignore") as f:
                with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
                    batch_size = 1000
                    batch = []

                    for line in f:
                        sub = line.strip()
                        if sub:
                            batch.append(f"{sub}.{target}")

                        if len(batch) >= batch_size:
                            self._process_batch(executor, batch, subdomains)
                            batch = []

                    if batch:
                        self._process_batch(executor, batch, subdomains)

        except Exception as e:
            error(f"Error during bruteforce: {str(e)}")

        return subdomains

    def _process_batch(self, executor, batch: list, subdomains: set) -> None:
        """Helper to process a batch of subdomains."""
        futures = {
            executor.submit(self._check_subdomain, domain): domain for domain in batch
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                if res:
                    subdomains.add(res)
            except Exception:
                pass

    def _check_subdomain(self, subdomain: str) -> str | None:
        """Check if a subdomain exists using DNS resolution."""
        try:
            socket.gethostbyname(subdomain)
            return subdomain
        except socket.gaierror:
            return None

    async def _find_by_passive(self, target: str) -> set:
        """Get domains from passive sources."""
        subdomains = set()

        results = await asyncio.gather(
            self.find_by_crt(target),
            self._find_by_anubis(target),
            self._find_by_rapiddns(target),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, set):
                subdomains |= result
            elif isinstance(result, Exception):
                pass

        return subdomains

    async def _find_by_anubis(self, target: str) -> set:
        """Get domains from anubis.db free API."""
        subdomains = set()

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://anubisdb.com/anubis/subdomains/{target}",
                    timeout=60,
                    headers={"User-Agent": UserAgents.get()},
                )

                if r.status_code != 200:
                    return set()

                data = r.json()

                for line in data:
                    subdomains.add(line)
        except Exception:
            pass

        return subdomains

    async def _find_by_rapiddns(self, target: str) -> set:
        """Get domains from rapiddns.io free API."""
        subdomains = set()

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://rapiddns.io/subdomain/{target}?full=1",
                    timeout=30,
                    headers={"User-Agent": UserAgents.get()},
                )

                if r.status_code != 200:
                    return set()

                pattern = rf"^(?:[a-zA-Z0-9-]+\.).*{re.escape(target)}$"

                subdomains = set(
                    match.group(0)
                    for match in re.finditer(pattern, r.text, re.MULTILINE)
                )
        except Exception:
            pass

        return subdomains

    async def _save_results(self, target: str, results: dict) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory

        subdomains = results.get("subdomains", [])

        builder = ResultBuilder()
        builder.add_node(NodeFactory.domain(target, subdomains_count=len(subdomains)))

        for sub in subdomains:
            sub_cleaned = sub.strip().lower()
            if not sub_cleaned:
                continue

            builder.add_node(NodeFactory.domain(sub_cleaned))
            builder.add_edge(target, sub_cleaned, "has-subdomain")

        await self.post_run(builder.build())
