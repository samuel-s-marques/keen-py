from src.utils.print_utils import success
from urllib.parse import urlparse

from src.core.base_module import BaseModule


class UrlToDomain(BaseModule):
    metadata = {
        "name": "Url_To_Domain",
        "description": "Extracts the domain name from a URL.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": ["", True, "The URL to convert.", "url"],
        },
    }

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()
        domain: str = await self.execute(target)

        success(f"Extracted domain: {domain}")

        await self._save_results(domain)

    async def execute(self, target: str) -> str:
        parsed = urlparse(target)
        domain = parsed.netloc
        return domain

    async def _save_results(self, domain: str) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory

        url: str = str(self.options.get("TARGET")).lower()
        if not url:
            return

        builder = ResultBuilder()
        builder.add_node(NodeFactory.url(url))

        if domain:
            domain_cleaned = domain.strip().lower()
            if domain_cleaned:
                builder.add_node(NodeFactory.domain(domain_cleaned))
                builder.add_edge(url, domain_cleaned, "hosted-on")

        await self.post_run(builder.build())
