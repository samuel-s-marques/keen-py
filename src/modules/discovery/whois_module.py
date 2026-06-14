from typing import Any
from src.utils.rdap import query_rdap

from src.utils.print_utils import error
from src.core.base_module import BaseModule


class WhoisModule(BaseModule):
    metadata = {
        "name": "Whois",
        "description": "Retrieves registration details, expiration dates, and nameservers for a domain using RDAP.",
        "author": "Samuel Marques",
        "version": "1.1.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The domain name to lookup (e.g. google.com).",
                "domain",
            ],
        },
    }

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()

        await self.loading(f"Executing RDAP query on {target}...", self.execute, target)

    async def execute(self, target: str) -> None:
        try:
            async with self.get_http_client(follow_redirects=True, timeout=15) as client:
                w = await query_rdap(target, client=client)
            if w:
                self.display_whois_results(target, w)
                await self._save_results(target, w)
            else:
                error(f"RDAP lookup failed: No data retrieved for {target}")
        except Exception as e:
            error(f"RDAP lookup failed: {str(e)}")

    def display_whois_results(self, target: str, data: dict[str, Any]) -> None:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich import box
        from datetime import datetime

        console = Console()

        table = Table(box=box.HORIZONTALS, expand=True, show_header=False)
        table.add_column("Property", style="cyan", width=25)
        table.add_column("Details", style="white")

        def clean_val(v) -> str:
            if not v:
                return "Unknown"
            if isinstance(v, datetime):
                return v.strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(v, list):
                return ", ".join(clean_val(x) for x in v if x)
            return str(v).strip()

        # Extract major properties
        registrar = clean_val(data.get("registrar"))
        org = clean_val(data.get("org"))
        creation_date = clean_val(data.get("creation_date"))
        updated_date = clean_val(data.get("updated_date"))
        expiration_date = clean_val(data.get("expiration_date"))
        name_servers = clean_val(data.get("name_servers"))
        emails = clean_val(data.get("emails"))
        status = clean_val(data.get("status"))

        table.add_row("Registrar", registrar)
        table.add_row("Registrant Organization", org)
        table.add_row("Creation Date", creation_date)
        table.add_row("Updated Date", updated_date)
        table.add_row("Expiration Date", expiration_date)
        table.add_row("Name Servers", name_servers)
        table.add_row("Contact Emails", emails)
        table.add_row("Domain Status", status)

        if not getattr(self, "is_web_context", False):
            console.print(
                Panel(
                    table,
                    title=f"[bold cyan]RDAP Information: {target}[/bold cyan]",
                    border_style="cyan",
                    box=box.HEAVY,
                )
            )

    async def _save_results(self, target: str, results: dict) -> None:
        from datetime import datetime
        from src.core.result_builder import ResultBuilder, NodeFactory

        # Helper to convert datetime to string safely
        def format_date(d) -> str | None:
            if isinstance(d, datetime):
                return d.isoformat()
            if isinstance(d, list) and d:
                return format_date(d[0])
            if isinstance(d, str):
                return d
            return None

        # Helper to safely retrieve scalar or list as a clean string or list
        def get_clean_list(v) -> list[str]:
            if not v:
                return []
            if isinstance(v, list):
                return [str(x).strip().lower() for x in v if x]
            if isinstance(v, str):
                return [x.strip().lower() for x in v.split(",") if x.strip()]
            return [str(v).strip().lower()]

        def get_clean_str(v) -> str | None:
            if not v:
                return None
            if isinstance(v, list) and v:
                return str(v[0]).strip()
            return str(v).strip()

        # Retrieve values
        registrar = get_clean_str(results.get("registrar"))
        org = get_clean_str(results.get("org"))
        creation_date = format_date(results.get("creation_date"))
        updated_date = format_date(results.get("updated_date"))
        expiration_date = format_date(results.get("expiration_date"))
        emails = get_clean_list(results.get("emails"))
        name_servers = get_clean_list(results.get("name_servers"))

        builder = ResultBuilder()

        builder.add_node(
            NodeFactory.domain(
                target,
                creation_date=creation_date,
                updated_date=updated_date,
                expiration_date=expiration_date,
                registrar=registrar,
                registrant_org=org,
                name_servers=name_servers,
                emails=emails,
            )
        )

        # Registrar
        if registrar:
            builder.add_node(NodeFactory.organization(registrar))
            # Override MISP type
            reg_node = builder._nodes[-1]
            reg_node["metadata"]["misp"] = {"type": "registrar", "value": registrar}
            builder.add_edge(target, registrar, "registered-by")

        # Registrant Organization
        if org and org != registrar:
            builder.add_node(NodeFactory.organization(org))
            # Override MISP type
            org_node = builder._nodes[-1]
            org_node["metadata"]["misp"] = {"type": "registrar", "value": org}
            builder.add_edge(target, org, "registrant")

        # Name Servers
        for ns in name_servers:
            ns_cleaned = ns.rstrip(".")
            if not ns_cleaned:
                continue
            builder.add_node(NodeFactory.domain(ns_cleaned))
            builder.add_edge(target, ns_cleaned, "has-ns-record")

        # Contact Emails
        for email in emails:
            if not email:
                continue
            builder.add_node(NodeFactory.email(email))
            builder.add_edge(target, email, "has-contact-email")

        await self.post_run(builder.build())
