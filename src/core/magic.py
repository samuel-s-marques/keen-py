from src.utils.print_utils import warn, info, error
import re
import asyncio
from src.core.loader import load_modules
from src.utils.validator import InputValidator


class MagicEngine:
    COMMON_USERNAMES = {
        "admin",
        "support",
        "test",
        "root",
        "user",
        "guest",
        "info",
        "contact",
        "sales",
        "api",
        "default",
        "staff",
        "system",
        "administrator",
        "none",
        "null",
        "undefined",
        "temp",
        "temporary",
        "test1",
        "test2",
        "owner",
        "master",
        "webmaster",
        "postmaster",
        "hostmaster",
        "service",
        "services",
        "office",
        "mail",
        "marketing",
        "billing",
        "jobs",
        "hr",
        "careers",
        "press",
    }

    TYPE_TO_MODULE_MAP = {
        "email-addr": [
            "enumeration/email_enrichment",
            "enumeration/email_verification",
            "enumeration/user_scanner",
        ],
        "domain-name": ["enumeration/domain_enrichment", "enumeration/email_finder"],
        "user-account": [
            "enumeration/sherlock",
            "enumeration/github",
            "enumeration/user_scanner",
        ],
        "x-phone-number": ["enumeration/phone_verification"],
    }

    def __init__(self, shell, config=None):
        self.shell = shell
        if config:
            self.config = config
        elif hasattr(shell, "config") and shell.config:
            self.config = shell.config
        else:
            from src.core.managers import ConfigManager

            self.config = ConfigManager("~/.keen/config.db")

        self.modules = load_modules()
        self.executed_pairs = set()

    @staticmethod
    def detect_type(value: str) -> str | None:
        """Automatically detect node type based on patterns."""
        value = value.strip()
        if not value:
            return None

        # Email Address
        if InputValidator.is_valid_email(value):
            return "email-addr"

        # IP Address
        if InputValidator.is_valid_ip(value):
            return "ipv6-addr" if ":" in value else "ipv4-addr"

        # URL
        if InputValidator.is_valid_url(value):
            return "x-url"

        # Domain Name
        if InputValidator.is_valid_domain(value):
            return "domain-name"

        # Phone Number
        if InputValidator.is_valid_phone_number(value):
            return "x-phone-number"

        # Hashes (MD5, SHA-1, SHA-256)
        if re.match(r"^[a-fA-F0-9]{32}$", value):
            return "x-hash"
        if re.match(r"^[a-fA-F0-9]{40}$", value):
            return "x-hash"
        if re.match(r"^[a-fA-F0-9]{64}$", value):
            return "x-hash"

        # Username / Account Target
        if re.match(r"^[a-zA-Z0-9_.-]{3,30}$", value):
            return "user-account"

        return None

    async def run_chain(
        self, initial_value: str, initial_type: str | None = None, force: bool = False
    ):
        """Runs the magic chaining algorithm on an initial target value."""
        if not force:
            enabled = self.config.get_preference("magic_enabled") == "true"
            if not enabled:
                return

        max_depth = int(self.config.get_preference("magic_max_depth") or "2")
        interactive = self.config.get_preference("magic_interactive") == "true"
        exclude_str = self.config.get_preference("magic_exclude_modules") or ""
        excluded_modules = [
            m.strip().lower() for m in exclude_str.split(",") if m.strip()
        ]

        queue = []
        detected = initial_type or self.detect_type(initial_value)
        if not detected:
            msg = f"Could not automatically detect type for value: {initial_value}"
            warn(msg)
            print(f"[magic] {msg}")
            return

        queue.append((initial_value, detected, 0))

        while queue:
            value, node_type, depth = queue.pop(0)

            if depth >= max_depth:
                continue

            # Skip common usernames
            if node_type == "user-account" and value.lower() in self.COMMON_USERNAMES:
                msg = f"Generic username '{value}' skipped to prevent massive false-positives."
                info(msg)
                print(f"[magic] {msg}")
                continue

            # Get modules matching this node type
            target_modules = self.TYPE_TO_MODULE_MAP.get(node_type, [])
            if not target_modules:
                continue

            tasks = []
            for mod_name in target_modules:
                # Find matching module class in self.modules
                mod_class = self.modules.get(mod_name)
                if not mod_class:
                    short_name = mod_name.split("/")[-1]
                    mod_class = self.modules.get(short_name)

                if not mod_class:
                    continue

                friendly_name = (
                    getattr(mod_class, "metadata", {}).get("name", "").lower()
                )

                # Exclusion check
                if (
                    mod_name.lower() in excluded_modules
                    or friendly_name.lower() in excluded_modules
                ):
                    info(f"Module '{mod_name}' is excluded. Skipping.")
                    continue

                # Deduplication check
                pair = (value, friendly_name)
                if pair in self.executed_pairs:
                    continue

                # Interactive confirmation (only for CLI shell context)
                is_web = getattr(self.shell, "is_web_context", False)
                if interactive and not is_web:
                    try:
                        ans = input(
                            f"[magic] Run module '{friendly_name}' on '{value}'? [Y/n]: "
                        )
                        if ans.strip().lower() in ["n", "no"]:
                            continue
                    except (KeyboardInterrupt, EOFError):
                        print()
                        return

                self.executed_pairs.add(pair)
                tasks.append((friendly_name, self._run_module(mod_class, value, depth)))

            if tasks:
                # Run concurrently using asyncio.gather
                friendly_names = [t[0] for t in tasks]
                coroutines = [t[1] for t in tasks]
                results = await asyncio.gather(*coroutines, return_exceptions=True)

                for name, result in zip(friendly_names, results):
                    if isinstance(result, BaseException):
                        error(f"Error executing module '{name}': {result}")
                        print(f"[magic] Error executing module '{name}': {result}")
                    elif result:
                        # Queue newly discovered nodes for next iteration
                        for node in result:
                            node_val = node.get("value")
                            node_t = node.get("type")
                            if node_val and node_t:
                                queue.append((node_val, node_t, depth + 1))

    async def _run_module(self, mod_class, target_value: str, depth: int) -> list:
        """Instantiates and executes a module class, intercepting and returning its post_run results."""
        friendly_name = getattr(mod_class, "metadata", {}).get("name", "")
        msg = f"Magic chaining depth {depth}: running '{friendly_name}' on '{target_value}'"
        info(msg)
        print(f"[magic] {msg}")

        module_instance = mod_class()
        module_instance.shell = self.shell
        module_instance.is_web_context = getattr(self.shell, "is_web_context", False)

        if self.config.is_unlocked():
            module_instance.load_api_keys(self.config)

        # Set target option
        target_option = None
        for opt_key, opt_val in (
            getattr(mod_class, "metadata", {}).get("options", {}).items()
        ):
            validator = opt_val[3]
            if validator:
                target_option = opt_key
                break
        if not target_option:
            target_option = "TARGET"

        module_instance.set_option(target_option, target_value)

        # Validate options
        if not module_instance.pre_run():
            warn(
                f"Pre-run validation failed for module '{getattr(mod_class, 'metadata', {}).get('name')}' on target '{target_value}'"
            )
            return []

        original_post_run = module_instance.post_run
        discovered_nodes = []

        async def magic_post_run(results: dict):
            # Capture results for chaining
            discovered_nodes.extend(results.get("nodes", []))
            # Save results to the active workspace
            await original_post_run(results)

        module_instance.post_run = magic_post_run

        # Execute
        await module_instance.run()
        return discovered_nodes
