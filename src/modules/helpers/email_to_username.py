from src.core.base_module import BaseModule


class EmailToUsername(BaseModule):
    metadata = {
        "name": "Email_To_Username",
        "description": "Extracts the username from an email address.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The email address to extract the username from.",
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

        email: str = str(self.options.get("TARGET")).lower()
        username: str = await self.execute(email)

        await self._save_results(email, username)

    async def execute(self, email: str) -> str:
        if "@" in email:
            return email.split("@")[0]
        return email

    async def _save_results(self, email: str, username: str) -> None:
        import uuid
        from typing import Any

        if not email or not username:
            return

        # STIX 2.1 Standard Email-Address Object
        STIX_EMAIL_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa2")
        email_uuid = uuid.uuid5(STIX_EMAIL_NAMESPACE, email)

        stix2_email = {
            "type": "email-addr",
            "id": f"email-addr--{email_uuid}",
            "spec_version": "2.1",
            "value": email,
        }

        misp_email = {
            "type": "email-dst",
            "value": email,
        }

        email_node = {
            "type": "email-addr",
            "value": email,
            "metadata": {
                "stix2": stix2_email,
                "misp": misp_email,
            },
        }

        # STIX 2.1 Standard User-Account Object
        STIX_ACCOUNT_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa6")
        user_uuid = uuid.uuid5(STIX_ACCOUNT_NAMESPACE, username)

        stix2_user = {
            "type": "user-account",
            "id": f"user-account--{user_uuid}",
            "spec_version": "2.1",
            "user_id": username,
        }

        misp_user = {
            "type": "text",
            "value": username,
        }

        user_node = {
            "type": "user-account",
            "value": username,
            "metadata": {
                "stix2": stix2_user,
                "misp": misp_user,
            },
        }

        nodes: list[dict[str, Any]] = [email_node, user_node]
        edges: list[dict[str, Any]] = [
            {
                "source": email,
                "target": username,
                "relationship": "has-username",
            }
        ]

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
