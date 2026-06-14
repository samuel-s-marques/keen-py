from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from src.utils.user_agents import UserAgents
from src.utils.print_utils import error, success
from src.core.base_module import BaseModule


class HudsonRockModule(BaseModule):
    metadata = {
        "name": "Hudson_Rock",
        "description": "Checks if email is associated with devices from infostealers.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": ["", True, "The email address to lookup.", "email"],
        },
    }

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()

        await self.loading(f"Checking {target}...", self.execute, target)

    async def execute(self, email: str) -> None:
        try:
            async with self.get_http_client() as client:
                r = await client.get(
                    f"https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email?email={email}",
                    headers={
                        "User-Agent": UserAgents.get(),
                    },
                    timeout=15,
                )

                if r.status_code != 200:
                    error(f"Error checking Hudson Rock: {r.status_code}")
                    return

                data = r.json()
                self.display_hudson_rock_results(email, data)
                await self._save_results(email, data)

        except Exception as e:
            error(f"Error checking Hudson Rock: {e}")

    def display_hudson_rock_results(self, email: str, data: dict) -> None:
        console = Console()

        message = data.get("message")
        stealers = data.get("stealers", [])

        if not stealers:
            success(f"No infostealer infections found for {email}.")
            return

        # Main Warning Panel
        if not getattr(self, "is_web_context", False):
            console.print(
                Panel(
                    f"[bold red]WARNING: Information Stealer Infection Detected![/bold red]\n\n"
                    f"[white]{message}[/white]",
                    title=f"[bold red]Hudson Rock: {email}[/bold red]",
                    border_style="red",
                    box=box.HEAVY,
                )
            )

        # Summary Table
        summary_table = Table(box=box.SIMPLE, show_header=False, expand=True)
        summary_table.add_column("Key", style="cyan", width=30)
        summary_table.add_column("Value", style="white")

        summary_table.add_row("Total Stealers Found", str(len(stealers)))
        summary_table.add_row(
            "Total Corporate Services Affected",
            str(data.get("total_corporate_services", 0)),
        )
        summary_table.add_row(
            "Total User Services Affected", str(data.get("total_user_services", 0))
        )

        if not getattr(self, "is_web_context", False):
            console.print(
                Panel(
                    summary_table,
                    title="[bold blue]Overall Summary[/bold blue]",
                    border_style="blue",
                )
            )

        # Detail Stealers
        for index, stealer in enumerate(stealers, start=1):
            stealer_table = Table(box=box.HORIZONTALS, expand=True)
            stealer_table.add_column("Property", style="cyan", width=25)
            stealer_table.add_column("Details", style="white")

            stealer_table.add_row(
                "Date Compromised", stealer.get("date_compromised", "Unknown")
            )
            stealer_table.add_row(
                "Computer Name", stealer.get("computer_name", "Unknown")
            )
            stealer_table.add_row(
                "Operating System", stealer.get("operating_system", "Unknown")
            )
            stealer_table.add_row(
                "Malware Path", stealer.get("malware_path", "Unknown")
            )
            stealer_table.add_row("IP Address", stealer.get("ip", "Unknown"))

            # Passwords and Logins
            top_passwords = (
                ", ".join(p for p in stealer.get("top_passwords", []) if p) or "None"
            )
            top_logins = (
                ", ".join(l for l in stealer.get("top_logins", []) if l) or "None"
            )

            stealer_table.add_row("Top Passwords (Masked)", top_passwords)
            stealer_table.add_row("Top Logins", top_logins)

            if not getattr(self, "is_web_context", False):
                console.print(
                    Panel(
                        stealer_table,
                        title=f"[bold yellow]Infection #{index}[/bold yellow]",
                        border_style="yellow",
                    )
                )

    async def _save_results(self, target: str, results: dict) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory, STIXNamespaces

        stealers = results.get("stealers", [])

        builder = ResultBuilder()
        builder.add_node(
            NodeFactory.email(
                target,
                message=results.get("message"),
                total_corporate_services=results.get("total_corporate_services", 0),
                total_user_services=results.get("total_user_services", 0),
                infections_count=len(stealers),
            )
        )

        for index, stealer in enumerate(stealers, start=1):
            comp_name = stealer.get("computer_name", "Unknown")
            date_comp = stealer.get("date_compromised", "Unknown")
            os_name = stealer.get("operating_system", "Unknown")
            mal_path = stealer.get("malware_path", "Unknown")
            ip_val = stealer.get("ip", "Unknown")
            passwords = stealer.get("top_passwords", [])
            logins = stealer.get("top_logins", [])

            device_val = f"infected-device:{comp_name}:{date_comp}"

            builder.add_node(
                NodeFactory.custom(
                    "x-infected-device",
                    device_val,
                    namespace=STIXNamespaces.DEVICE,
                    stix2_extra={
                        "computer_name": comp_name,
                        "date_compromised": date_comp,
                        "operating_system": os_name,
                        "malware_path": mal_path,
                        "ip_address": ip_val if ip_val != "Unknown" else None,
                    },
                    misp_type="stealer-infection",
                    computer_name=comp_name,
                    date_compromised=date_comp,
                    operating_system=os_name,
                    malware_path=mal_path,
                )
            )
            # Override MISP with structured attributes
            device_node = builder._nodes[-1]
            device_node["metadata"]["misp"] = {
                "type": "stealer-infection",
                "attributes": [
                    {
                        "type": "text",
                        "value": comp_name,
                        "object_relation": "computer-name",
                    },
                    {
                        "type": "text",
                        "value": date_comp,
                        "object_relation": "date-compromised",
                    },
                    {
                        "type": "text",
                        "value": os_name,
                        "object_relation": "operating-system",
                    },
                    {
                        "type": "filename",
                        "value": mal_path,
                        "object_relation": "malware-path",
                    },
                ],
            }

            builder.add_edge(
                target,
                device_val,
                "compromised-device",
                metadata={
                    "top_passwords": passwords,
                    "top_logins": logins,
                },
            )

            # IP node if present
            if ip_val and ip_val != "Unknown":
                builder.add_node(NodeFactory.ip(ip_val))
                # Override MISP type to ip-src
                ip_node = builder._nodes[-1]
                ip_node["metadata"]["misp"] = {"type": "ip-src", "value": ip_val}

                builder.add_edge(device_val, ip_val, "had-ip")

        await self.post_run(builder.build())
