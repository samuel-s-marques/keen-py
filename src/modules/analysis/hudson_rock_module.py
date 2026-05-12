import httpx
from typing import Any
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

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()

        await self.loading(f"Checking {target}...", self.execute, target)

    async def execute(self, email: str) -> None:
        try:
            async with httpx.AsyncClient() as client:
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

            console.print(
                Panel(
                    stealer_table,
                    title=f"[bold yellow]Infection #{index}[/bold yellow]",
                    border_style="yellow",
                )
            )

    async def _save_results(self, target: str, results: dict) -> None:
        import uuid

        stealers = results.get("stealers", [])

        # STIX 2.1 Standard Email-Address Object
        STIX_EMAIL_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa2")
        email_uuid = uuid.uuid5(STIX_EMAIL_NAMESPACE, target)

        stix2_email = {
            "type": "email-addr",
            "id": f"email-addr--{email_uuid}",
            "spec_version": "2.1",
            "value": target,
        }

        misp_email = {
            "type": "email-dst",
            "value": target,
        }

        primary_node = {
            "type": "email-addr",
            "value": target,
            "metadata": {
                "stix2": stix2_email,
                "misp": misp_email,
                "message": results.get("message"),
                "total_corporate_services": results.get("total_corporate_services", 0),
                "total_user_services": results.get("total_user_services", 0),
                "infections_count": len(stealers),
            },
        }

        nodes: list[dict[str, Any]] = [primary_node]
        edges: list[dict[str, Any]] = []

        # Namespaces for UUIDv5
        STIX_DEVICE_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa9")
        STIX_IP_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa0")

        for index, stealer in enumerate(stealers, start=1):
            comp_name = stealer.get("computer_name", "Unknown")
            date_comp = stealer.get("date_compromised", "Unknown")
            os_name = stealer.get("operating_system", "Unknown")
            mal_path = stealer.get("malware_path", "Unknown")
            ip_val = stealer.get("ip", "Unknown")
            passwords = stealer.get("top_passwords", [])
            logins = stealer.get("top_logins", [])

            device_val = f"infected-device:{target}:{comp_name}:{date_comp}"
            device_uuid = uuid.uuid5(STIX_DEVICE_NAMESPACE, device_val)

            # STIX 2.1 Custom infostealer-infection Object
            stix2_device = {
                "type": "x-infected-device",
                "id": f"x-infected-device--{device_uuid}",
                "spec_version": "2.1",
                "computer_name": comp_name,
                "date_compromised": date_comp,
                "operating_system": os_name,
                "malware_path": mal_path,
                "ip_address": ip_val if ip_val != "Unknown" else None,
                "top_passwords": passwords,
                "top_logins": logins,
            }

            misp_device = {
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

            device_node = {
                "type": "x-infected-device",
                "value": device_val,
                "metadata": {
                    "stix2": stix2_device,
                    "misp": misp_device,
                    "computer_name": comp_name,
                    "date_compromised": date_comp,
                    "operating_system": os_name,
                    "malware_path": mal_path,
                    "top_passwords": passwords,
                    "top_logins": logins,
                },
            }

            if device_node not in nodes:
                nodes.append(device_node)

            edges.append(
                {
                    "source": target,
                    "target": device_val,
                    "relationship": "compromised-device",
                }
            )

            # Map IP Node if present and valid
            if ip_val and ip_val != "Unknown":
                ip_uuid = uuid.uuid5(STIX_IP_NAMESPACE, ip_val)
                stix2_ip = {
                    "type": "ipv4-addr",
                    "id": f"ipv4-addr--{ip_uuid}",
                    "spec_version": "2.1",
                    "value": ip_val,
                }
                ip_node = {
                    "type": "ipv4-addr",
                    "value": ip_val,
                    "metadata": {
                        "stix2": stix2_ip,
                        "misp": {"type": "ip-src", "value": ip_val},
                    },
                }
                if ip_node not in nodes:
                    nodes.append(ip_node)

                edges.append(
                    {
                        "source": device_val,
                        "target": ip_val,
                        "relationship": "had-ip",
                    }
                )

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
