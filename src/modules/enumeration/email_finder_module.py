import httpx
from src.utils.print_utils import error, warn, info
from src.core.base_module import BaseModule
from src.utils.utils import get_bool
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box


class EmailFinderModule(BaseModule):
    metadata = {
        "name": "Email_Finder",
        "description": "Generates possible email addresses based on name and domain through multiple methods. Ranks them by probability and tests against common EmailVerification module.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "FNAME": ["", True, "First name of the target.", "name"],
            "LNAME": ["", True, "Last name of the target.", "name"],
            "DOMAIN": ["", True, "Domain name to generate emails for.", "domain"],
            "VERIFY": [
                "False",
                False,
                "Verify found emails using EmailVerification module.",
                "bool",
            ],
            "HUNTER_IO_APIKEY": ["", False, "API Key for Hunter.io API.", ""],
        },
    }

    async def run(self) -> None:
        if not self.pre_run():
            return

        first_name: str = self.options.get("FNAME", "").strip().lower()
        last_name: str = self.options.get("LNAME", "").strip().lower()
        domain: str = self.options.get("DOMAIN", "").strip().lower()
        verify: bool = get_bool(self.options.get("VERIFY", ""))

        # Try Hunter.io first
        hunter_data = await self.check_hunter_io(first_name, last_name, domain)

        if hunter_data and hunter_data.get("email"):
            await self.display_hunter_results(hunter_data)
            await self.save_hunter_results(hunter_data)
            return

        # Fallback to generated emails
        email_variations: list[str] = self.generate_emails(
            first_name, last_name, domain
        )

        if verify:
            emails_with_probability: dict[str, int] = await self.verify_emails(
                email_variations
            )
            await self.display_emails(emails_with_probability, with_probability=True)
            await self.save_results(list(emails_with_probability.keys()))
        else:
            emails_with_probability = {email: 0 for email in email_variations}
            await self.display_emails(emails_with_probability, with_probability=False)
            await self.save_results(email_variations)

    def generate_emails(
        self, first_name: str, last_name: str, domain: str
    ) -> list[str]:
        """Generates possible email addresses based on name and domain.

        Args:
            first_name (str): First name of the target.
            last_name (str): Last name of the target.
            domain (str): Domain name to generate emails for.

        Returns:
            list[str]: List of possible email addresses.
        """
        emails = []

        combinations = [
            f"{first_name}.{last_name}",
            f"{first_name}{last_name}",
            f"{first_name[0]}{last_name}",
            f"{first_name}.{last_name[0]}",
            f"{last_name}.{first_name}",
            f"{last_name}{first_name}",
            f"{last_name[0]}{first_name}",
            f"{last_name}.{first_name[0]}",
        ]

        for combination in combinations:
            emails.append(f"{combination}@{domain}")

        return emails

    async def check_hunter_io(
        self, first_name: str, last_name: str, domain: str
    ) -> dict | None:
        api_key = self.options.get("HUNTER_IO_APIKEY")

        if not api_key:
            warn("Hunter.io API Key not found. Skipping Hunter.io search.")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.hunter.io/v2/email-finder?domain={domain}&first_name={first_name}&last_name={last_name}&api_key={api_key}",
                    timeout=15,
                )

                if response.status_code != 200:
                    data = response.json()
                    error_resp = data.get("errors", [])
                    errors = (
                        "\n".join(
                            [f"{e.get('code')}: {e.get('details')}" for e in error_resp]
                        )
                        if error_resp
                        else str(response.status_code)
                    )
                    error(f"Error checking Hunter.io: {errors}")
                    return None

                data = response.json()
                return data.get("data")

        except Exception as e:
            error(f"Error checking Hunter.io: {str(e)}")
            return None

    async def display_hunter_results(self, data: dict) -> None:
        console = Console()

        email = data.get("email")
        score = data.get("score")
        company = data.get("company")
        position = data.get("position")

        content = f"[bold cyan]Email:[/bold cyan] [bold white]{email}[/bold white]\n"
        if score:
            content += f"[bold cyan]Score:[/bold cyan] {score}%\n"
        if company:
            content += f"[bold cyan]Company:[/bold cyan] {company}\n"
        if position:
            content += f"[bold cyan]Position:[/bold cyan] {position}\n"

        if not getattr(self, "is_web_context", False):
            console.print(
                Panel(
                    content.strip(),
                    title="[bold green]Hunter.io Results[/bold green]",
                    border_style="green",
                    box=box.ROUNDED,
                )
            )

    async def save_hunter_results(self, data: dict) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory

        builder = ResultBuilder()

        email = data.get("email")
        if not email:
            return

        first_name = data.get("first_name")
        last_name = data.get("last_name")
        score = data.get("score")
        sources = data.get("sources")

        # Add email node
        builder.add_node(
            NodeFactory.email(
                email,
                first_name=first_name,
                last_name=last_name,
            )
        )

        email_node = builder._nodes[-1]
        if score:
            email_node["metadata"]["score"] = score
        if sources:
            email_node["metadata"]["sources"] = sources

        # Company
        company = data.get("company")
        position = data.get("position")
        if company:
            builder.add_node(NodeFactory.organization(company, title=position))
            builder.add_edge(email, company, "employed-by")

        # Phone
        phone = data.get("phone_number")
        if phone:
            builder.add_node(NodeFactory.phone(phone))
            builder.add_edge(email, phone, "associated-phone")

        # Twitter
        twitter = data.get("twitter")
        if twitter:
            builder.add_node(
                NodeFactory.user_account(
                    f"twitter:{twitter}",
                    platform="twitter",
                    handle=twitter,
                )
            )
            builder.add_edge(email, f"twitter:{twitter}", "owns-account")

        # LinkedIn
        linkedin = data.get("linkedin_url")
        if linkedin:
            builder.add_node(
                NodeFactory.user_account(
                    f"linkedin:{linkedin}",
                    platform="linkedin",
                    handle=linkedin,
                )
            )
            builder.add_edge(email, f"linkedin:{linkedin}", "owns-account")

        await self.post_run(builder.build())

    async def display_emails(
        self, emails: dict[str, int], with_probability: bool = True
    ) -> None:
        console = Console()
        table = Table(
            title="[bold green]Generated Emails[/bold green]", box=box.ROUNDED
        )

        table.add_column("Email", style="cyan")
        if with_probability:
            table.add_column("Probability", style="magenta")

        if with_probability:
            sorted_emails = sorted(emails.items(), key=lambda x: x[1], reverse=True)
            for email, score in sorted_emails:
                table.add_row(email, f"{score}%")
        else:
            for email in emails:
                table.add_row(email)

        if not getattr(self, "is_web_context", False):
            console.print(table)

    async def verify_emails(self, emails: list[str]) -> dict[str, int]:
        """Verifies email addresses using EmailVerification module.

        Args:
            emails (list[str]): List of email addresses to verify.

        Returns:
            dict[str, int]: Dictionary of email addresses with their probabilities.
        """
        from src.modules.enumeration.email_verification_module import (
            EmailVerificationModule,
        )
        import asyncio

        module: EmailVerificationModule = EmailVerificationModule()
        results: dict[str, int] = {}

        info(f"Verifying {len(emails)} emails in parallel...")
        tasks = [module.execute(email, 10) for email in emails]
        results_list = await asyncio.gather(*tasks)

        for email, result in zip(emails, results_list):
            score: int = result.get("score", 0)
            results[email] = score

        return results

    async def save_results(self, emails: list[str]) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory

        builder = ResultBuilder()

        for email in emails:
            builder.add_node(NodeFactory.email(email))

        await self.post_run(builder.build())
