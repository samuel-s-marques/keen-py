"""Censys host pivot.

Same shape and purpose as ``intel/shodan_host.py`` -- queries Censys' Host
API (v2) for a single IP and produces open-port/service and SSL-certificate
nodes. Deliberately reuses ``shodan_host.py``'s exact ``x-port``/
``x-ssl-certificate`` node-value conventions (``f"{ip}:{port}/{transport}"``)
so a host both modules cover merges its port data onto the same graph nodes
instead of producing two parallel silos of the same infrastructure.

Censys uses HTTP Basic auth (an API ID + secret) rather than Shodan's single
key, so this module has two API-key options instead of one.
"""

import json

from src.core.base_module import BaseModule
from src.core.result_builder import NodeFactory, ResultBuilder, STIXNamespaces
from src.utils.print_utils import error, success


class CensysHost(BaseModule):
    metadata = {
        "name": "Censys_Host",
        "description": (
            "Pulls open ports, service banners, and SSL certificate data for an "
            "IP from Censys' Host API."
        ),
        "author": "Samuel Marques",
        "version": "1.0.0",
        "category": "intel",
        "magic_consumes": ["ipv4-addr", "ipv6-addr"],
        # Passive: reads Censys' existing scan index, never touches the
        # target's infrastructure directly.
        "execution_safety": "passive",
        "options": {
            "TARGET": ["", True, "The IP address to look up.", "ip"],
            "CENSYS_API_ID": ["", True, "Censys API ID.", ""],
            "CENSYS_APIKEY": ["", True, "Censys API secret.", ""],
        },
    }

    def loading_message(self, target: str) -> str:
        return f"Querying Censys for {target}..."

    async def execute(self, target: str) -> None:
        api_id = self.options.get("CENSYS_API_ID")
        api_secret = self.options.get("CENSYS_APIKEY")
        if not api_id or not api_secret:
            error(
                "CENSYS_API_ID and CENSYS_APIKEY are required. "
                "Set them via 'set CENSYS_API_ID <id>' / 'set CENSYS_APIKEY <secret>'."
            )
            return

        result = await self._fetch_host(target, api_id, api_secret)
        if result is None:
            error(f"Could not retrieve Censys data for {target}.")
            return
        if not result:
            success(f"No Censys data found for {target}.")
            return

        services = result.get("services", [])
        success(f"Found {len(services)} service(s) for {target} on Censys.")
        self.display_results(target, result)
        await self._save_results(target, result)

    async def _fetch_host(
        self, target: str, api_id: str, api_secret: str
    ) -> dict | None:
        cache_key = f"censys:{target}"
        cached = self.cache_get(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                pass

        result = await self._query_censys(target, api_id, api_secret)
        if result is None:
            return None

        self.cache_set(cache_key, json.dumps(result), ttl=3600)
        return result

    async def _query_censys(
        self, target: str, api_id: str, api_secret: str
    ) -> dict | None:
        await self.rate_limit("censys")
        try:
            async with self.get_http_client() as client:
                response = await self.request(
                    client,
                    "GET",
                    f"https://search.censys.io/api/v2/hosts/{target}",
                    auth=(api_id, api_secret),
                )
        except Exception as e:
            self.logger.error(f"Censys request failed for {target}: {e}")
            return None

        if response is None:
            return None
        if response.status_code == 404:
            return {}
        if response.status_code != 200:
            return None

        try:
            return (response.json() or {}).get("result", {})
        except Exception:
            return None

    def display_results(self, target: str, result: dict) -> None:
        table = self.results_table(
            title=f"Censys Host: {target}",
            columns=["Port", "Transport", "Service", "Product"],
        )
        for svc in result.get("services", []):
            software = svc.get("software") or [{}]
            product = software[0].get("product", "") if software else ""
            table.add_row(
                str(svc.get("port", "")),
                svc.get("transport_protocol", ""),
                svc.get("service_name", ""),
                product,
            )
        self.render(table)

    async def _save_results(self, target: str, result: dict) -> None:
        builder = ResultBuilder()

        try:
            import ipaddress

            version = ipaddress.ip_address(target).version
        except ValueError:
            version = 4
        builder.add_node(NodeFactory.ip(target, version=version))

        autonomous_system = result.get("autonomous_system") or {}
        org = autonomous_system.get("name")
        if org:
            builder.add_node(NodeFactory.organization(org))
            builder.add_edge(target, org, "belongs-to-org")

        for svc in result.get("services", []):
            port = svc.get("port")
            transport = (svc.get("transport_protocol") or "tcp").lower()
            if port is None:
                continue

            software = svc.get("software") or [{}]
            product = software[0].get("product") if software else None
            product_version = software[0].get("version") if software else None

            # Same value scheme as shodan_host.py -- both modules dedup onto
            # the same x-port node for a given ip/port/transport.
            port_val = f"{target}:{port}/{transport}"
            builder.add_node(
                NodeFactory.custom(
                    "x-port",
                    port_val,
                    namespace=STIXNamespaces.URL,
                    stix2_extra={
                        "port": port,
                        "transport": transport,
                        "product": product,
                        "version": product_version,
                    },
                    misp_type="port",
                    misp_value=str(port),
                    product=product,
                    version=product_version,
                )
            )
            builder.add_edge(target, port_val, "has-open-port")

            cert = svc.get("cert") or {}
            fingerprint = cert.get("fingerprint_sha256")
            if fingerprint:
                cert_val = f"censys:{fingerprint}"
                builder.add_node(
                    NodeFactory.custom(
                        "x-ssl-certificate",
                        cert_val,
                        namespace=STIXNamespaces.URL,
                        stix2_extra={
                            "fingerprint_sha256": fingerprint,
                            "issuer": cert.get("issuer"),
                            "subject": cert.get("subject"),
                            "validity_not_after": cert.get("not_after"),
                        },
                        misp_type="x509-fingerprint-sha256",
                        misp_value=fingerprint,
                    )
                )
                builder.add_edge(cert_val, target, "issued-for")
                builder.add_edge(port_val, cert_val, "secured-by")

        await self.post_run(builder.build())
