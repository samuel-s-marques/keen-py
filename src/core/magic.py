import asyncio
import re
from collections import deque

from src.core.loader import load_modules
from src.core.options import as_option
from src.utils.print_utils import error, info, warn
from src.utils.utils import clean_node_value
from src.utils.validator import InputValidator

# Precompiled once instead of on every detect_type() call.
_HASH_RE = re.compile(r"^[a-fA-F0-9]{32}$|^[a-fA-F0-9]{40}$|^[a-fA-F0-9]{64}$")
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,30}$")


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

    # Fallback map from node type -> module keys to chain. This is now derived
    # automatically from each module's metadata ``magic_consumes`` declaration
    # (see _build_type_map); the hardcoded map is kept only as a safety net for
    # any node type no installed module declares, and as documentation.
    #
    # Email_Finder is intentionally NOT chained from a domain: it requires a
    # person's FNAME/LNAME that magic cannot supply from a bare domain, so
    # pre_run would always fail. Run it manually instead.
    TYPE_TO_MODULE_MAP = {
        "email-addr": [
            "enumeration/email_enrichment",
            "enumeration/email_verification",
            "enumeration/user_scanner",
        ],
        "domain-name": ["enumeration/domain_enrichment"],
        "user-account": [
            "enumeration/sherlock",
            "enumeration/github_enumeration",
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
        self.type_to_modules = self._build_type_map()
        self.executed_pairs = set()

    def _build_type_map(self) -> dict:
        """Build node-type -> [module keys] from module metadata declarations.

        A module opts into magic chaining by declaring ``"magic_consumes":
        [<node-type>, ...]`` in its ``metadata``. This removes the need to edit
        the engine when adding a module. The hardcoded ``TYPE_TO_MODULE_MAP`` is
        merged in as a fallback for any type no module declares, so behavior is
        never *reduced* relative to the static map.
        """
        discovered: dict = {}
        seen: set = set()
        for cls in self.modules.values():
            meta = getattr(cls, "metadata", {}) or {}
            consumes = meta.get("magic_consumes") or []
            if not consumes:
                continue
            category = meta.get("category", "")
            name = (meta.get("name") or "").lower()
            if not name:
                continue
            canonical = f"{category}/{name}" if category and category != "." else name
            if canonical in seen:
                continue  # loader registers each module under several keys
            seen.add(canonical)
            for node_type in consumes:
                discovered.setdefault(node_type, []).append(canonical)

        # Merge the static fallback for any node type not covered by metadata.
        for node_type, mods in self.TYPE_TO_MODULE_MAP.items():
            discovered.setdefault(node_type, list(mods))
        return discovered

    @staticmethod
    def detect_type(value: str) -> str | None:
        """Automatically detect node type based on patterns."""
        value = clean_node_value(value).strip()
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
        if _HASH_RE.match(value):
            return "x-hash"

        # Username / Account Target
        if _USERNAME_RE.match(value):
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

        # Suppress re-entrant chaining: while this chain runs, any module it
        # executes will reach post_run and must NOT spawn its own MagicEngine
        # (which would re-chain the same nodes with a fresh executed_pairs set).
        prev_running = getattr(self.shell, "_magic_running", False)
        if self.shell is not None:
            self.shell._magic_running = True

        try:
            await self._run_chain_inner(initial_value, initial_type)
        finally:
            if self.shell is not None:
                self.shell._magic_running = prev_running

    async def _run_chain_inner(
        self, initial_value: str, initial_type: str | None = None
    ):
        try:
            max_depth = int(self.config.get_preference("magic_max_depth") or "2")
        except (ValueError, TypeError):
            max_depth = 2
        interactive = self.config.get_preference("magic_interactive") == "true"
        exclude_str = self.config.get_preference("magic_exclude_modules") or ""
        excluded_modules = [
            m.strip().lower() for m in exclude_str.split(",") if m.strip()
        ]

        queue = deque()
        detected = initial_type or self.detect_type(initial_value)
        if not detected:
            msg = f"Could not automatically detect type for value: {initial_value}"
            warn(msg)
            print(f"[magic] {msg}")
            return

        queue.append((initial_value, detected, 0))

        while queue:
            value, node_type, depth = queue.popleft()

            # Yield to event loop to keep the FastAPI server responsive
            await asyncio.sleep(0.01)

            if depth >= max_depth:
                continue

            # Skip common usernames
            if node_type == "user-account" and value.lower() in self.COMMON_USERNAMES:
                msg = f"Generic username '{value}' skipped to prevent massive false-positives."
                info(msg)
                print(f"[magic] {msg}")
                continue

            # Get modules matching this node type
            target_modules = self.type_to_modules.get(node_type, [])
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
                                # Clean prefixed values so downstream
                                # modules receive plain targets
                                cleaned_val = clean_node_value(node_val)
                                queue.append((cleaned_val, node_t, depth + 1))

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
            if as_option(opt_val).validator:
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

        async def magic_post_run(results: dict, raw=None):
            # Capture results for chaining
            discovered_nodes.extend(results.get("nodes", []))
            # Save results to the active workspace
            await original_post_run(results, raw=raw)

        module_instance.post_run = magic_post_run

        try:
            # Execute
            await module_instance.run()
        finally:
            if hasattr(module_instance, "cleanup"):
                module_instance.cleanup()

        return discovered_nodes
