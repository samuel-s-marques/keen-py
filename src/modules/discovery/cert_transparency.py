"""Standalone Certificate Transparency sweep.

crt.sh is already queried ad hoc inside ``subdomain_module.py`` purely to
seed its own bruteforce wordlist. This module is additive, not a
replacement: it exposes the same crt.sh data as a first-class, chainable
node producer -- one ``x-ssl-certificate`` node per distinct certificate,
with `domain-name` nodes for every subdomain/SAN entry it covers.
"""

import json

from src.core.base_module import BaseModule
from src.core.result_builder import NodeFactory, ResultBuilder, STIXNamespaces
from src.utils.print_utils import error, success


class CertTransparency(BaseModule):
    metadata = {
        "name": "Cert_Transparency",
        "description": (
            "Sweeps crt.sh Certificate Transparency logs for a domain, producing "
            "SSL certificate nodes and the subdomains/SANs each one covers."
        ),
        "author": "Samuel Marques",
        "version": "1.0.0",
        "category": "discovery",
        "magic_consumes": ["domain-name"],
        # Passive: a public CT-log query about the target, never touching its
        # infrastructure directly.
        "execution_safety": "passive",
        "options": {
            "TARGET": ["", True, "The root domain to sweep.", "domain"],
        },
    }

    def loading_message(self, target: str) -> str:
        return f"Sweeping Certificate Transparency logs for {target}..."

    async def execute(self, target: str) -> None:
        certs = await self._fetch_certs(target)
        if certs is None:
            error(f"Could not query crt.sh for {target}.")
            return
        if not certs:
            success(f"No certificates found for {target} on crt.sh.")
            return

        success(f"Found {len(certs)} certificate(s) for {target} on crt.sh.")
        self.display_results(target, certs)
        await self._save_results(target, certs)

    async def _fetch_certs(self, target: str) -> list[dict] | None:
        cache_key = f"crtsh:{target}"
        cached = self.cache_get(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                pass

        raw_certs = await self._query_crtsh(target)
        if raw_certs is None:
            return None

        parsed = self._parse_certs(raw_certs)
        self.cache_set(cache_key, json.dumps(parsed), ttl=3600)
        return parsed

    async def _query_crtsh(self, target: str) -> list[dict] | None:
        await self.rate_limit("crtsh")
        try:
            async with self.get_http_client() as client:
                response = await self.request(
                    client,
                    "GET",
                    f"https://crt.sh/?q=%25.{target}&output=json",
                    timeout=60,
                )
        except Exception as e:
            self.logger.error(f"crt.sh request failed for {target}: {e}")
            return None

        if response is None or response.status_code != 200:
            return None

        try:
            return response.json()
        except Exception:
            return None

    @staticmethod
    def _parse_certs(raw_certs: list[dict]) -> list[dict]:
        """Group crt.sh's flat row-per-name rows into one entry per certificate."""
        certs: dict[str, dict] = {}
        for row in raw_certs:
            cert_id = str(row.get("id") or row.get("min_cert_id") or "")
            if not cert_id:
                continue
            names = {
                line.strip().lower()
                for line in str(row.get("name_value", "")).split("\n")
                if line.strip() and "*" not in line
            }
            entry = certs.setdefault(
                cert_id,
                {
                    "id": cert_id,
                    "issuer": row.get("issuer_name", ""),
                    "not_before": row.get("not_before", ""),
                    "not_after": row.get("not_after", ""),
                    "names": set(),
                },
            )
            entry["names"] |= names

        return [{**entry, "names": sorted(entry["names"])} for entry in certs.values()]

    def display_results(self, target: str, certs: list[dict]) -> None:
        table = self.results_table(
            title=f"Certificate Transparency: {target}",
            columns=["Cert ID", "Issuer", "Names", "Not After"],
        )
        for cert in certs:
            names = ", ".join(cert["names"][:5])
            if len(cert["names"]) > 5:
                names += f" (+{len(cert['names']) - 5} more)"
            table.add_row(
                cert["id"], cert.get("issuer", ""), names, cert.get("not_after", "")
            )
        self.render(table)

    async def _save_results(self, target: str, certs: list[dict]) -> None:
        builder = ResultBuilder()
        builder.add_node(NodeFactory.domain(target))

        for cert in certs:
            cert_value = f"crt.sh:{cert['id']}"
            builder.add_node(
                NodeFactory.custom(
                    "x-ssl-certificate",
                    cert_value,
                    namespace=STIXNamespaces.URL,
                    stix2_extra={
                        "serial_number": cert["id"],
                        "issuer": cert.get("issuer", ""),
                        "validity_not_before": cert.get("not_before", ""),
                        "validity_not_after": cert.get("not_after", ""),
                    },
                    misp_type="x509-fingerprint-sha256",
                    misp_value=cert["id"],
                    issuer=cert.get("issuer", ""),
                    not_before=cert.get("not_before", ""),
                    not_after=cert.get("not_after", ""),
                )
            )
            builder.add_edge(cert_value, target, "issued-for")

            for name in cert["names"]:
                builder.add_node(NodeFactory.domain(name))
                builder.add_edge(name, cert_value, "secured-by")

        await self.post_run(builder.build())
