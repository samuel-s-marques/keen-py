from src.utils.print_utils import info, error
from ddgs import DDGS
import re

from src.core.base_module import BaseModule


class OrganizationToDomain(BaseModule):
    metadata = {
        "name": "Organization_To_Domain",
        "description": "Converts an organization name to a domain name.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "NAME": [
                "",
                True,
                "The name of the organization to convert.",
                "name",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        pass

    async def execute(self, name: str) -> str | None:
        # Strip common legal suffixes to clean up the search query
        clean_name = re.sub(
            r"\b(llc|inc|corp|corporation|ltd|gmbh|sa)\b",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()

        domains: set[str] = set()
        best_domain: str | None = None
        best_score: int = 0

        domains.update(await self._query_ddgs(clean_name))

        domains_list = list(domains)
        best_domain = domains_list[0]
        return best_domain

    async def _query_ddgs(self, name: str) -> set[str]:
        # Exclude massive aggregators from the search results to find the actual homepage
        query = f'"{name}" -site:linkedin.com -site:wikipedia.org -site:crunchbase.com'
        info(f"Search Query: {query}")

        domains: set[str] = set()

        try:
            with DDGS() as ddg:
                # Grab the top 5 search results for a broader pool
                results = ddg.text(query, max_results=5)
                if results:
                    for result in results:
                        url = result.get("href")
                        if url:
                            domain_match = re.search(r"https?://(?:www\.)?([^/]+)", url)
                            if domain_match:
                                domains.add(domain_match.group(1))
        except Exception as e:
            error(f"Failed to query DDGS: {e}")
            return domains

        return domains
