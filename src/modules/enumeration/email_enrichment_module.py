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
        await self.check_hunter_io(email)

    async def check_hunter_io(self, email: str) -> None:
        api_key = self.options.get("HUNTER_IO_APIKEY")

        if not api_key:
            warn("Hunter.io API Key not found. Skipping Hunter.io enrichment.")
            return

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
                    return

                data = r.json()
                person = data.get("data", {})

                if not person:
                    warn(f"No information found for {email} with Hunter.io.")
                    return

                self.display_hunter_results(email, person)

        except Exception as e:
            error(f"Error checking {email} with Hunter.io: {str(e)}")

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
