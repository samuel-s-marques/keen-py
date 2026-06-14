from src.utils.user_agents import UserAgents
import phonenumbers
from phonenumbers import geocoder, carrier, timezone
from rich.table import Table
from rich.console import Console

from src.utils.print_utils import error, success, warn
from src.core.base_module import BaseModule
from src.utils.validator import InputValidator


class PhoneVerificationModule(BaseModule):
    metadata = {
        "name": "Phone_Verification",
        "description": "Verifies phone number validity through local analysis and external APIs.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The phone number to verify.",
                "phone",
            ],
            "TIMEOUT": ["15", False, "Timeout for API requests in seconds.", ""],
            "APILAYER_PHONE_VER_APIKEY": [
                "",
                False,
                "Optional API Key for APILayer Phone Verification to get detailed results.",
                "",
            ],
        },
    }

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).strip()
        timeout: int = int(self.options.get("TIMEOUT", 15))

        await self.loading(
            f"Verifying phone number {target}...", self.execute, target, timeout
        )

    async def execute(self, phone: str, timeout: int) -> None:
        if not InputValidator.is_valid_phone_number(phone):
            error(f"Invalid phone number format: {phone}")
            return

        results = {
            "local": self.local_analysis(phone),
            "api": await self.api_verify(phone, timeout),
        }

        self.display_results(phone, results)
        await self._save_results(phone, results)

    def local_analysis(self, phone: str) -> dict:
        """Perform local analysis using the phonenumbers library."""
        try:
            # Add '+' if missing for better parsing of international numbers
            if not phone.startswith("+"):
                phone = "+" + phone

            parsed = phonenumbers.parse(phone, None)

            return {
                "valid": phonenumbers.is_valid_number(parsed),
                "possible": phonenumbers.is_possible_number(parsed),
                "international_format": phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
                ),
                "national_format": phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.NATIONAL
                ),
                "e164_format": phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                ),
                "country_code": parsed.country_code,
                "region": geocoder.description_for_number(parsed, "en"),
                "carrier": carrier.name_for_number(parsed, "en"),
                "timezones": list(timezone.time_zones_for_number(parsed)),
                "error": None,
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}

    async def api_verify(self, phone: str, timeout: int) -> dict | None:
        """Verify phone number via APILayer API."""
        api_key = self.options.get("APILAYER_PHONE_VER_APIKEY")
        if not api_key:
            return None

        try:
            async with self.get_http_client(timeout=timeout) as client:
                r = await client.get(
                    f"https://api.apilayer.com/number_verification/validate?number={phone}",
                    headers={"apikey": api_key, "User-Agent": UserAgents.get()},
                )

                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 401:
                    warn("APILayer API Key is invalid or expired.")
                else:
                    warn(f"APILayer API returned status code {r.status_code}")

        except Exception as e:
            warn(f"API verification failed: {e}")

        return None

    def display_results(self, phone: str, results: dict) -> None:
        local = results["local"]
        api = results["api"]

        table = Table(
            show_header=True,
            header_style="bold blue",
            title=f"Phone Verification: [bold white]{phone}[/bold white]",
            title_style="bold cyan",
            show_lines=True,
            expand=True,
        )

        table.add_column("Property", justify="left", style="cyan", no_wrap=True)
        table.add_column("Details", justify="left", style="white")

        # Local Analysis Section
        if not local.get("error"):
            status_color = "green" if local["valid"] else "red"
            table.add_row(
                "Validity (Local)",
                f"[{status_color}]{'Valid' if local['valid'] else 'Invalid'}[/{status_color}]",
            )
            table.add_row("Format (Intl)", local.get("international_format", "N/A"))
            table.add_row("Format (National)", local.get("national_format", "N/A"))
            table.add_row("E.164 Format", local.get("e164_format", "N/A"))
            table.add_row("Country Code", str(local.get("country_code", "N/A")))
            table.add_row("Region/Location", local.get("region") or "Unknown")
            table.add_row("Carrier", local.get("carrier") or "Unknown")
            table.add_row(
                "Timezones", ", ".join(local.get("timezones", [])) or "Unknown"
            )
        else:
            table.add_row("Local Analysis Error", f"[red]{local['error']}[/red]")

        # API Section
        if api:
            table.add_row("[bold]API Data (APILayer)[/bold]", "")
            table.add_row("Carrier (API)", api.get("carrier") or "N/A")
            table.add_row("Line Type", api.get("line_type") or "N/A")
            table.add_row("Location (API)", api.get("location") or "N/A")
            table.add_row(
                "Valid (API)",
                "[green]Yes[/green]" if api.get("valid") else "[red]No[/red]",
            )

        console = Console()
        if not getattr(self, "is_web_context", False):
            console.print(table)

        if local.get("valid"):
            success(f"Phone number {phone} appears to be valid.")
        else:
            error(f"Phone number {phone} is invalid or could not be verified.")

    async def _save_results(self, phone: str, results: dict) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory

        local = results.get("local", {})
        api = results.get("api") or {}

        carrier_name = local.get("carrier") or api.get("carrier")
        region = local.get("region") or api.get("location")
        line_type = api.get("line_type")

        builder = ResultBuilder()

        phone_node = NodeFactory.phone(
            phone,
            country_code=local.get("country_code"),
            carrier=carrier_name,
            region=region,
            line_type=line_type,
            valid=local.get("valid"),
        )
        # Override stix2 with extra fields
        phone_node["metadata"]["stix2"]["country_code"] = (
            str(local.get("country_code")) if local.get("country_code") else None
        )
        phone_node["metadata"]["stix2"]["region"] = region
        phone_node["metadata"]["stix2"]["carrier"] = carrier_name
        phone_node["metadata"]["stix2"]["line_type"] = line_type
        phone_node["metadata"]["stix2"]["valid"] = bool(local.get("valid", False))

        # Build detailed MISP object
        misp_attributes = [
            {"type": "phone-number", "value": phone, "object_relation": "phone-number"}
        ]
        if local.get("country_code"):
            misp_attributes.append(
                {
                    "type": "text",
                    "value": str(local["country_code"]),
                    "object_relation": "country-code",
                }
            )
        if region:
            misp_attributes.append(
                {"type": "text", "value": region, "object_relation": "location"}
            )
        if carrier_name:
            misp_attributes.append(
                {"type": "text", "value": carrier_name, "object_relation": "carrier"}
            )
        if line_type:
            misp_attributes.append(
                {"type": "text", "value": line_type, "object_relation": "line-type"}
            )
        misp_attributes.append(
            {
                "type": "boolean",
                "value": "true" if local.get("valid") else "false",
                "object_relation": "valid",
            }
        )

        phone_node["metadata"]["misp"] = {
            "name": "phone-number",
            "meta-category": "misc",
            "description": "Phone number object describing a phone number and its metadata.",
            "attributes": misp_attributes,
        }

        builder.add_node(phone_node)

        # Carrier node
        if carrier_name:
            builder.add_node(NodeFactory.organization(carrier_name, type="carrier"))
            builder.add_edge(phone, carrier_name, "allocated-to")

        # Location node
        if region:
            builder.add_node(NodeFactory.location(region, type="region"))
            builder.add_edge(phone, region, "located-in")

        await self.post_run(builder.build())
