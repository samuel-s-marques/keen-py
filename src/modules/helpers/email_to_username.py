from src.core.base_module import BaseModule
from src.utils.print_utils import success


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

    async def run(self) -> None:
        if not self.pre_run():
            return

        email: str = str(self.options.get("TARGET")).lower()
        username: str = await self.execute(email)

        success(f"Extracted username: {username}")

        await self._save_results(email, username)

    async def execute(self, email: str) -> str:
        if "@" in email:
            return email.split("@")[0]
        return email

    async def _save_results(self, email: str, username: str) -> None:
        if not email or not username:
            return

        from src.core.result_builder import NodeFactory, ResultBuilder

        builder = ResultBuilder()
        builder.add_node(NodeFactory.email(email))
        builder.add_node(NodeFactory.user_account(username))
        builder.add_edge(email, username, "has-username")

        await self.post_run(builder.build())
