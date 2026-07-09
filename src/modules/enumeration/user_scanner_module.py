from user_scanner.core import engine as us_engine
from user_scanner.core.result import Result

from src.core.base_module import BaseModule
from src.core.pattern_extractor import PatternExtractor
from src.utils.print_utils import error, success
from src.utils.validator import InputValidator


class UserScannerModule(BaseModule):
    metadata = {
        "name": "User_Scanner",
        "description": "Checks for usernames and emails on various platforms.",
        "author": "Samuel Marques",
        "version": "1.1.0",
        "magic_consumes": ["email-addr", "user-account"],
        "options": {
            "TARGET": [
                "",
                True,
                "The target to lookup.",
                "email,username",
            ],
        },
    }

    lower_target = False

    def loading_message(self, target: str) -> str:
        return f"Executing user_scanner scan on {target}..."

    async def execute(self, target: str) -> None:
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
            res_dict = res.as_dict()
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
        table = self.results_table(
            title=f"User Scanner Results: [bold cyan]{target}[/bold cyan]",
            columns=[
                "Site Name",
                "Category",
                ("URL", "green underline"),
                "Details",
            ],
        )

        for item in results:
            site_name = item.get("site_name", "Unknown")
            category = item.get("category", "Unknown")
            url = item.get("url", "N/A")
            extra = item.get("extra", "").strip()

            table.add_row(site_name, category, url, extra)

        self.render(table)

    async def _save_results(self, target: str, results: list) -> None:
        from src.core.result_builder import NodeFactory, ResultBuilder
        from src.utils.validator import InputValidator

        is_email = InputValidator.is_valid_email(target)

        builder = ResultBuilder()

        if is_email:
            builder.add_node(NodeFactory.email(target))
        else:
            builder.add_node(NodeFactory.user_account(target))

        for item in results:
            site_name = item.get("site_name", "Unknown")
            url = item.get("url", "")
            category = item.get("category", "")
            extra = item.get("extra", "")

            # Organization node for the site
            builder.add_node(NodeFactory.organization(site_name, category=category))

            # User account node on that site
            account_id_str = f"{site_name}:{target}"
            account_node = builder.add_node(
                NodeFactory.user_account(
                    account_id_str,
                    site=site_name,
                    profile_url=url,
                    details=extra,
                )
            )
            # Override stix2 specifics
            account_node["metadata"]["stix2"]["display_name"] = (
                f"{target} on {site_name}"
            )
            account_node["metadata"]["stix2"]["account_type"] = "social-media"
            account_node["metadata"]["stix2"]["x_profile_url"] = url
            account_node["metadata"]["stix2"]["description"] = extra
            account_node["metadata"]["misp"] = {"type": "link", "value": url}

            # Edges
            builder.add_edge(target, account_id_str, "owns-account")
            builder.add_edge(account_id_str, site_name, "registered-on")

            # Extract patterns from the structured result dict. (Passing the
            # free-text `extra` string here was a no-op: extract_and_link only
            # operates on a dict of fields.)
            PatternExtractor.extract_and_link(builder, account_id_str, item)

        await self.post_run(builder.build())
