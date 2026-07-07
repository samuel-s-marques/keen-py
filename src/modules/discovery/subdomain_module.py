import asyncio
import os
import re
import socket

import dns.query
import dns.resolver
import dns.zone

from src.core.base_module import BaseModule
from src.utils.print_utils import error, info
from src.utils.user_agents import UserAgents


class SubdomainModule(BaseModule):
    # Common SRV service prefixes probed during DNS discovery.
    SRV_RECORDS = [
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
                # All three discovery strategies run concurrently (async).
                results = await asyncio.gather(
                    self._find_by_dns(target),
                    self._find_by_bruteforce(target),
                    self._find_by_passive(target),
                    return_exceptions=True,
                )
                for result in results:
                    if isinstance(result, set):
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
            async with self.get_http_client() as client:
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

    async def _find_by_dns(self, target: str) -> set[str]:
        """Find subdomains using DNS techniques (AXFR, SRV)."""
        subdomains: set[str] = set()

        # Zone Transfer (AXFR) — blocking, so offload to a worker thread.
        subdomains |= await asyncio.to_thread(self._axfr_transfer, target)

        # Common SRV records, resolved with bounded concurrency.
        srv_results = await self.gather_bounded(
            [self._check_srv(f"{srv}.{target}") for srv in self.SRV_RECORDS],
            limit=20,
        )
        for result in srv_results:
            if isinstance(result, set):
                subdomains |= result

        return subdomains

    def _axfr_transfer(self, target: str) -> set[str]:
        """Attempt DNS zone transfers (AXFR) against the target's nameservers."""
        subdomains: set[str] = set()
        try:
            ns_answers = dns.resolver.resolve(target, "NS")
            for ns in ns_answers:
                ns_str = str(ns.target).rstrip(".")
                try:
                    xfr = dns.query.xfr(ns_str, target, timeout=10)
                    zone = dns.zone.from_xfr(xfr)
                    for name, node in zone.nodes.items():
                        hostname = f"{name}.{target}" if str(name) != "@" else target
                        subdomains.add(hostname.rstrip("."))
                except Exception:
                    pass
        except Exception:
            pass
        return subdomains

    async def _check_srv(self, srv_target: str) -> set:
        """Helper to check a specific SRV record."""
        found = set()
        try:
            answers = await asyncio.to_thread(dns.resolver.resolve, srv_target, "SRV")
            for rdata in answers:
                hostname = str(rdata.target).rstrip(".")
                found.add(hostname)
        except Exception:
            pass
        return found

    async def _find_by_bruteforce(self, target: str) -> set:
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
                candidates = [
                    f"{sub}.{target}" for sub in (line.strip() for line in f) if sub
                ]
        except Exception as e:
            error(f"Error during bruteforce: {str(e)}")
            return subdomains

        # Resolve in chunks so a huge wordlist stays memory-bounded, each chunk
        # with capped concurrency instead of a fixed 50-thread pool.
        chunk_size = 1000
        for i in range(0, len(candidates), chunk_size):
            chunk = candidates[i : i + chunk_size]
            results = await self.gather_bounded(
                [self._check_subdomain(domain) for domain in chunk], limit=50
            )
            for res in results:
                if res and not isinstance(res, Exception):
                    subdomains.add(res)

        return subdomains

    async def _check_subdomain(self, subdomain: str) -> str | None:
        """Check if a subdomain exists using DNS resolution (off the event loop)."""
        try:
            await asyncio.to_thread(socket.gethostbyname, subdomain)
            return subdomain
        except (socket.gaierror, OSError):
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
            async with self.get_http_client() as client:
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
            async with self.get_http_client() as client:
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
        from src.core.result_builder import NodeFactory, ResultBuilder

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
