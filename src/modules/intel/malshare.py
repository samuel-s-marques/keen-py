"""Malshare hash/IOC lookup.

Chains directly off ``helpers/hash_lookup.py``'s ``x-hash`` output (same
target type, same validator) rather than introducing a new hash format --
that module already gave ``magic.py``'s ``x-hash`` detection its first
consumer; this is a second one, doing actual threat-intel enrichment
instead of just identifying the hash algorithm.
"""

import json

from src.core.base_module import BaseModule
from src.core.result_builder import NodeFactory, ResultBuilder, STIXNamespaces
from src.utils.print_utils import error, success


class Malshare(BaseModule):
    metadata = {
        "name": "Malshare",
        "description": (
            "Looks up a file hash in Malshare's malware-sample corpus, "
            "producing a malware-sample node on a hit."
        ),
        "author": "Samuel Marques",
        "version": "1.0.0",
        "category": "intel",
        "magic_consumes": ["x-hash"],
        # Passive: a lookup against a third-party malware-sample database,
        # never touching anything the hash itself might reference.
        "execution_safety": "passive",
        "options": {
            "TARGET": ["", True, "The hash to look up (MD5/SHA-1/SHA-256).", "hash"],
            "MALSHARE_APIKEY": ["", True, "API key for Malshare.", ""],
        },
    }

    lower_target: bool = False

    def loading_message(self, target: str) -> str:
        return f"Looking up {target} on Malshare..."

    async def execute(self, target: str) -> None:
        api_key = self.options.get("MALSHARE_APIKEY")
        if not api_key:
            error(
                "MALSHARE_APIKEY is required. Set it via 'set MALSHARE_APIKEY <key>'."
            )
            return

        sample = await self._fetch_sample(target, api_key)
        if sample is None:
            error(f"Could not query Malshare for {target}.")
            return
        if not sample:
            success(f"No Malshare sample found for {target}.")
            return

        success(f"Malshare has a sample matching {target}.")
        self.display_results(target, sample)
        await self._save_results(target, sample)

    async def _fetch_sample(self, target: str, api_key: str) -> dict | None:
        cache_key = f"malshare:{target}"
        cached = self.cache_get(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                pass

        sample = await self._query_malshare(target, api_key)
        if sample is None:
            return None

        self.cache_set(cache_key, json.dumps(sample), ttl=3600)
        return sample

    async def _query_malshare(self, target: str, api_key: str) -> dict | None:
        await self.rate_limit("malshare")
        try:
            async with self.get_http_client() as client:
                response = await self.request(
                    client,
                    "GET",
                    "https://malshare.com/api.php",
                    params={"api_key": api_key, "action": "details", "hash": target},
                )
        except Exception as e:
            self.logger.error(f"Malshare request failed for {target}: {e}")
            return None

        if response is None or response.status_code != 200:
            return None

        try:
            data = response.json()
        except Exception:
            return None

        # A miss comes back as an error payload rather than a 404 -- treat it
        # as "no sample found", not a request failure.
        if not data or "ERROR" in data:
            return {}
        return data

    def display_results(self, target: str, sample: dict) -> None:
        table = self.kv_table(title=f"Malshare: {target}")
        table.add_row("File Type", sample.get("F_TYPE", "") or "")
        table.add_row("SSDEEP", sample.get("SSDEEP", "") or "")
        table.add_row("Sources", ", ".join(sample.get("SOURCES", []) or []))
        self.render(table)

    async def _save_results(self, target: str, sample: dict) -> None:
        builder = ResultBuilder()

        # Same shape hash_lookup.py produces, so a standalone Malshare run
        # (not chained off hash_lookup) still leaves a proper x-hash node.
        builder.add_node(
            NodeFactory.custom(
                stix_type="x-hash",
                value=target,
                node_type="x-hash",
                misp_type="text",
            )
        )

        sample_val = f"malshare:{target}"
        builder.add_node(
            NodeFactory.custom(
                "x-malware-sample",
                sample_val,
                namespace=STIXNamespaces.URL,
                stix2_extra={
                    "file_type": sample.get("F_TYPE"),
                    "ssdeep": sample.get("SSDEEP"),
                    "sources": sample.get("SOURCES", []),
                },
                misp_type="malware-sample",
                misp_value=target,
                file_type=sample.get("F_TYPE"),
            )
        )
        builder.add_edge(target, sample_val, "matches")

        await self.post_run(builder.build())
