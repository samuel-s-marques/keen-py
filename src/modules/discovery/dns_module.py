import asyncio
import dns.resolver
from rich.table import Table
from rich.console import Console

from src.utils.print_utils import info, success
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
        else:
            info(f"No DNS records found for {target}.")
