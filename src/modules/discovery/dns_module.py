import asyncio
from typing import Any
import dns.resolver
import random
import string
import ipaddress

from src.utils.print_utils import info, success, warn
from src.core.base_module import BaseModule


class DnsModule(BaseModule):
    # Meaningful DNS record types for recon (obsolete/experimental types dropped).
    RECORD_TYPES = [
        "A",
        "AAAA",
        "NS",
        "MX",
        "TXT",
        "CNAME",
        "SOA",
        "CAA",
        "SRV",
        "PTR",
        "NAPTR",
        "SPF",
        "DNSKEY",
        "DS",
        "TLSA",
    ]

    metadata = {
        "name": "DNS_Enum",
        "description": "Discovers DNS records of a target domain.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The domain name to enumerate (e.g. google.com).",
                "domain",
            ]
        },
    }

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()

        await self.loading(
            f"Enumerating DNS records for {target}...", self.execute, target
        )

    async def execute(self, target: str) -> None:
        await self.get_wildcard_records(target)
        await self.check_dnssec(target)

        records: list[str] = self.RECORD_TYPES
        results = []

        async def resolve_record(record_type: str):
            try:
                # Use asyncio.to_thread to avoid blocking the event loop
                answers = await asyncio.to_thread(
                    dns.resolver.resolve, target, record_type, lifetime=5
                )
                return record_type, [str(rdata) for rdata in answers]
            except (
                dns.resolver.NoAnswer,
                dns.resolver.NXDOMAIN,
                dns.resolver.Timeout,
                dns.resolver.NoNameservers,
            ):
                return record_type, None
            except Exception:
                return record_type, None

        # Run all resolutions concurrently
        tasks = [resolve_record(record) for record in records]
        resolved = await asyncio.gather(*tasks)

        # Process and filter results
        for record_type, data in resolved:
            if data:
                results.append((record_type, data))

        # Display results in a table
        if results:
            table = self.results_table(
                title=f"DNS Records for {target}",
                columns=["Type", "Data"],
            )

            for record_type, data in results:
                table.add_row(record_type, "\n".join(data))

            self.render(table)
            success(f"Discovered {len(results)} record types for {target}.")

            # ASN Intelligence
            ips = []
            for record_type, data in results:
                if record_type in ["A", "AAAA"]:
                    ips.extend(data)

            unique_ips = list(set(ips))
            asn_results = []
            if unique_ips:
                for ip in unique_ips[:5]:  # Limit to avoid excessive queries
                    asn_data = await self.get_asn_info(ip)
                    if asn_data:
                        asn_results.append(asn_data)

                if asn_results:
                    asn_table = self.results_table(
                        title=f"ASN Intelligence for {target}",
                        columns=[
                            "IP Address",
                            "ASN",
                            "BGP Prefix",
                            "Provider",
                            "Country",
                        ],
                    )

                    for res in asn_results:
                        asn_table.add_row(
                            res["ip"],
                            res["asn"],
                            res["prefix"],
                            res["provider"],
                            res["country"],
                        )
                    self.render(asn_table)
        else:
            info(f"No DNS records found for {target}.")
            asn_results = []

        results_dict = {"records": results, "asn_info": asn_results}
        await self._save_results(target, results_dict)

    async def get_wildcard_records(self, target: str) -> None:
        """Detect if the target domain has a wildcard DNS record."""
        # Generate a random subdomain that is unlikely to exist
        random_sub = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=12)
        )
        test_domain = f"{random_sub}.{target}"

        try:
            # Check for A records
            answers = await asyncio.to_thread(
                dns.resolver.resolve, test_domain, "A", lifetime=5
            )
            if answers:
                ips = [str(rdata) for rdata in answers]
                warn(
                    f"Wildcard record detected! {test_domain} resolves to: {', '.join(ips)}"
                )
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout):
            # This is expected if there is NO wildcard
            pass
        except Exception:
            pass

    async def check_dnssec(self, target: str) -> None:
        """Analyze DNSSEC for the target domain."""
        algorithms = {
            1: "RSAMD5",
            3: "DSA",
            5: "RSASHA1",
            7: "RSASHA1-NSEC3-SHA1",
            8: "RSASHA256",
            10: "RSASHA512",
            13: "ECDSAP256SHA256",
            14: "ECDSAP384SHA384",
            15: "ED25519",
            16: "ED448",
        }

        digest_types = {
            1: "SHA-1",
            2: "SHA-256",
            3: "GOST R 34.11-94",
            4: "SHA-384",
        }

        results = []

        try:
            # Check for DNSKEY
            dnskeys = await asyncio.to_thread(
                dns.resolver.resolve, target, "DNSKEY", lifetime=5
            )
            for key in dnskeys:
                key_type = "KSK" if key.flags == 257 else "ZSK"
                algo = algorithms.get(key.algorithm, f"Unknown ({key.algorithm})")
                results.append(
                    ["DNSKEY", f"{key_type} | {algo} | Tag: {key.key_tag()}"]
                )
        except Exception:
            pass

        try:
            # Check for DS
            ds_records = await asyncio.to_thread(
                dns.resolver.resolve, target, "DS", lifetime=5
            )
            for ds in ds_records:
                algo = algorithms.get(ds.algorithm, f"Unknown ({ds.algorithm})")
                digest = digest_types.get(ds.digest_type, f"Unknown ({ds.digest_type})")
                results.append(["DS", f"{algo} | {digest} | Tag: {ds.key_tag}"])
        except Exception:
            pass

        if results:
            table = self.results_table(
                title=f"DNSSEC Analysis for {target}",
                columns=["Record", "Details"],
            )

            for record_type, details in results:
                table.add_row(record_type, details)

            self.render(table)
            success(f"DNSSEC is enabled for {target}.")
        else:
            info(f"DNSSEC is not enabled for {target}.")

    async def get_asn_info(self, ip: str) -> dict | None:
        """Retrieve ASN intelligence for an IP using Team Cymru DNS service."""
        try:
            addr = ipaddress.ip_address(ip)
            if addr.version == 4:
                reversed_ip = ".".join(reversed(ip.split(".")))
                query = f"{reversed_ip}.origin.asn.cymru.com"
            else:  # IPv6
                # Expanded nibbles for IPv6 origin6 lookup
                nibbles = addr.exploded.replace(":", "")
                reversed_nibbles = ".".join(reversed(nibbles))
                query = f"{reversed_nibbles}.origin6.asn.cymru.com"

            answers = await asyncio.to_thread(dns.resolver.resolve, query, "TXT")
            # Format: "15169 | 8.8.8.0/24 | US | arin | 2001-01-24"
            data = str(answers[0]).strip('"').split(" | ")
            if len(data) < 3:
                return None

            asn = data[0].strip()
            prefix = data[1].strip()
            country = data[2].strip()

            # Get ASN Name/Description
            name_query = f"AS{asn}.asn.cymru.com"
            name_answers = await asyncio.to_thread(
                dns.resolver.resolve, name_query, "TXT"
            )
            # Format: "15169 | US | arin | 2001-01-24 | GOOGLE, US"
            name_data = str(name_answers[0]).strip('"').split(" | ")
            provider = name_data[4].strip() if len(name_data) > 4 else "Unknown"

            return {
                "ip": ip,
                "asn": asn,
                "prefix": prefix,
                "country": country,
                "provider": provider,
            }
        except Exception:
            return None

    async def _save_results(self, target: str, results: dict) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory, STIXNamespaces

        records = results.get("records", [])
        asn_info = results.get("asn_info", [])

        builder = ResultBuilder()
        builder.add_node(NodeFactory.domain(target, record_types_count=len(records)))

        # Map DNS Records
        for record_type, data in records:
            if not data:
                continue

            for item in data:
                item_cleaned = item.strip().rstrip(".")

                if record_type in ["A", "AAAA"]:
                    version = 4 if record_type == "A" else 6
                    builder.add_node(NodeFactory.ip(item_cleaned, version=version))
                    builder.add_edge(target, item_cleaned, "resolves-to")

                elif record_type == "MX":
                    parts = item_cleaned.split()
                    mx_host = parts[-1].rstrip(".")
                    priority = (
                        int(parts[0]) if len(parts) > 1 and parts[0].isdigit() else 10
                    )
                    builder.add_node(NodeFactory.domain(mx_host, priority=priority))
                    builder.add_edge(target, mx_host, "has-mx-record")

                elif record_type == "NS":
                    builder.add_node(NodeFactory.domain(item_cleaned))
                    builder.add_edge(target, item_cleaned, "has-ns-record")

                elif record_type == "CNAME":
                    builder.add_node(NodeFactory.domain(item_cleaned))
                    builder.add_edge(target, item_cleaned, "has-cname-record")

                elif record_type == "TXT":
                    builder.add_node(
                        NodeFactory.custom(
                            "x-dns-txt",
                            item_cleaned,
                            misp_type="text",
                        )
                    )
                    builder.add_edge(target, item_cleaned, "has-txt-record")

        # Map ASN Intelligence
        for asn_entry in asn_info:
            ip_val = asn_entry.get("ip")
            asn_val = asn_entry.get("asn")
            prefix = asn_entry.get("prefix")
            provider = asn_entry.get("provider")
            country = asn_entry.get("country")

            if not ip_val or not asn_val:
                continue

            as_val = f"AS{asn_val}"
            builder.add_node(
                NodeFactory.custom(
                    "autonomous-system",
                    as_val,
                    namespace=STIXNamespaces.IDENTITY,
                    stix2_extra={
                        "number": int(asn_val) if asn_val.isdigit() else 0,
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
            builder.add_edge(ip_val, as_val, "belongs-to-as")

        await self.post_run(builder.build())
