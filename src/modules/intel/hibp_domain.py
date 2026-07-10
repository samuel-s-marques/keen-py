"""HIBP domain-breach lookup.

``analysis/leak_module.py`` already checks HIBP's ``breachedAccount``
endpoint for a single email (needs an API key). This is the missing
*domain*-level view: HIBP's public ``breaches?domain=`` endpoint needs no
key at all and answers "which breaches is this domain's own service
associated with" -- exposure metadata only (name/date/data-classes), never
raw credentials, per BEYOND_MALTEGO §5.1's own framing.

Breach nodes intentionally reuse the exact node shape (``x-data-breach``,
``STIXNamespaces.BREACH``, ``f"HIBP:{name}"`` value) that
``leak_module.py``'s HIBP check already produces, so the same breach found
via either module dedups onto one graph node instead of two.
"""

import json

from src.core.base_module import BaseModule
from src.core.result_builder import NodeFactory, ResultBuilder, STIXNamespaces
from src.utils.print_utils import error, success


class HibpDomain(BaseModule):
    metadata = {
        "name": "Hibp_Domain",
        "description": (
            "Looks up which breaches HIBP's public catalog associates with a "
            "domain (exposure metadata only, no API key required)."
        ),
        "author": "Samuel Marques",
        "version": "1.0.0",
        "category": "intel",
        "magic_consumes": ["domain-name"],
        # Passive: a public breach-catalog lookup about the target domain,
        # never touching its infrastructure.
        "execution_safety": "passive",
        "options": {
            "TARGET": ["", True, "The domain to check.", "domain"],
        },
    }

    def loading_message(self, target: str) -> str:
        return f"Checking HIBP's breach catalog for {target}..."

    async def execute(self, target: str) -> None:
        breaches = await self._fetch_breaches(target)
        if breaches is None:
            error(f"Could not query HIBP for {target}.")
            return
        if not breaches:
            success(f"No breaches found in HIBP's catalog for {target}.")
            return

        success(f"Found {len(breaches)} breach(es) in HIBP's catalog for {target}.")
        self.display_results(target, breaches)
        await self._save_results(target, breaches)

    async def _fetch_breaches(self, target: str) -> list[dict] | None:
        cache_key = f"hibp_domain:{target}"
        cached = self.cache_get(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                pass

        breaches = await self._query_hibp(target)
        if breaches is None:
            return None

        self.cache_set(cache_key, json.dumps(breaches), ttl=3600)
        return breaches

    async def _query_hibp(self, target: str) -> list[dict] | None:
        await self.rate_limit("hibp")
        try:
            async with self.get_http_client() as client:
                response = await self.request(
                    client,
                    "GET",
                    "https://haveibeenpwned.com/api/v3/breaches",
                    params={"domain": target},
                    headers={"User-Agent": "keen-py/1.0.0"},
                )
        except Exception as e:
            self.logger.error(f"HIBP request failed for {target}: {e}")
            return None

        if response is None:
            return None
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            return None

        try:
            return response.json() or []
        except Exception:
            return None

    def display_results(self, target: str, breaches: list[dict]) -> None:
        table = self.results_table(
            title=f"HIBP Breach Catalog: {target}",
            columns=["Breach", "Date", "Pwned Accounts", "Data Classes"],
        )
        for breach in breaches:
            classes = ", ".join(breach.get("DataClasses", []))
            table.add_row(
                breach.get("Name", "Unknown"),
                breach.get("BreachDate", ""),
                str(breach.get("PwnCount", "")),
                classes,
            )
        self.render(table)

    async def _save_results(self, target: str, breaches: list[dict]) -> None:
        builder = ResultBuilder()
        builder.add_node(NodeFactory.domain(target))

        for breach in breaches:
            name = breach.get("Name", "Unknown")
            breach_val = f"HIBP:{name}"

            builder.add_node(
                NodeFactory.custom(
                    "x-data-breach",
                    breach_val,
                    namespace=STIXNamespaces.BREACH,
                    stix2_extra={
                        "name": name,
                        "description": breach.get("Description", ""),
                        "source": "HIBP",
                        "breach_date": breach.get("BreachDate"),
                        "categories": breach.get("DataClasses", []),
                        "pwn_count": breach.get("PwnCount"),
                    },
                    misp_type="leak-source",
                    misp_value=f"HIBP ({name})",
                    breach_date=breach.get("BreachDate"),
                )
            )
            builder.add_edge(
                target,
                breach_val,
                "compromised-in",
                metadata={"categories": breach.get("DataClasses", [])},
            )

        await self.post_run(builder.build())
