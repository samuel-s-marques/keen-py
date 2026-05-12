import asyncio

from src.utils.print_utils import error, info
from src.core.base_module import BaseModule


class SherlockModule(BaseModule):
    metadata = {
        "name": "Sherlock",
        "description": "Searches for a username on the internet, using the Sherlock tool.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The target to lookup (username, name, domain, etc).",
                "",
            ]
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
            f"Executing Sherlock scan on {target}...", self.sherlock, target
        )

    async def sherlock(self, target: str, timeout: str = "5"):
        cmd: list[str] = [
            "python",
            "vendors/sherlock/sherlock_project/sherlock.py",
            target,
            "--timeout",
            timeout,
        ]

        info(f"Lauching external Sherlock process for {target}...")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error("Sherlock process failed to execute.")
            return

        data = stdout.decode("utf-8")
        results = self._parse_output(data)

        if not results:
            error("No results found.")
            return

        info("Displaying results...")
        self.display_results(target, results)
        await self._save_results(target, results)

    def _parse_output(self, output: str) -> dict[str, str]:
        accounts = {}

        lines = output.splitlines()
        for line in lines:
            line = line.strip()
            if (
                line.startswith("[*]")
                or line.startswith("[+")
                or line == ""
                or line.endswith("\r")
            ):
                line = (
                    line.replace("[*]", "").replace("[+", "").replace("] ", "").strip()
                )

            if line.startswith("Search completed") or line.startswith("Checking "):
                continue

            try:
                account = line.split(":")[0].strip()
                url = ":".join(line.split(":")[1:]).strip()

                accounts[account] = url

            except Exception:
                continue

        return accounts

    def display_results(self, target: str, results: dict[str, str]) -> None:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich import box

        console = Console()

        table = Table(box=box.MINIMAL_DOUBLE_HEAD, expand=True)
        table.add_column("Platform", style="cyan bold", width=30)
        table.add_column("Profile URL", style="green underline")

        for platform, url in sorted(results.items()):
            table.add_row(platform, url)

        console.print(
            Panel(
                table,
                title=f"[bold green]Sherlock Profile Footprint: {target}[/bold green]",
                border_style="green",
                box=box.HEAVY,
            )
        )

    async def _save_results(self, target: str, results: dict[str, str]) -> None:
        import uuid
        from typing import Any

        # STIX 2.1 User-Account Namespace
        STIX_ACCOUNT_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa6")
        target_uuid = uuid.uuid5(STIX_ACCOUNT_NAMESPACE, target)

        stix2_target = {
            "type": "user-account",
            "id": f"user-account--{target_uuid}",
            "spec_version": "2.1",
            "user_id": target,
        }

        misp_target = {
            "type": "github-username",
            "value": target,
        }

        primary_node = {
            "type": "user-account",
            "value": target,
            "metadata": {
                "stix2": stix2_target,
                "misp": misp_target,
                "accounts_found_count": len(results),
            },
        }

        nodes: list[dict[str, Any]] = [primary_node]
        edges: list[dict[str, Any]] = []

        # Standard Namespaces
        STIX_IDENTITY_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa3")

        # Map each found profile
        for platform, profile_url in results.items():
            if not platform or not profile_url:
                continue

            platform_cleaned = platform.strip()
            profile_url_cleaned = profile_url.strip()

            # Create Platform Organization node
            org_uuid = uuid.uuid5(STIX_IDENTITY_NAMESPACE, platform_cleaned)
            stix2_org = {
                "type": "identity",
                "id": f"identity--{org_uuid}",
                "spec_version": "2.1",
                "name": platform_cleaned,
                "identity_class": "organization",
            }

            org_node = {
                "type": "organization",
                "value": platform_cleaned,
                "metadata": {
                    "stix2": stix2_org,
                    "misp": {"type": "text", "value": platform_cleaned},
                },
            }

            if org_node not in nodes:
                nodes.append(org_node)

            # Create specific social user-account node
            profile_id_str = f"{platform_cleaned}:{target}"
            profile_uuid = uuid.uuid5(STIX_ACCOUNT_NAMESPACE, profile_id_str)

            stix2_profile = {
                "type": "user-account",
                "id": f"user-account--{profile_uuid}",
                "spec_version": "2.1",
                "user_id": target,
                "display_name": f"{target} on {platform_cleaned}",
                "account_type": "social-media",
                "account_login": target,
                "x_profile_url": profile_url_cleaned,
            }

            misp_profile = {
                "type": "link",
                "value": profile_url_cleaned,
            }

            profile_node = {
                "type": "user-account",
                "value": profile_id_str,
                "metadata": {
                    "stix2": stix2_profile,
                    "misp": misp_profile,
                    "platform": platform_cleaned,
                    "profile_url": profile_url_cleaned,
                },
            }

            if profile_node not in nodes:
                nodes.append(profile_node)

            # Create relations:
            # Target owns the social profile
            edges.append(
                {
                    "source": target,
                    "target": profile_id_str,
                    "relationship": "owns-account",
                }
            )

            # Social profile is registered-on the platform organization
            edges.append(
                {
                    "source": profile_id_str,
                    "target": platform_cleaned,
                    "relationship": "registered-on",
                }
            )

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
