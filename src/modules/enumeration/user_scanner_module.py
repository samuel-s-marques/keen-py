from user_scanner.core.result import Result
from src.utils.validator import InputValidator
from typing import Any
from user_scanner.core import engine as us_engine

from src.utils.print_utils import error, success
from src.core.base_module import BaseModule


class UserScannerModule(BaseModule):
    metadata = {
        "name": "User_Scanner",
        "description": "Checks for usernames and emails on various platforms.",
        "author": "Samuel Marques",
        "version": "1.1.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The target to lookup.",
                "email,username",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET"))
        await self.loading(
            f"Executing user_scanner scan on {target}...", self.execute, target
        )

    async def execute(self, target: str) -> None:
        import json

        is_email: bool = InputValidator.is_valid_email(target)

        self.logger.debug(
            f"Starting user_scanner check for target: {target} (is_email: {is_email})"
        )
        results: list[Result] = await us_engine.check_all(target, is_email)

        self.logger.debug(f"Scan complete. Found {len(results)} total results.")

        # Filter for registered accounts only
        # Status can be 'Registered' (email) or 'Found' (username)
        registered_results = []
        for res in results:
            res_dict = json.loads(res.to_json())
            status = res_dict.get("status")

            if status in ["Registered", "Found"]:
                registered_results.append(res_dict)

        self.logger.debug(f"Filtered {len(registered_results)} registered results.")

        if registered_results:
            success(f"Found {len(registered_results)} registrations for {target}")
            self.display_results(target, registered_results)
        else:
            error(f"No registrations found for target '{target}'.")

        await self._save_results(target, registered_results)

    def display_results(self, target: str, results: list) -> None:
        from rich.console import Console
        from rich.table import Table
        from rich import box

        console = Console()
        table = Table(
            title=f"User Scanner Results: [bold cyan]{target}[/bold cyan]",
            box=box.ROUNDED,
            expand=True,
            show_lines=True,
            header_style="bold blue",
        )

        table.add_column("Site Name", style="cyan bold", width=20)
        table.add_column("Category", style="magenta")
        table.add_column("URL", style="green underline")
        table.add_column("Details", style="white", overflow="fold")

        for item in results:
            site_name = item.get("site_name", "Unknown")
            category = item.get("category", "Unknown")
            url = item.get("url", "N/A")
            extra = item.get("extra", "").strip()

            table.add_row(site_name, category, url, extra)

        console.print(table)

    async def _save_results(self, target: str, results: list) -> None:
        import uuid

        is_email = InputValidator.is_valid_email(target)

        # Standard Namespaces
        STIX_EMAIL_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa2")
        STIX_ACCOUNT_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa6")
        STIX_IDENTITY_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa3")

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        if is_email:
            target_uuid = uuid.uuid5(STIX_EMAIL_NAMESPACE, target)
            primary_node = {
                "type": "email-addr",
                "value": target,
                "metadata": {
                    "stix2": {
                        "type": "email-addr",
                        "id": f"email-addr--{target_uuid}",
                        "spec_version": "2.1",
                        "value": target,
                    },
                    "misp": {"type": "email-dst", "value": target},
                },
            }
        else:
            target_uuid = uuid.uuid5(STIX_ACCOUNT_NAMESPACE, target)
            primary_node = {
                "type": "user-account",
                "value": target,
                "metadata": {
                    "stix2": {
                        "type": "user-account",
                        "id": f"user-account--{target_uuid}",
                        "spec_version": "2.1",
                        "user_id": target,
                    },
                    "misp": {"type": "github-username", "value": target},
                },
            }

        nodes.append(primary_node)

        for item in results:
            site_name = item.get("site_name", "Unknown")
            url = item.get("url", "")
            category = item.get("category", "")
            extra = item.get("extra", "")

            # Create Organization Node for the site
            org_uuid = uuid.uuid5(STIX_IDENTITY_NAMESPACE, site_name)
            org_node = {
                "type": "organization",
                "value": site_name,
                "metadata": {
                    "stix2": {
                        "type": "identity",
                        "id": f"identity--{org_uuid}",
                        "spec_version": "2.1",
                        "name": site_name,
                        "identity_class": "organization",
                    },
                    "misp": {"type": "text", "value": site_name},
                    "category": category,
                },
            }
            if org_node not in nodes:
                nodes.append(org_node)

            # Create User Account Node on that site
            account_id_str = f"{site_name}:{target}"
            account_uuid = uuid.uuid5(STIX_ACCOUNT_NAMESPACE, account_id_str)

            account_node = {
                "type": "user-account",
                "value": account_id_str,
                "metadata": {
                    "stix2": {
                        "type": "user-account",
                        "id": f"user-account--{account_uuid}",
                        "spec_version": "2.1",
                        "user_id": target,
                        "display_name": f"{target} on {site_name}",
                        "account_type": "social-media",
                        "x_profile_url": url,
                        "description": extra,
                    },
                    "misp": {"type": "link", "value": url},
                    "site": site_name,
                    "profile_url": url,
                    "details": extra,
                },
            }
            if account_node not in nodes:
                nodes.append(account_node)

            # Edges
            edges.append(
                {
                    "source": target,
                    "target": account_id_str,
                    "relationship": "owns-account",
                }
            )

            edges.append(
                {
                    "source": account_id_str,
                    "target": site_name,
                    "relationship": "registered-on",
                }
            )

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
