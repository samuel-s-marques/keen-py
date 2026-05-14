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

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

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
        import uuid
        from typing import Any

        url: str = str(self.options.get("TARGET")).lower()
        if not url:
            return

        # STIX 2.1 Standard URL Object
        STIX_URL_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa5")
        url_uuid = uuid.uuid5(STIX_URL_NAMESPACE, url)

        stix2_url = {
            "type": "url",
            "id": f"url--{url_uuid}",
            "spec_version": "2.1",
            "value": url,
        }

        misp_url = {
            "type": "link",
            "value": url,
        }

        url_node = {
            "type": "url",
            "value": url,
            "metadata": {
                "stix2": stix2_url,
                "misp": misp_url,
            },
        }

        nodes: list[dict[str, Any]] = [url_node]
        edges: list[dict[str, Any]] = []

        if domain:
            domain_cleaned = domain.strip().lower()
            if domain_cleaned:
                # STIX 2.1 Standard Domain-Name Object
                STIX_DOMAIN_NAMESPACE = uuid.UUID(
                    "f070f381-8b38-5fdf-9730-802526e84fa7"
                )
                domain_uuid = uuid.uuid5(STIX_DOMAIN_NAMESPACE, domain_cleaned)

                stix2_domain = {
                    "type": "domain-name",
                    "id": f"domain-name--{domain_uuid}",
                    "spec_version": "2.1",
                    "value": domain_cleaned,
                }

                misp_domain = {
                    "type": "domain",
                    "value": domain_cleaned,
                }

                domain_node = {
                    "type": "domain-name",
                    "value": domain_cleaned,
                    "metadata": {
                        "stix2": stix2_domain,
                        "misp": misp_domain,
                    },
                }

                nodes.append(domain_node)

                edges.append(
                    {
                        "source": url,
                        "target": domain_cleaned,
                        "relationship": "hosted-on",
                    }
                )

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
