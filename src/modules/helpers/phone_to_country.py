import phonenumbers
from phonenumbers import geocoder

from src.core.base_module import BaseModule
from src.utils.print_utils import error, success


class PhoneToCountry(BaseModule):
    metadata = {
        "name": "Phone_To_Country",
        "description": "Resolves a phone number to its ISO country code, country name, and region via libphonenumber.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "magic_consumes": ["x-phone-number"],
        "options": {
            "TARGET": [
                "",
                True,
                "The phone number to resolve (e.g. +14157120049).",
                "phone",
            ],
        },
    }

    lower_target: bool = False

    def loading_message(self, target: str) -> str:
        return f"Resolving country for {target}..."

    async def execute(self, target: str) -> None:
        phone = target if target.startswith("+") else f"+{target}"

        try:
            parsed = phonenumbers.parse(phone, None)
        except Exception as e:
            error(f"Could not parse phone number {target}: {e}")
            return

        country_code = phonenumbers.region_code_for_number(parsed)
        region = geocoder.description_for_number(parsed, "en")
        calling_code = parsed.country_code

        if not country_code or calling_code is None:
            error(f"Could not resolve a country for {target}.")
            return

        success(f"{target} resolves to {country_code} ({region or 'Unknown region'}).")
        self.display_results(target, country_code, region, calling_code)
        await self._save_results(target, country_code, region)

    def display_results(
        self, phone: str, country_code: str, region: str | None, calling_code: int
    ) -> None:
        table = self.kv_table(title=f"Country Lookup: {phone}")
        table.add_row("ISO Country Code", country_code)
        table.add_row("Region", region or "Unknown")
        table.add_row("Calling Code", f"+{calling_code}")
        self.render(table)

    async def _save_results(
        self, phone: str, country_code: str, region: str | None
    ) -> None:
        from src.core.result_builder import NodeFactory, ResultBuilder

        location_name = region or country_code

        builder = ResultBuilder()
        builder.add_node(NodeFactory.phone(phone))
        builder.add_node(NodeFactory.location(location_name, country_code=country_code))
        builder.add_edge(phone, location_name, "located-in")

        await self.post_run(builder.build())
