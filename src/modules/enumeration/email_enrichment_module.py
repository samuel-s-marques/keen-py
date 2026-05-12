from typing import Any
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from src.utils.print_utils import error, warn, success
from src.core.base_module import BaseModule


class EmailEnrichmentModule(BaseModule):
    metadata = {
        "name": "Email_Enrichment",
        "description": "Enriches an email address with additional information using Hunter.io and other sources.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": ["", True, "The email address to lookup.", "email"],
            "HUNTER_IO_APIKEY": ["", False, "API Key for Hunter.io API.", ""],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()

        await self.loading(f"Enriching email {target}...", self.execute, target)

    async def execute(self, email: str) -> None:
        person = await self.check_hunter_io(email)
        if person:
            await self._save_results(email, person)

    async def check_hunter_io(self, email: str) -> dict | None:
        api_key = self.options.get("HUNTER_IO_APIKEY")

        if not api_key:
            warn("Hunter.io API Key not found. Skipping Hunter.io enrichment.")
            return None

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://api.hunter.io/v2/people/find?email={email}&api_key={api_key}",
                    timeout=15,
                )

                if r.status_code != 200:
                    data = r.json()
                    error_resp = data.get("errors", [])
                    errors = (
                        "\n".join(
                            [f"{e.get('code')}: {e.get('details')}" for e in error_resp]
                        )
                        if error_resp
                        else str(r.status_code)
                    )
                    error(f"Error checking {email} with Hunter.io: {errors}")
                    return None

                data = r.json()
                person = data.get("data", {})

                if not person:
                    warn(f"No information found for {email} with Hunter.io.")
                    return None

                self.display_hunter_results(email, person)
                return person

        except Exception as e:
            error(f"Error checking {email} with Hunter.io: {str(e)}")
            return None

    def display_hunter_results(self, email: str, person: dict) -> None:
        console = Console()

        name_data = person.get("name", {})
        full_name = name_data.get("fullName", "Unknown")
        location = person.get("location", "Unknown")
        bio = person.get("bio")
        site = person.get("site")
        phone = person.get("phone")
        provider = person.get("emailProvider", "Unknown")

        # Main Info Panel
        console.print(
            Panel(
                f"[bold cyan]Target:[/bold cyan] [bold white]{email}[/bold white]\n"
                f"[bold cyan]Name:[/bold cyan]   {full_name}\n"
                f"[bold cyan]Location:[/bold cyan] {location}",
                title="[bold green]Hunter.io Enrichment[/bold green]",
                border_style="green",
                box=box.ROUNDED,
            )
        )

        # Personal Details Table
        details_table = Table(box=box.SIMPLE, show_header=False, expand=True)
        details_table.add_column("Key", style="cyan", width=15)
        details_table.add_column("Value", style="white")

        if bio:
            details_table.add_row("Bio", bio)
        if site:
            details_table.add_row("Website", site)
        if phone:
            details_table.add_row("Phone", phone)
        details_table.add_row("Provider", provider)

        if details_table.row_count > 0:
            console.print(
                Panel(
                    details_table,
                    title="[bold blue]Personal Details[/bold blue]",
                    border_style="blue",
                )
            )

        # Employment Information
        employment = person.get("employment", {})
        if employment and any(employment.values()):
            emp_table = Table(box=box.HORIZONTALS, expand=True)
            emp_table.add_column("Company", style="yellow")
            emp_table.add_column("Title", style="white")
            emp_table.add_column("Role", style="magenta")
            emp_table.add_column("Seniority", style="cyan")

            emp_table.add_row(
                employment.get("name") or "N/A",
                employment.get("title") or "N/A",
                employment.get("role") or "N/A",
                employment.get("seniority") or "N/A",
            )
            console.print(
                Panel(
                    emp_table,
                    title="[bold yellow]Employment[/bold yellow]",
                    border_style="yellow",
                )
            )

        # Social Media Presence
        social_types = [
            "facebook",
            "github",
            "twitter",
            "linkedin",
            "googleplus",
            "gravatar",
        ]
        social_rows = []
        for s_type in social_types:
            handle = person.get(s_type, {}).get("handle")
            if handle:
                social_rows.append(f"[bold]{s_type.capitalize()}:[/bold] {handle}")

        if social_rows:
            console.print(
                Panel(
                    "\n".join(social_rows),
                    title="[bold magenta]Social Presence[/bold magenta]",
                    border_style="magenta",
                    box=box.ROUNDED,
                )
            )

        success(f"Enrichment completed for {email}")

    async def _save_results(self, email: str, results: dict) -> None:
        import uuid

        # STIX 2.1 Standard Email-Address Object
        STIX_EMAIL_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa2")
        email_uuid = uuid.uuid5(STIX_EMAIL_NAMESPACE, email)

        stix2_email = {
            "type": "email-addr",
            "id": f"email-addr--{email_uuid}",
            "spec_version": "2.1",
            "value": email,
        }

        # MISP representation
        misp_email = {
            "type": "email-dst",
            "value": email,
        }

        # General target personal details
        name_data = results.get("name", {})
        full_name = name_data.get("fullName")
        first_name = name_data.get("firstName")
        last_name = name_data.get("lastName")
        bio = results.get("bio")
        location = results.get("location")
        phone = results.get("phone")
        site = results.get("site")
        provider = results.get("emailProvider")

        primary_node = {
            "type": "email-addr",
            "value": email,
            "metadata": {
                "stix2": stix2_email,
                "misp": misp_email,
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "bio": bio,
                "location": location,
                "provider": provider,
            },
        }

        nodes: list[dict[str, Any]] = [primary_node]
        edges: list[dict[str, Any]] = []

        # Employment Mapping (Organization Node)
        employment = results.get("employment", {})
        company_name = employment.get("name")
        if company_name and company_name.strip():
            # Build STIX 2.1 Identity (Organization) Object
            STIX_IDENTITY_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa3")
            org_uuid = uuid.uuid5(STIX_IDENTITY_NAMESPACE, company_name)
            stix2_org = {
                "type": "identity",
                "id": f"identity--{org_uuid}",
                "spec_version": "2.1",
                "name": company_name,
                "identity_class": "organization",
            }
            misp_org = {
                "type": "target-org",
                "value": company_name,
            }
            org_node = {
                "type": "organization",
                "value": company_name,
                "metadata": {
                    "stix2": stix2_org,
                    "misp": misp_org,
                    "title": employment.get("title"),
                    "role": employment.get("role"),
                    "seniority": employment.get("seniority"),
                },
            }
            nodes.append(org_node)
            edges.append(
                {
                    "source": email,
                    "target": company_name,
                    "relationship": "employed-by",
                }
            )

        # Location Mapping (Location Node)
        if location and location != "Unknown":
            STIX_LOCATION_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa4")
            loc_uuid = uuid.uuid5(STIX_LOCATION_NAMESPACE, location)
            stix2_loc = {
                "type": "location",
                "id": f"location--{loc_uuid}",
                "spec_version": "2.1",
                "name": location,
            }
            misp_loc = {
                "type": "target-location",
                "value": location,
            }
            loc_node = {
                "type": "location",
                "value": location,
                "metadata": {
                    "stix2": stix2_loc,
                    "misp": misp_loc,
                },
            }
            nodes.append(loc_node)
            edges.append(
                {
                    "source": email,
                    "target": location,
                    "relationship": "located-in",
                }
            )

        # Phone Mapping (x-phone-number Node)
        if phone:
            STIX_PHONE_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa1")
            phone_uuid = uuid.uuid5(STIX_PHONE_NAMESPACE, phone)
            stix2_phone = {
                "type": "x-phone-number",
                "id": f"x-phone-number--{phone_uuid}",
                "spec_version": "2.1",
                "value": phone,
            }
            misp_phone = {
                "type": "phone-number",
                "value": phone,
            }
            phone_node = {
                "type": "x-phone-number",
                "value": phone,
                "metadata": {
                    "stix2": stix2_phone,
                    "misp": misp_phone,
                },
            }
            nodes.append(phone_node)
            edges.append(
                {
                    "source": email,
                    "target": phone,
                    "relationship": "associated-phone",
                }
            )

        # Website Mapping (url Node)
        if site:
            STIX_URL_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa5")
            url_uuid = uuid.uuid5(STIX_URL_NAMESPACE, site)
            stix2_url = {
                "type": "url",
                "id": f"url--{url_uuid}",
                "spec_version": "2.1",
                "value": site,
            }
            misp_url = {
                "type": "url",
                "value": site,
            }
            url_node = {
                "type": "url",
                "value": site,
                "metadata": {
                    "stix2": stix2_url,
                    "misp": misp_url,
                },
            }
            nodes.append(url_node)
            edges.append(
                {
                    "source": email,
                    "target": site,
                    "relationship": "associated-website",
                }
            )

        # Social Media Accounts Mapping
        social_types = {
            "facebook": "facebook-id",
            "github": "github-username",
            "twitter": "twitter-id",
            "linkedin": "linkedin-url",
            "googleplus": "text",
            "gravatar": "text",
        }
        for s_type, misp_type in social_types.items():
            handle = results.get(s_type, {}).get("handle")
            if handle:
                STIX_ACCOUNT_NAMESPACE = uuid.UUID(
                    "f070f381-8b38-5fdf-9730-802526e84fa6"
                )
                acc_uuid = uuid.uuid5(STIX_ACCOUNT_NAMESPACE, f"{s_type}:{handle}")
                stix2_acc = {
                    "type": "user-account",
                    "id": f"user-account--{acc_uuid}",
                    "spec_version": "2.1",
                    "account_login": handle,
                    "account_type": s_type,
                }
                misp_acc = {
                    "type": misp_type,
                    "value": handle,
                }
                acc_node = {
                    "type": "user-account",
                    "value": f"{s_type}:{handle}",
                    "metadata": {
                        "stix2": stix2_acc,
                        "misp": misp_acc,
                        "platform": s_type,
                        "handle": handle,
                    },
                }
                nodes.append(acc_node)
                edges.append(
                    {
                        "source": email,
                        "target": f"{s_type}:{handle}",
                        "relationship": "owns-account",
                    }
                )

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
