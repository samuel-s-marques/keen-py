"""IP geolocation via ipapi.co.

Produces a `location` node carrying real latitude/longitude -- unlike
`helpers/ip_to_asn.py`'s existing `location` node, which is a country-name
string with no coordinates. This is the first module to feed real
coordinate data into the World View map for anything other than an
EXIF-tagged photo. Also produces an `organization` node for the owning
ISP/network when the API reports one, cross-referencing `ip_to_asn.py`'s
independently-sourced ASN/provider data on the same IP.
"""

import ipaddress

from src.core.base_module import BaseModule
from src.core.result_builder import NodeFactory, ResultBuilder
from src.utils.print_utils import error, success


class IpGeolocation(BaseModule):
    metadata = {
        "name": "Ip_Geolocation",
        "description": (
            "Resolves an IP address to an approximate geographic location "
            "(city/region/country + coordinates) via ipapi.co."
        ),
        "author": "Samuel Marques",
        "version": "1.0.0",
        "magic_consumes": ["ipv4-addr", "ipv6-addr"],
        # Passive: a public geolocation lookup about the IP, never touching
        # the target's own infrastructure.
        "execution_safety": "passive",
        "options": {
            "TARGET": ["", True, "The IP address to geolocate.", "ip"],
        },
    }

    def loading_message(self, target: str) -> str:
        return f"Geolocating {target}..."

    async def execute(self, target: str) -> None:
        await self.rate_limit("ipapi_co")

        result = await self._lookup(target)
        if result is None:
            error(f"Could not geolocate {target}.")
            return

        location_label = (
            ", ".join(
                p for p in (result["city"], result["region"], result["country"]) if p
            )
            or f"{result['latitude']}, {result['longitude']}"
        )
        success(f"{target} geolocates to {location_label}.")
        self.display_results(target, result)
        await self._save_results(target, result)

    async def _lookup(self, ip: str) -> dict | None:
        cache_key = f"ipapi_co:{ip}"
        cached = self.cache_get(cache_key)
        if cached is not None:
            import json

            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                pass

        try:
            async with self.get_http_client() as client:
                response = await self.request(
                    client, "GET", f"https://ipapi.co/{ip}/json/", timeout=15
                )
        except Exception as e:
            self.logger.error(f"ipapi.co request failed for {ip}: {e}")
            return None

        if response is None or response.status_code != 200:
            return None

        try:
            data = response.json()
        except Exception:
            return None

        # ipapi.co returns HTTP 200 with {"error": true, "reason": "..."} for
        # invalid/rate-limited/reserved-range lookups rather than a 4xx.
        if data.get("error") or data.get("latitude") is None:
            return None

        parsed = self._parse(data)

        import json

        self.cache_set(cache_key, json.dumps(parsed), ttl=86400)
        return parsed

    @staticmethod
    def _parse(data: dict) -> dict:
        return {
            "city": data.get("city") or "",
            "region": data.get("region") or "",
            "country": data.get("country_name") or "",
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "org": data.get("org") or "",
            "asn": data.get("asn") or "",
        }

    def display_results(self, target: str, result: dict) -> None:
        table = self.kv_table(title=f"Geolocation: {target}")
        table.add_row(
            "Location",
            ", ".join(
                p for p in (result["city"], result["region"], result["country"]) if p
            )
            or "-",
        )
        table.add_row("Coordinates", f"{result['latitude']}, {result['longitude']}")
        table.add_row("Org/ISP", result.get("org") or "-")
        self.render(table)

    async def _save_results(self, target: str, result: dict) -> None:
        try:
            version = ipaddress.ip_address(target).version
        except ValueError:
            version = 4

        builder = ResultBuilder()
        builder.add_node(NodeFactory.ip(target, version=version))

        location_name = (
            ", ".join(
                p for p in (result["city"], result["region"], result["country"]) if p
            )
            or f"{result['latitude']}, {result['longitude']}"
        )

        builder.add_node(
            NodeFactory.location(
                location_name,
                latitude=result["latitude"],
                longitude=result["longitude"],
                city=result["city"],
                region=result["region"],
                country=result["country"],
            )
        )
        builder.add_edge(target, location_name, "geolocated-to")

        if result.get("org"):
            builder.add_node(NodeFactory.organization(result["org"]))
            builder.add_edge(target, result["org"], "hosted-by")

        await self.post_run(builder.build())
