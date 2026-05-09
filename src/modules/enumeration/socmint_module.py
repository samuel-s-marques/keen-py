from src.utils.print_utils import error
from src.utils.validator import InputValidator
from src.core.base_module import BaseModule
from src.modules.enumeration.sherlock_module import SherlockModule
from src.modules.enumeration.holehe_module import HoleheModule


class SOCMINTModule(BaseModule):
    metadata = {
        "name": "SOCMINT_Enum",
        "description": "Performs SOCMINT (Social Media Intelligence) on a target.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The target to lookup (username, name, domain, etc).",
                "",
            ],
            "TYPE": [
                "auto",
                False,
                "The type of the target (username, name, domain, auto).",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target_type: str = str(self.options.get("TYPE")).lower()
        target: str = str(self.options.get("TARGET")).lower()

        if target_type not in ["username", "name", "domain", "auto"]:
            error(
                "Invalid type. Please choose one of 'username', 'name', 'domain', or 'auto'."
            )
            return

        if target_type == "auto":
            if InputValidator.is_valid_email(target):
                target_type = "email"
            elif InputValidator.is_valid_domain(target):
                target_type = "domain"
            elif len(target.split(" ")) == 1:
                target_type = "username"
            else:
                target_type = "name"

        match target_type:
            case "email":
                await self._check_email(target)
            case "username":
                await self._check_username(target)
            case "name":
                await self._check_name(target)
            case "domain":
                await self._check_domain(target)
            case _:
                error(
                    "Invalid type. Please choose one of 'username', 'name', 'domain', or 'auto'."
                )
                return

    async def _check_email(self, target: str) -> None:
        holehe = HoleheModule()
        await holehe.holehe(target)

    async def _check_username(self, target: str) -> None:
        sherlock = SherlockModule()
        await sherlock.sherlock(target)

    async def _check_name(self, target: str) -> None:
        pass

    async def _check_domain(self, target: str) -> None:
        pass
