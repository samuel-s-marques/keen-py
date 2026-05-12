from typing import Any
import whois
import asyncio

from src.utils.print_utils import error
from src.core.base_module import BaseModule


class WhoisModule(BaseModule):
    metadata = {
        "name": "Whois",
        "description": "Retrieves registration details, expiration dates, and nameservers for a domain.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The domain name to lookup (e.g. google.com).",
                "domain",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        # Initialize options with default values
        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()

        await self.loading(
            f"Executing WHOIS query on {target}...", self.execute, target
        )

    async def execute(self, target: str) -> None:
        try:
            # Wrap in to_thread to prevent blocking the event loop on network sockets
            w: dict[str, Any] = await asyncio.to_thread(whois.whois, target)
            self.display_whois_results(target, w)
            await self._save_results(target, w)
        except Exception as e:
            error(f"WHOIS lookup failed: {str(e)}")

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

        console.print(
            Panel(
                table,
                title=f"[bold cyan]WHOIS Information: {target}[/bold cyan]",
                border_style="cyan",
                box=box.HEAVY,
            )
        )

    async def _save_results(self, target: str, results: dict) -> None:
        import uuid
        from datetime import datetime

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
                "creation_date": creation_date,
                "updated_date": updated_date,
                "expiration_date": expiration_date,
                "registrar": registrar,
                "registrant_org": org,
                "name_servers": name_servers,
                "emails": emails,
            },
        }

        nodes: list[dict[str, Any]] = [primary_node]
        edges: list[dict[str, Any]] = []

        # Namespaces for UUIDv5
        STIX_IDENTITY_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa3")
        STIX_EMAIL_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa2")

        # 1. Map Registrar
        if registrar:
            reg_uuid = uuid.uuid5(STIX_IDENTITY_NAMESPACE, registrar)
            stix2_reg = {
                "type": "identity",
                "id": f"identity--{reg_uuid}",
                "spec_version": "2.1",
                "name": registrar,
                "identity_class": "organization",
            }
            reg_node = {
                "type": "organization",
                "value": registrar,
                "metadata": {
                    "stix2": stix2_reg,
                    "misp": {"type": "registrar", "value": registrar},
                },
            }
            if reg_node not in nodes:
                nodes.append(reg_node)

            edges.append(
                {
                    "source": target,
                    "target": registrar,
                    "relationship": "registered-by",
                }
            )

        # 2. Map Registrant Organization
        if org and org != registrar:
            org_uuid = uuid.uuid5(STIX_IDENTITY_NAMESPACE, org)
            stix2_org = {
                "type": "identity",
                "id": f"identity--{org_uuid}",
                "spec_version": "2.1",
                "name": org,
                "identity_class": "organization",
            }
            org_node = {
                "type": "organization",
                "value": org,
                "metadata": {
                    "stix2": stix2_org,
                    "misp": {"type": "registrar", "value": org},
                },
            }
            if org_node not in nodes:
                nodes.append(org_node)

            edges.append(
                {
                    "source": target,
                    "target": org,
                    "relationship": "registrant",
                }
            )

        # 3. Map Name Servers
        for ns in name_servers:
            ns_cleaned = ns.rstrip(".")
            if not ns_cleaned:
                continue

            ns_uuid = uuid.uuid5(STIX_DOMAIN_NAMESPACE, ns_cleaned)
            stix2_ns = {
                "type": "domain-name",
                "id": f"domain-name--{ns_uuid}",
                "spec_version": "2.1",
                "value": ns_cleaned,
            }
            ns_node = {
                "type": "domain-name",
                "value": ns_cleaned,
                "metadata": {
                    "stix2": stix2_ns,
                    "misp": {"type": "domain", "value": ns_cleaned},
                },
            }
            if ns_node not in nodes:
                nodes.append(ns_node)

            edges.append(
                {
                    "source": target,
                    "target": ns_cleaned,
                    "relationship": "has-ns-record",
                }
            )

        # 4. Map Contact Emails
        for email in emails:
            if not email:
                continue

            email_uuid = uuid.uuid5(STIX_EMAIL_NAMESPACE, email)
            stix2_email = {
                "type": "email-addr",
                "id": f"email-addr--{email_uuid}",
                "spec_version": "2.1",
                "value": email,
            }
            email_node = {
                "type": "email-addr",
                "value": email,
                "metadata": {
                    "stix2": stix2_email,
                    "misp": {"type": "email-dst", "value": email},
                },
            }
            if email_node not in nodes:
                nodes.append(email_node)

            edges.append(
                {
                    "source": target,
                    "target": email,
                    "relationship": "has-contact-email",
                }
            )

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
