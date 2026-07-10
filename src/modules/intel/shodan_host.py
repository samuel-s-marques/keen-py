"""Shodan host pivot.

Queries Shodan's Host API for a single IP, producing open-port/service
nodes and any SSL certificate data Shodan already collected during its own
scans -- this module never scans the target itself, it only reads Shodan's
existing public index of it.
"""

import json

from src.core.base_module import BaseModule
from src.core.result_builder import NodeFactory, ResultBuilder, STIXNamespaces
from src.utils.print_utils import error, success


class ShodanHost(BaseModule):
    metadata = {
        "name": "Shodan_Host",
        "description": (
            "Pulls open ports, service banners, and SSL certificate data for an "
            "IP from Shodan's existing internet-wide scan index."
        ),
        "author": "Samuel Marques",
        "version": "1.0.0",
        "category": "intel",
        "magic_consumes": ["ipv4-addr", "ipv6-addr"],
        # Passive: reads Shodan's already-public index of the target IP; it
        # never touches the target's infrastructure directly (unlike a real
        # port scan, which would be classified active/intrusive).
        "execution_safety": "passive",
        "options": {
            "TARGET": ["", True, "The IP address to look up.", "ip"],
            "SHODAN_APIKEY": ["", True, "API key for Shodan.", ""],
        },
    }

    def loading_message(self, target: str) -> str:
        return f"Querying Shodan for {target}..."

    async def execute(self, target: str) -> None:
        api_key = self.options.get("SHODAN_APIKEY")
        if not api_key:
            error("SHODAN_APIKEY is required. Set it via 'set SHODAN_APIKEY <key>'.")
            return

        host = await self._fetch_host(target, api_key)
        if host is None:
            error(f"Could not retrieve Shodan data for {target}.")
            return
        if not host:
            success(f"No Shodan data found for {target}.")
            return

        success(f"Found {len(host.get('data', []))} service(s) for {target} on Shodan.")
        self.display_results(target, host)
        await self._save_results(target, host)

    async def _fetch_host(self, target: str, api_key: str) -> dict | None:
        cache_key = f"shodan:{target}"
        cached = self.cache_get(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                pass

        host = await self._query_shodan(target, api_key)
        if host is None:
            return None

        self.cache_set(cache_key, json.dumps(host), ttl=3600)
        return host

    async def _query_shodan(self, target: str, api_key: str) -> dict | None:
        await self.rate_limit("shodan")
        try:
            async with self.get_http_client() as client:
                response = await self.request(
                    client,
                    "GET",
                    f"https://api.shodan.io/shodan/host/{target}",
                    params={"key": api_key},
                )
        except Exception as e:
            self.logger.error(f"Shodan request failed for {target}: {e}")
            return None

        if response is None:
            return None
        if response.status_code == 404:
            return {}
        if response.status_code != 200:
            return None

        try:
            return response.json()
        except Exception:
            return None

    def display_results(self, target: str, host: dict) -> None:
        table = self.results_table(
            title=f"Shodan Host: {target}",
            columns=["Port", "Transport", "Product", "Version"],
        )
        for service in host.get("data", []):
            table.add_row(
                str(service.get("port", "")),
                service.get("transport", ""),
                service.get("product", "") or "",
                service.get("version", "") or "",
            )
        self.render(table)

    async def _save_results(self, target: str, host: dict) -> None:
        builder = ResultBuilder()

        try:
            import ipaddress

            version = ipaddress.ip_address(target).version
        except ValueError:
            version = 4
        builder.add_node(NodeFactory.ip(target, version=version))

        org = host.get("org")
        if org:
            builder.add_node(NodeFactory.organization(org))
            builder.add_edge(target, org, "belongs-to-org")

        for service in host.get("data", []):
            port = service.get("port")
            transport = service.get("transport", "tcp")
            if port is None:
                continue

            port_val = f"{target}:{port}/{transport}"
            builder.add_node(
                NodeFactory.custom(
                    "x-port",
                    port_val,
                    namespace=STIXNamespaces.URL,
                    stix2_extra={
                        "port": port,
                        "transport": transport,
                        "product": service.get("product"),
                        "version": service.get("version"),
                    },
                    misp_type="port",
                    misp_value=str(port),
                    product=service.get("product"),
                    version=service.get("version"),
                )
            )
            builder.add_edge(target, port_val, "has-open-port")

            cert = (service.get("ssl") or {}).get("cert") or {}
            fingerprint = (cert.get("fingerprint") or {}).get("sha256")
            if fingerprint:
                cert_val = f"shodan:{fingerprint}"
                builder.add_node(
                    NodeFactory.custom(
                        "x-ssl-certificate",
                        cert_val,
                        namespace=STIXNamespaces.URL,
                        stix2_extra={
                            "fingerprint_sha256": fingerprint,
                            "issuer": cert.get("issuer"),
                            "subject": cert.get("subject"),
                            "validity_not_after": cert.get("expires"),
                        },
                        misp_type="x509-fingerprint-sha256",
                        misp_value=fingerprint,
                    )
                )
                builder.add_edge(cert_val, target, "issued-for")
                builder.add_edge(port_val, cert_val, "secured-by")

        await self.post_run(builder.build())
