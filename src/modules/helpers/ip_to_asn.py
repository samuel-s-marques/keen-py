import ipaddress

from src.core.base_module import BaseModule
from src.utils.asn import lookup_asn
from src.utils.print_utils import error, success


class IpToAsn(BaseModule):
    metadata = {
        "name": "Ip_To_Asn",
        "description": "Resolves an IP address to its announcing ASN, BGP prefix, and country via Team Cymru.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "magic_consumes": ["ipv4-addr", "ipv6-addr"],
        "options": {
            "TARGET": [
                "",
                True,
                "The IP address to resolve.",
                "ip",
            ],
        },
    }

    def loading_message(self, target: str) -> str:
        return f"Resolving ASN for {target}..."

    async def execute(self, target: str) -> None:
        ip = target
        result = await lookup_asn(ip)

        if not result:
            error(f"Could not resolve an ASN for {ip}.")
            return

        success(f"{ip} is routed via AS{result['asn']} ({result['provider']}).")
        self.display_results(ip, result)
        await self._save_results(ip, result)

    def display_results(self, ip: str, result: dict) -> None:
        table = self.kv_table(title=f"ASN Lookup: {ip}")
        table.add_row("ASN", f"AS{result['asn']}")
        table.add_row("Provider", result.get("provider") or "Unknown")
        table.add_row("BGP Prefix", result.get("prefix") or "Unknown")
        table.add_row("Country", result.get("country") or "Unknown")
        self.render(table)

    async def _save_results(self, ip: str, result: dict) -> None:
        from src.core.result_builder import NodeFactory, ResultBuilder, STIXNamespaces

        asn = str(result.get("asn") or "").strip()
        if not asn:
            return

        asn_value = f"AS{asn}"
        provider = result.get("provider") or None
        prefix = result.get("prefix") or None
        country = result.get("country") or None

        builder = ResultBuilder()

        try:
            version = ipaddress.ip_address(ip).version
        except ValueError:
            version = 4
        builder.add_node(NodeFactory.ip(ip, version=version))

        # Same shape as the ASN nodes produced by dns_module.py, so both
        # modules dedup/merge onto the same graph node for a given ASN.
        builder.add_node(
            NodeFactory.custom(
                "autonomous-system",
                asn_value,
                namespace=STIXNamespaces.IDENTITY,
                stix2_extra={
                    "number": int(asn) if asn.isdigit() else 0,
                    "name": provider,
                    "country": country,
                    "prefix": prefix,
                },
                misp_type="asn",
                provider=provider,
                prefix=prefix,
                country=country,
            )
        )
        builder.add_edge(ip, asn_value, "belongs-to-as")

        if country:
            builder.add_node(NodeFactory.location(country, type="country"))
            builder.add_edge(asn_value, country, "located-in")

        await self.post_run(builder.build())
