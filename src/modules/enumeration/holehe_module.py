import httpx
import asyncio
from typing import Any
from holehe import core as holehe_core

from src.utils.print_utils import error, success
from src.core.base_module import BaseModule


class HoleheModule(BaseModule):
    metadata = {
        "name": "Holehe",
        "description": "Checks for email accounts on various platforms.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The target email to lookup.",
                "email",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET"))
        await self.loading(f"Executing holehe scan on {target}...", self.holehe, target)

    async def holehe(self, target: str) -> None:
        output = []

        # pyrefly: ignore [missing-attribute]
        modules = holehe_core.import_submodules("holehe.modules")
        websites = holehe_core.get_functions(modules)

        client = httpx.AsyncClient(timeout=10)
        tasks = [website(target, client, output) for website in websites]

        # Run all module checks concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
        await client.aclose()

        # Holehe results (for parsing later) TODO: Parse results
        """
        {
            "name": "example",
            "rateLimit": false,
            "exists": true,
            "emailrecovery": "ex****e@gmail.com",
            "phoneNumber": "0*******78",
            "others": null
        }
        """

        # Display results (only registered ones)
        registered = [item["name"] for item in output if item.get("exists")]
        if registered:
            success(f"Email registered on: {', '.join(registered)}")
        else:
            error(f"No registrations found or target '{target}' is invalid.")

        await self._save_results(target, output)

    async def _save_results(self, email: str, results: list) -> None:
        import uuid

        # STIX 2.1 Standard Email-Address Object
        STIX_EMAIL_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa2")
        email_uuid = uuid.uuid5(STIX_EMAIL_NAMESPACE, email)

        stix2_email = {
            "type": "email-addr",
            "id": f"email-addr--{email_uuid}",
            "spec_version": "2.1",
            "value": email,
        }

        # MISP representation
        misp_email = {
            "type": "email-dst",
            "value": email,
        }

        primary_node = {
            "type": "email-addr",
            "value": email,
            "metadata": {
                "stix2": stix2_email,
                "misp": misp_email,
            }
        }

        nodes: list[dict[str, Any]] = [primary_node]
        edges: list[dict[str, Any]] = []

        # Process registered services
        for item in results:
            if not item.get("exists"):
                continue

            service = item["name"]
            service_name = service.capitalize()

            # Create an organization node for the registered service
            service_node = {
                "type": "organization",
                "value": service_name,
                "metadata": {"type": "service"}
            }
            if service_node not in nodes:
                nodes.append(service_node)

            edges.append({
                "source": email,
                "target": service_name,
                "relationship": "registered-on"
            })

            # Process recovery email if exists
            recovery_email = item.get("emailrecovery")
            if recovery_email and recovery_email.strip() and not recovery_email.startswith("null"):
                rec_email_uuid = uuid.uuid5(STIX_EMAIL_NAMESPACE, recovery_email)
                rec_stix = {
                    "type": "email-addr",
                    "id": f"email-addr--{rec_email_uuid}",
                    "spec_version": "2.1",
                    "value": recovery_email,
                    "comment": "Masked recovery email found via Holehe"
                }
                rec_node = {
                    "type": "email-addr",
                    "value": recovery_email,
                    "metadata": {
                        "stix2": rec_stix,
                        "misp": {"type": "email-dst", "value": recovery_email},
                        "masked": True
                    }
                }
                if rec_node not in nodes:
                    nodes.append(rec_node)

                edges.append({
                    "source": email,
                    "target": recovery_email,
                    "relationship": "recovery-email"
                })

            # Process recovery phone if exists
            recovery_phone = item.get("phoneNumber")
            if recovery_phone and recovery_phone.strip() and not recovery_phone.startswith("null"):
                STIX_PHONE_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa1")
                phone_uuid = uuid.uuid5(STIX_PHONE_NAMESPACE, recovery_phone)
                phone_stix = {
                    "type": "x-phone-number",
                    "id": f"x-phone-number--{phone_uuid}",
                    "spec_version": "2.1",
                    "value": recovery_phone,
                    "comment": "Masked recovery phone found via Holehe"
                }
                phone_node = {
                    "type": "x-phone-number",
                    "value": recovery_phone,
                    "metadata": {
                        "stix2": phone_stix,
                        "misp": {"type": "phone-number", "value": recovery_phone},
                        "masked": True
                    }
                }
                if phone_node not in nodes:
                    nodes.append(phone_node)

                edges.append({
                    "source": email,
                    "target": recovery_phone,
                    "relationship": "recovery-phone"
                })

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
