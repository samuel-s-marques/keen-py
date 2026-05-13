from src.utils.print_utils import error
from src.utils.validator import InputValidator
from src.core.base_module import BaseModule
from src.modules.enumeration.sherlock_module import SherlockModule
from src.modules.enumeration.holehe_module import HoleheModule
from src.modules.enumeration.phone_verification_module import PhoneVerificationModule
from src.modules.enumeration.email_verification_module import EmailVerificationModule
from src.modules.enumeration.email_enrichment_module import EmailEnrichmentModule
from src.modules.enumeration.github_module import GitHubModule
import asyncio


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
                "email,phone,username,domain,name",
            ],
            "TYPE": [
                "auto",
                False,
                "The type of the target (username, name, domain, phone, auto).",
                "",
            ],
            "TIMEOUT": [
                "15",
                False,
                "Timeout for each module execution in seconds.",
                "",
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

        if target_type not in ["username", "name", "phone", "domain", "auto"]:
            error(
                "Invalid type. Please choose one of 'username', 'name', 'domain', 'phone', or 'auto'."
            )
            return

        if target_type == "auto":
            if InputValidator.is_valid_email(target):
                target_type = "email"
            elif InputValidator.is_valid_phone_number(target):
                target_type = "phone"
            elif InputValidator.is_valid_domain(target):
                target_type = "domain"
            elif len(target.split(" ")) == 1:
                target_type = "username"
            else:
                target_type = "name"

        match target_type:
            case "email":
                await self.loading(
                    f"Checking {target} on social media and verifying email...",
                    self._check_email,
                    target,
                )
            case "username":
                await self.loading(
                    f"Scanning {target} on social media and GitHub...",
                    self._check_username,
                    target,
                )
            case "phone":
                await self.loading(
                    f"Verifying phone number {target}...",
                    self._check_phone,
                    target,
                )
            case "name":
                await self.loading(
                    f"Searching for {target} on social media...",
                    self._check_name,
                    target,
                )
            case "domain":
                await self.loading(
                    f"Researching {target} on the web...",
                    self._check_domain,
                    target,
                )
            case _:
                error(
                    "Invalid type. Please choose one of 'username', 'name', 'domain', 'phone', or 'auto'."
                )
                return

    async def _check_email(self, target: str) -> None:
        timeout = int(self.options.get("TIMEOUT", 15))

        # Initialize modules
        holehe = HoleheModule()
        email_ver = EmailVerificationModule()
        email_enr = EmailEnrichmentModule()

        # Run concurrently
        await asyncio.gather(
            holehe.holehe(target),
            email_ver.execute(target, timeout=timeout),
            email_enr.execute(target),
            return_exceptions=True,
        )

    async def _check_username(self, target: str) -> None:
        # Initialize modules
        sherlock = SherlockModule()
        github = GitHubModule()

        # Run concurrently
        await asyncio.gather(
            sherlock.sherlock(target),
            github.execute(target),
            return_exceptions=True,
        )

    async def _check_phone(self, target: str) -> None:
        timeout = int(self.options.get("TIMEOUT", 15))
        phone_verification = PhoneVerificationModule()
        await phone_verification.execute(target, timeout=timeout)

    async def _check_name(self, target: str) -> None:
        # Future: Integrate modules that search by name (e.g., LinkedIn, Whitepages API)
        pass

    async def _check_domain(self, target: str) -> None:
        # Future: Integrate domain-related OSINT modules
        pass
