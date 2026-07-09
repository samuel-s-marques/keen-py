import os
import sys

from src.core.base_module import BaseModule
from src.utils.print_utils import error, info

# Repo root (…/keen-py), four levels up from this file, used to locate the
# vendored Sherlock submodule regardless of the process working directory.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SHERLOCK_SCRIPT = os.path.join(
    _REPO_ROOT, "vendors", "sherlock", "sherlock_project", "sherlock.py"
)


class SherlockModule(BaseModule):
    metadata = {
        "name": "Sherlock",
        "description": "Searches for a username on the internet, using the Sherlock tool.",
        "author": "Samuel Marques",
        "version": "1.1.0",
        "magic_consumes": ["user-account"],
        "options": {
            "TARGET": [
                "",
                True,
                "The username to lookup.",
                "username",
            ]
        },
    }

    lower_target = False

    def loading_message(self, target: str) -> str:
        return f"Executing Sherlock scan on {target}..."

    async def execute(self, target: str, timeout: str = "5") -> None:
        if not os.path.isfile(_SHERLOCK_SCRIPT):
            error(
                "Sherlock is not available: the vendored submodule is missing. "
                "Fetch it with:\n"
                "    git submodule update --init --recursive"
            )
            return

        cmd: list[str] = [
            sys.executable or "python",
            _SHERLOCK_SCRIPT,
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
        table = self.results_table(
            columns=["Platform", ("Profile URL", "green underline")],
        )

        for platform, url in sorted(results.items()):
            table.add_row(platform, url)

        self.render(
            self.result_panel(
                table,
                title=f"[bold green]Sherlock Profile Footprint: {target}[/bold green]",
                kind="success",
            )
        )

    async def _save_results(self, target: str, results: dict[str, str]) -> None:
        from src.core.result_builder import NodeFactory, ResultBuilder

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
            profile_node = builder.add_node(
                NodeFactory.user_account(
                    profile_id_str,
                    platform=platform_cleaned,
                    profile_url=profile_url_cleaned,
                )
            )
            # Override the stix2 fields for social-media specifics
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
