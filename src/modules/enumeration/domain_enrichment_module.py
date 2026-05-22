import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from src.utils.print_utils import error, warn, success
from src.core.base_module import BaseModule


class DomainEnrichmentModule(BaseModule):
    metadata = {
        "name": "Domain_Enrichment",
        "description": "Enriches a domain with company information from Hunter.io.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": ["", True, "The domain to enrich.", "domain"],
            "HUNTER_IO_APIKEY": ["", False, "API Key for Hunter.io API.", ""],
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self.results = {}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()

        await self.loading(f"Enriching {target}...", self.execute, target)

        await self._save_results(target)

    async def execute(self, target: str) -> None:
        company = await self.check_hunter_io(target)
        self.results = company if company else {}
        if company:
            self.display_hunter_results(target, company)

    async def check_hunter_io(self, domain: str) -> dict | None:
        api_key = self.options.get("HUNTER_IO_APIKEY")

        if not api_key:
            warn("Hunter.io API Key not found. Skipping Hunter.io enrichment.")
            return None

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://api.hunter.io/v2/companies/find?domain={domain}&api_key={api_key}",
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
                    error(f"Error checking {domain} with Hunter.io: {errors}")
                    return None

                data = r.json()
                company = data.get("data", {})

                if not company:
                    warn(f"No information found for {domain} with Hunter.io.")
                    return None

                return company
        except Exception as e:
            error(f"Error checking {domain} with Hunter.io: {str(e)}")
            return None

    def display_hunter_results(self, target: str, company: dict) -> None:
        if getattr(self, "is_web_context", False):
            return

        console = Console()

        name = company.get("name") or company.get("legalName") or "Unknown"
        description = company.get("description") or "No description available."
        location = company.get("location") or "Unknown"
        founded = company.get("foundedYear") or "Unknown"
        company_type = company.get("company_type") or company.get("type") or "Unknown"
        email_provider = company.get("emailProvider") or "Unknown"
        phone = company.get("phone") or "Unknown"

        # Main Info Panel
        info_text = (
            f"[bold cyan]Domain:[/bold cyan]       [bold white]{target}[/bold white]\n"
            f"[bold cyan]Company Name:[/bold cyan] {name}\n"
            f"[bold cyan]Location:[/bold cyan]     {location}\n"
            f"[bold cyan]Founded:[/bold cyan]      {founded}\n"
            f"[bold cyan]Type:[/bold cyan]         {company_type}\n"
            f"[bold cyan]Description:[/bold cyan]  {description}"
        )
        console.print(
            Panel(
                info_text,
                title="[bold green]Hunter.io Domain Enrichment[/bold green]",
                border_style="green",
                box=box.ROUNDED,
            )
        )

        # Details Table
        details_table = Table(box=box.SIMPLE, show_header=False, expand=True)
        details_table.add_column("Key", style="cyan", width=20)
        details_table.add_column("Value", style="white")

        details_table.add_row("Email Provider", email_provider)
        details_table.add_row("Phone", phone)

        # Category
        category = company.get("category", {})
        category_parts = [
            category.get("sector"),
            category.get("industryGroup"),
            category.get("industry"),
            category.get("subIndustry"),
        ]
        category_str = " -> ".join([c for c in category_parts if c])
        if category_str:
            details_table.add_row("Industry Category", category_str)

        # Metrics
        metrics = company.get("metrics", {})
        emp_range = metrics.get("employees")
        if emp_range:
            details_table.add_row("Employees", emp_range)
        traffic = metrics.get("trafficRank")
        if traffic:
            details_table.add_row("Traffic Rank", str(traffic))
        revenue = metrics.get("annualRevenue") or metrics.get("estimatedAnnualRevenue")
        if revenue:
            details_table.add_row("Annual Revenue", str(revenue))

        # Tags
        tags = company.get("tags", [])
        if tags:
            details_table.add_row("Tags", ", ".join(tags))

        console.print(
            Panel(
                details_table,
                title="[bold blue]Company Details[/bold blue]",
                border_style="blue",
            )
        )

        # Tech Stack Panel
        tech_list = company.get("tech", [])
        if tech_list:
            tech_str = ", ".join(tech_list)
            console.print(
                Panel(
                    tech_str,
                    title="[bold yellow]Technologies Tracked[/bold yellow]",
                    border_style="yellow",
                    box=box.ROUNDED,
                )
            )

        # Social Presence
        social_rows = []
        for platform in ["facebook", "linkedin", "twitter", "crunchbase", "instagram"]:
            handle = company.get(platform, {}).get("handle")
            if handle:
                social_rows.append(f"[bold]{platform.capitalize()}:[/bold] {handle}")

        if social_rows:
            console.print(
                Panel(
                    "\n".join(social_rows),
                    title="[bold magenta]Social Presence[/bold magenta]",
                    border_style="magenta",
                    box=box.ROUNDED,
                )
            )

        # Associated Emails & Phones
        site_info = company.get("site", {})
        emails = site_info.get("emailAddresses", [])
        phones = site_info.get("phoneNumbers", [])

        if emails or phones:
            contact_table = Table(box=box.SIMPLE, expand=True)
            contact_table.add_column("Type", style="cyan", width=15)
            contact_table.add_column("Value", style="white")

            for p in phones:
                contact_table.add_row("Phone", p)
            for e in emails:
                contact_table.add_row("Email", e)

            console.print(
                Panel(
                    contact_table,
                    title="[bold cyan]Associated Contacts[/bold cyan]",
                    border_style="cyan",
                )
            )

        success(f"Enrichment completed for {target}")

    async def _save_results(self, target: str) -> None:
        if not self.results:
            return

        from src.core.result_builder import ResultBuilder, NodeFactory

        builder = ResultBuilder()
        builder.add_node(NodeFactory.domain(target))

        company = self.results
        name = company.get("name") or company.get("legalName")

        if name:
            builder.add_node(
                NodeFactory.organization(
                    name,
                    description=company.get("description"),
                    founded_year=company.get("foundedYear"),
                    company_type=company.get("company_type") or company.get("type"),
                )
            )
            builder.add_edge(name, target, "owns")

        # Location
        location = company.get("location")
        if location and location != "Unknown":
            builder.add_node(NodeFactory.location(location))
            builder.add_edge(target, location, "located-in")

        # Associated Phones
        site_info = company.get("site", {})
        phones = set(site_info.get("phoneNumbers", []))
        main_phone = company.get("phone")
        if main_phone:
            phones.add(main_phone)

        for phone in phones:
            if phone:
                builder.add_node(NodeFactory.phone(phone))
                builder.add_edge(target, phone, "associated-phone")

        # Associated Emails
        emails = site_info.get("emailAddresses", [])
        for email in emails:
            if email:
                builder.add_node(NodeFactory.email(email))
                builder.add_edge(email, target, "belongs-to-domain")

        # Social Media Accounts
        social_types = {
            "facebook": "facebook-id",
            "twitter": "twitter-id",
            "linkedin": "linkedin-url",
            "instagram": "text",
            "crunchbase": "text",
        }
        for s_type, misp_type in social_types.items():
            handle = company.get(s_type, {}).get("handle")
            if handle:
                acc_val = f"{s_type}:{handle}"
                builder.add_node(
                    NodeFactory.user_account(
                        acc_val,
                        platform=s_type,
                        handle=handle,
                    )
                )
                acc_node = builder._nodes[-1]
                acc_node["metadata"]["stix2"]["account_login"] = handle
                acc_node["metadata"]["stix2"]["account_type"] = s_type
                acc_node["metadata"]["misp"] = {"type": misp_type, "value": handle}
                builder.add_edge(target, acc_val, "owns-account")

        await self.post_run(builder.build())
