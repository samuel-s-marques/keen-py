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
                "The username to lookup.",
                "username",
            ]
        },
    }

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
        returncode, stdout, stderr = await self.run_subprocess(cmd)

        if returncode != 0:
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

        if not getattr(self, "is_web_context", False):
            console.print(
                Panel(
                    table,
                    title=f"[bold green]Sherlock Profile Footprint: {target}[/bold green]",
                    border_style="green",
                    box=box.HEAVY,
                )
            )

    async def _save_results(self, target: str, results: dict[str, str]) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory

        builder = ResultBuilder()
        builder.add_node(
            NodeFactory.user_account(target, accounts_found_count=len(results))
        )

        for platform, profile_url in results.items():
            if not platform or not profile_url:
                continue

            platform_cleaned = platform.strip()
            profile_url_cleaned = profile_url.strip()

            # Organization node for the platform
            builder.add_node(NodeFactory.organization(platform_cleaned))

            # Social profile account node
            profile_id_str = f"{platform_cleaned}:{target}"
            builder.add_node(
                NodeFactory.user_account(
                    profile_id_str,
                    platform=platform_cleaned,
                    profile_url=profile_url_cleaned,
                )
            )
            # Override the stix2 fields for social-media specifics
            profile_node = builder._nodes[-1]
            profile_node["metadata"]["stix2"]["display_name"] = (
                f"{target} on {platform_cleaned}"
            )
            profile_node["metadata"]["stix2"]["account_type"] = "social-media"
            profile_node["metadata"]["stix2"]["account_login"] = target
            profile_node["metadata"]["stix2"]["x_profile_url"] = profile_url_cleaned
            profile_node["metadata"]["misp"] = {
                "type": "link",
                "value": profile_url_cleaned,
            }

            # Edges
            builder.add_edge(target, profile_id_str, "owns-account")
            builder.add_edge(profile_id_str, platform_cleaned, "registered-on")

        await self.post_run(builder.build())
