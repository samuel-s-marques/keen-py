from src.utils.print_utils import error, warn, success
from src.core.base_module import BaseModule


class EmailEnrichmentModule(BaseModule):
    metadata = {
        "name": "Email_Enrichment",
        "description": "Enriches an email address with additional information using Hunter.io and other sources.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "magic_consumes": ["email-addr"],
        "options": {
            "TARGET": ["", True, "The email address to lookup.", "email"],
            "HUNTER_IO_APIKEY": ["", False, "API Key for Hunter.io API.", ""],
        },
    }

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()

        await self.loading(f"Enriching email {target}...", self.execute, target)

    async def execute(self, email: str) -> None:
        person = await self.check_hunter_io(email)
        if person:
            await self._save_results(email, person)
        else:
            # Even with no enrichment data (e.g. no API key), persist the target
            # node so it appears in the workspace and magic chaining can proceed.
            from src.core.result_builder import ResultBuilder, NodeFactory

            builder = ResultBuilder()
            builder.add_node(NodeFactory.email(email))
            await self.post_run(builder.build())

    async def check_hunter_io(self, email: str) -> dict | None:
        api_key = self.options.get("HUNTER_IO_APIKEY")

        if not api_key:
            warn("Hunter.io API Key not found. Skipping Hunter.io enrichment.")
            return None

        try:
            async with self.get_http_client() as client:
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
        name_data = person.get("name", {})
        full_name = name_data.get("fullName", "Unknown")
        location = person.get("location", "Unknown")
        bio = person.get("bio")
        site = person.get("site")
        phone = person.get("phone")
        provider = person.get("emailProvider", "Unknown")

        # Main Info Panel
        self.render(
            self.result_panel(
                f"[bold cyan]Target:[/bold cyan] [bold white]{email}[/bold white]\n"
                f"[bold cyan]Name:[/bold cyan]   {full_name}\n"
                f"[bold cyan]Location:[/bold cyan] {location}",
                title="[bold green]Hunter.io Enrichment[/bold green]",
                kind="success",
            )
        )

        # Personal Details Table
        details_table = self.kv_table()

        if bio:
            details_table.add_row("Bio", bio)
        if site:
            details_table.add_row("Website", site)
        if phone:
            details_table.add_row("Phone", phone)
        details_table.add_row("Provider", provider)

        if details_table.row_count > 0:
            self.render(
                self.result_panel(
                    details_table,
                    title="[bold blue]Personal Details[/bold blue]",
                    kind="info",
                )
            )

        # Employment Information
        employment = person.get("employment", {})
        if employment and any(employment.values()):
            emp_table = self.results_table(
                columns=["Company", "Title", "Role", "Seniority"],
            )

            emp_table.add_row(
                employment.get("name") or "N/A",
                employment.get("title") or "N/A",
                employment.get("role") or "N/A",
                employment.get("seniority") or "N/A",
            )
            self.render(
                self.result_panel(
                    emp_table,
                    title="[bold yellow]Employment[/bold yellow]",
                    kind="warn",
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
            self.render(
                self.result_panel(
                    "\n".join(social_rows),
                    title="[bold magenta]Social Presence[/bold magenta]",
                    kind="info",
                )
            )

        success(f"Enrichment completed for {email}")

    async def _save_results(self, email: str, results: dict) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory

        name_data = results.get("name", {})
        full_name = name_data.get("fullName")
        first_name = name_data.get("firstName")
        last_name = name_data.get("lastName")
        bio = results.get("bio")
        location = results.get("location")
        phone = results.get("phone")
        site = results.get("site")
        provider = results.get("emailProvider")

        builder = ResultBuilder()
        builder.add_node(
            NodeFactory.email(
                email,
                full_name=full_name,
                first_name=first_name,
                last_name=last_name,
                bio=bio,
                location=location,
                provider=provider,
            )
        )

        # Employment
        employment = results.get("employment", {})
        company_name = employment.get("name")
        if company_name and company_name.strip():
            org_node = builder.add_node(
                NodeFactory.organization(
                    company_name,
                    title=employment.get("title"),
                    role=employment.get("role"),
                    seniority=employment.get("seniority"),
                )
            )
            # Override MISP type
            org_node["metadata"]["misp"] = {"type": "target-org", "value": company_name}
            builder.add_edge(email, company_name, "employed-by")

        # Location
        if location and location != "Unknown":
            builder.add_node(NodeFactory.location(location))
            builder.add_edge(email, location, "located-in")

        # Phone
        if phone:
            builder.add_node(NodeFactory.phone(phone))
            builder.add_edge(email, phone, "associated-phone")

        # Website
        if site:
            url_node = builder.add_node(NodeFactory.url(site))
            # Override MISP type to url
            url_node["metadata"]["misp"] = {"type": "url", "value": site}
            builder.add_edge(email, site, "associated-website")

        # Social Media Accounts
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
                acc_val = f"{s_type}:{handle}"
                acc_node = builder.add_node(
                    NodeFactory.user_account(
                        acc_val,
                        platform=s_type,
                        handle=handle,
                    )
                )
                # Override stix2/misp specifics
                acc_node["metadata"]["stix2"]["account_login"] = handle
                acc_node["metadata"]["stix2"]["account_type"] = s_type
                acc_node["metadata"]["misp"] = {"type": misp_type, "value": handle}
                builder.add_edge(email, acc_val, "owns-account")

        await self.post_run(builder.build())
