"""Lightweight domain -> IP resolver.

``discovery/dns_enum`` already resolves A/AAAA records as part of a much
broader 15-record-type sweep (NS/MX/TXT/CNAME/SOA/CAA/...), but it doesn't
declare ``magic_consumes`` -- so today, discovering a bare ``domain-name``
node never automatically resolves to its IP(s) via magic chaining. This is
the fast, single-purpose, chainable pivot that closes that gap: additive to
``dns_enum``, not a replacement (same precedent as ``discovery/cert_transparency``
being pulled out of ``subdomain_module``'s inline crt.sh call).

Produces the exact same node/edge shape ``dns_enum`` already does for A/AAAA
records (``NodeFactory.ip`` + a ``resolves-to`` edge), so a domain resolved
by both modules dedups onto the same graph nodes rather than diverging.
"""

import asyncio

import dns.resolver

from src.core.base_module import BaseModule
from src.utils.print_utils import error, success


class DomainToIp(BaseModule):
    metadata = {
        "name": "Domain_To_IP",
        "description": "Resolves a domain's A/AAAA records to its IPv4/IPv6 addresses.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "magic_consumes": ["domain-name"],
        # Passive: a standard public DNS resolution, no different from what
        # a browser does visiting the domain.
        "execution_safety": "passive",
        "options": {
            "TARGET": ["", True, "The domain name to resolve.", "domain"],
        },
    }

    def loading_message(self, target: str) -> str:
        return f"Resolving {target} to its IP address(es)..."

    async def execute(self, target: str) -> None:
        addresses = await self._resolve(target)
        if not addresses:
            error(f"Could not resolve any A/AAAA records for {target}.")
            return

        success(f"{target} resolves to {len(addresses)} address(es).")
        self.display_results(target, addresses)
        await self._save_results(target, addresses)

    async def _resolve(self, domain: str) -> list[dict]:
        results: list[dict] = []
        for record_type, version in (("A", 4), ("AAAA", 6)):
            try:
                # asyncio.to_thread avoids blocking the event loop, matching
                # discovery/dns_enum's own convention for the same call.
                answers = await asyncio.to_thread(
                    dns.resolver.resolve, domain, record_type, lifetime=5
                )
                for answer in answers:
                    results.append({"ip": str(answer).strip(), "version": version})
            except (
                dns.resolver.NoAnswer,
                dns.resolver.NXDOMAIN,
                dns.resolver.NoNameservers,
                dns.resolver.Timeout,
            ):
                continue
            except Exception as e:
                self.logger.error(f"DNS {record_type} lookup failed for {domain}: {e}")
        return results

    def display_results(self, target: str, addresses: list[dict]) -> None:
        table = self.results_table(
            title=f"Domain -> IP: {target}", columns=["IP Address", "Version"]
        )
        for addr in addresses:
            table.add_row(addr["ip"], f"IPv{addr['version']}")
        self.render(table)

    async def _save_results(self, target: str, addresses: list[dict]) -> None:
        from src.core.result_builder import NodeFactory, ResultBuilder

        builder = ResultBuilder()
        builder.add_node(NodeFactory.domain(target))
        for addr in addresses:
            builder.add_node(NodeFactory.ip(addr["ip"], version=addr["version"]))
            builder.add_edge(target, addr["ip"], "resolves-to")

        await self.post_run(builder.build())
