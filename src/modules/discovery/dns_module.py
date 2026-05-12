import asyncio
from typing import Any
import dns.resolver
import random
import string
import ipaddress
from rich.table import Table
from rich.console import Console

from src.utils.print_utils import info, success, warn
from src.core.base_module import BaseModule


class DnsModule(BaseModule):
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

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

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
        records: list[str] = [
            "NONE",
            "A",
            "NS",
            "MD",
            "MF",
            "CNAME",
            "SOA",
            "MB",
            "MG",
            "MR",
            "NULL",
            "WKS",
            "PTR",
            "HINFO",
            "MINFO",
            "MX",
            "TXT",
            "RP",
            "AFSDB",
            "X25",
            "ISDN",
            "RT",
            "NSAP",
            "NSAP-PTR",
            "SIG",
            "KEY",
            "PX",
            "GPOS",
            "AAAA",
            "LOC",
            "NXT",
            "SRV",
            "NAPTR",
            "KX",
            "CERT",
            "A6",
            "DNAME",
            "OPT",
            "APL",
            "DS",
            "SSHFP",
            "IPSECKEY",
            "RRSIG",
            "NSEC",
            "DNSKEY",
            "DHCID",
            "NSEC3",
            "NSEC3PARAM",
            "TLSA",
            "HIP",
            "CDS",
            "CDNSKEY",
            "CSYNC",
            "SPF",
            "UNSPEC",
            "EUI48",
            "EUI64",
            "TKEY",
            "TSIG",
            "IXFR",
            "AXFR",
            "MAILB",
            "MAILA",
            "ANY",
            "URI",
            "CAA",
            "TA",
            "DLV",
        ]

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
            table = Table(
                show_header=True,
                header_style="bold blue",
                title=f"DNS Records for {target}",
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )

            table.add_column("Type", justify="left", style="cyan", no_wrap=True)
            table.add_column("Data", justify="left", style="white")

            for record_type, data in results:
                table.add_row(record_type, "\n".join(data))

            console = Console()
            console.print(table)
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
                    asn_table = Table(
                        show_header=True,
                        header_style="bold blue",
                        title=f"ASN Intelligence for {target}",
                        title_style="bold cyan",
                        show_lines=True,
                        expand=True,
                    )
                    asn_table.add_column("IP Address", style="cyan")
                    asn_table.add_column("ASN", style="magenta")
                    asn_table.add_column("BGP Prefix", style="white")
                    asn_table.add_column("Provider", style="green")
                    asn_table.add_column("Country", style="white")

                    for res in asn_results:
                        asn_table.add_row(
                            res["ip"],
                            res["asn"],
                            res["prefix"],
                            res["provider"],
                            res["country"],
                        )
                    console.print(asn_table)
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
            table = Table(
                show_header=True,
                header_style="bold blue",
                title=f"DNSSEC Analysis for {target}",
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )

            table.add_column("Record", justify="left", style="cyan", no_wrap=True)
            table.add_column("Details", justify="left", style="white")

            for record_type, details in results:
                table.add_row(record_type, details)

            console = Console()
            console.print(table)
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
        import uuid

        records = results.get("records", [])
        asn_info = results.get("asn_info", [])

        # STIX 2.1 Standard Domain-Name Object
        STIX_DOMAIN_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa7")
        domain_uuid = uuid.uuid5(STIX_DOMAIN_NAMESPACE, target)

        stix2_domain = {
            "type": "domain-name",
            "id": f"domain-name--{domain_uuid}",
            "spec_version": "2.1",
            "value": target,
        }

        misp_domain = {
            "type": "domain",
            "value": target,
        }

        primary_node = {
            "type": "domain-name",
            "value": target,
            "metadata": {
                "stix2": stix2_domain,
                "misp": misp_domain,
                "record_types_count": len(records),
            },
        }

        nodes: list[dict[str, Any]] = [primary_node]
        edges: list[dict[str, Any]] = []

        # Standard CTI Namespaces
        STIX_IP_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa0")
        STIX_TXT_NAMESPACE = uuid.UUID(
            "f070f381-8b38-5fdf-9730-802526e84fa5"
        )  # URL namespace for text
        STIX_AS_NAMESPACE = uuid.UUID(
            "f070f381-8b38-5fdf-9730-802526e84fa3"
        )  # Org namespace for AS

        # Map DNS Records
        for record_type, data in records:
            if not data:
                continue

            for item in data:
                # Format cleaning
                item_cleaned = item.strip().rstrip(".")

                if record_type in ["A", "AAAA"]:
                    # IP Address Node
                    ip_uuid = uuid.uuid5(STIX_IP_NAMESPACE, item_cleaned)
                    stix_type = "ipv4-addr" if record_type == "A" else "ipv6-addr"
                    stix2_ip = {
                        "type": stix_type,
                        "id": f"{stix_type}--{ip_uuid}",
                        "spec_version": "2.1",
                        "value": item_cleaned,
                    }
                    ip_node = {
                        "type": stix_type,
                        "value": item_cleaned,
                        "metadata": {
                            "stix2": stix2_ip,
                            "misp": {
                                "type": (
                                    "ip-dst" if record_type == "A" else "ip-dst-ipv6"
                                ),
                                "value": item_cleaned,
                            },
                        },
                    }
                    if ip_node not in nodes:
                        nodes.append(ip_node)

                    edges.append(
                        {
                            "source": target,
                            "target": item_cleaned,
                            "relationship": "resolves-to",
                        }
                    )

                elif record_type in ["MX"]:
                    # MX server host domain. Example: "10 mxb-001a.cyberdyne.com" or "mxb-001a.cyberdyne.com"
                    parts = item_cleaned.split()
                    mx_host = parts[-1].rstrip(".")
                    priority = (
                        int(parts[0]) if len(parts) > 1 and parts[0].isdigit() else 10
                    )

                    mx_uuid = uuid.uuid5(STIX_DOMAIN_NAMESPACE, mx_host)
                    stix2_mx = {
                        "type": "domain-name",
                        "id": f"domain-name--{mx_uuid}",
                        "spec_version": "2.1",
                        "value": mx_host,
                    }
                    mx_node = {
                        "type": "domain-name",
                        "value": mx_host,
                        "metadata": {
                            "stix2": stix2_mx,
                            "misp": {"type": "domain", "value": mx_host},
                            "priority": priority,
                        },
                    }
                    if mx_node not in nodes:
                        nodes.append(mx_node)

                    edges.append(
                        {
                            "source": target,
                            "target": mx_host,
                            "relationship": "has-mx-record",
                        }
                    )

                elif record_type in ["NS"]:
                    ns_uuid = uuid.uuid5(STIX_DOMAIN_NAMESPACE, item_cleaned)
                    stix2_ns = {
                        "type": "domain-name",
                        "id": f"domain-name--{ns_uuid}",
                        "spec_version": "2.1",
                        "value": item_cleaned,
                    }
                    ns_node = {
                        "type": "domain-name",
                        "value": item_cleaned,
                        "metadata": {
                            "stix2": stix2_ns,
                            "misp": {"type": "domain", "value": item_cleaned},
                        },
                    }
                    if ns_node not in nodes:
                        nodes.append(ns_node)

                    edges.append(
                        {
                            "source": target,
                            "target": item_cleaned,
                            "relationship": "has-ns-record",
                        }
                    )

                elif record_type in ["CNAME"]:
                    cname_uuid = uuid.uuid5(STIX_DOMAIN_NAMESPACE, item_cleaned)
                    stix2_cname = {
                        "type": "domain-name",
                        "id": f"domain-name--{cname_uuid}",
                        "spec_version": "2.1",
                        "value": item_cleaned,
                    }
                    cname_node = {
                        "type": "domain-name",
                        "value": item_cleaned,
                        "metadata": {
                            "stix2": stix2_cname,
                            "misp": {"type": "domain", "value": item_cleaned},
                        },
                    }
                    if cname_node not in nodes:
                        nodes.append(cname_node)

                    edges.append(
                        {
                            "source": target,
                            "target": item_cleaned,
                            "relationship": "has-cname-record",
                        }
                    )

                elif record_type in ["TXT"]:
                    txt_uuid = uuid.uuid5(STIX_TXT_NAMESPACE, item_cleaned)
                    stix2_txt = {
                        "type": "x-dns-txt",
                        "id": f"x-dns-txt--{txt_uuid}",
                        "spec_version": "2.1",
                        "value": item_cleaned,
                    }
                    txt_node = {
                        "type": "x-dns-txt",
                        "value": item_cleaned,
                        "metadata": {
                            "stix2": stix2_txt,
                            "misp": {"type": "text", "value": item_cleaned},
                        },
                    }
                    if txt_node not in nodes:
                        nodes.append(txt_node)

                    edges.append(
                        {
                            "source": target,
                            "target": item_cleaned,
                            "relationship": "has-txt-record",
                        }
                    )

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
            as_uuid = uuid.uuid5(STIX_AS_NAMESPACE, as_val)

            stix2_as = {
                "type": "autonomous-system",
                "id": f"autonomous-system--{as_uuid}",
                "spec_version": "2.1",
                "number": int(asn_val) if asn_val.isdigit() else 0,
                "name": provider,
                "country": country,
                "prefix": prefix,
            }

            misp_as = {
                "type": "asn",
                "value": as_val,
            }

            as_node = {
                "type": "autonomous-system",
                "value": as_val,
                "metadata": {
                    "stix2": stix2_as,
                    "misp": misp_as,
                    "provider": provider,
                    "prefix": prefix,
                    "country": country,
                },
            }

            if as_node not in nodes:
                nodes.append(as_node)

            # Link IP to AS Node
            edges.append(
                {
                    "source": ip_val,
                    "target": as_val,
                    "relationship": "belongs-to-as",
                }
            )

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
