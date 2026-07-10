import asyncio
import os
import sys

from cmd2 import Cmd, Color, stylize
from rich.console import Console
from rich.style import Style
from rich.table import Table

from src.core.base_module import BaseModule
from src.core.loader import load_modules
from src.core.managers import ConfigManager, WorkspaceManager
from src.utils.banner import get_banner
from src.utils.logger import set_debug_mode
from src.utils.print_utils import error, info, success


class Shell(Cmd):
    def __init__(self, debug_mode: bool = False) -> None:
        super().__init__()
        self.debug_mode = debug_mode
        self.version = "1.0.0"
        self.modules = load_modules()
        self.current_module = None

        # Creates a ConfigManager to handle API keys, preferences, and workspace registry.
        self.config = ConfigManager("~/.keen/config.db")

        # Starts empty, but attempts to restore the last active workspace.
        self.workspace = None
        last_ws = self.config.get_preference("last_workspace")
        if last_ws:
            w = self.config.get_workspace(last_ws)
            if w and os.path.exists(w["path"]):
                try:
                    self.workspace = WorkspaceManager(w["path"], name=last_ws)
                except Exception:
                    # Clean up if database fails to load
                    self.config.set_preference("last_workspace", "")

        self._update_prompt()

        self.intro = get_banner(self.version)

    def _update_prompt(self) -> None:
        """Centralized prompt updating based on active workspace and module."""
        keen_part = stylize("keen", Style(color=Color.BLUE))
        workspace_part = ""
        module_part = ""

        if self.workspace:
            workspace_part = stylize(
                f"[{self.workspace.name}]", Style(color=Color.GREEN)
            )

        if self.current_module:
            category = self.current_module.metadata.get("category", "")
            name = self.current_module.metadata.get("name", "").lower()
            if category and category != ".":
                display_path = f"{category}/{name}"
            else:
                display_path = name
            module_part = stylize(f"({display_path})", Style(color=Color.RED))

        self.prompt = f"{keen_part}{workspace_part}{module_part} > "

    def complete_use(self, text, line, begidx, endidx):
        """Tab-completion for the 'use' command."""
        # Suggest names that don't look like internal python paths
        return [
            name
            for name in self.modules
            if name.startswith(text.lower()) and "src.modules" not in name
        ]

    def ensure_key_manager_unlocked(self) -> bool:
        """Ensure the key manager is unlocked. If locked, prompts the user to unlock or setup."""
        if self.config.is_unlocked():
            return True

        import getpass

        from src.utils.print_utils import error, success, warn

        if self.config.has_master_password():
            print(
                stylize(
                    "🔑 Stored API keys detected. The API Key Manager is locked.",
                    Style(color=Color.CYAN),
                )
            )
            for _ in range(3):
                try:
                    password = getpass.getpass(
                        "Enter master password to unlock (press Enter to skip): "
                    )
                except (KeyboardInterrupt, EOFError):
                    print()
                    warn("Unlock skipped. API keys will not be loaded.")
                    return False

                if not password:
                    warn("Unlock skipped. API keys will not be loaded.")
                    return False

                if self.config.unlock(password):
                    success("Key manager unlocked successfully!")
                    # If a module is active, automatically load its keys now
                    if self.current_module:
                        self.current_module.load_api_keys(self.config)
                    return True
                else:
                    error("Incorrect password.")
            error("Too many failed attempts. API keys will not be loaded.")
            return False
        else:
            print(stylize("🔑 Secure API Key Manager Setup", Style(color=Color.CYAN)))
            print("Please set a master password to encrypt your stored API keys.")
            try:
                password = getpass.getpass(
                    "Set master password (press Enter to skip): "
                )
            except (KeyboardInterrupt, EOFError):
                print()
                warn("Setup skipped. API keys will not be saved securely.")
                return False

            if not password:
                warn("Setup skipped. API keys will not be saved securely.")
                return False

            try:
                confirm = getpass.getpass("Confirm master password: ")
            except (KeyboardInterrupt, EOFError):
                print()
                warn("Setup skipped. API keys will not be saved securely.")
                return False

            if password != confirm:
                error("Passwords do not match. Setup failed.")
                return False

            if self.config.unlock(password):
                success("Master password set and key manager unlocked successfully!")
                if self.current_module:
                    self.current_module.load_api_keys(self.config)
                return True
            return False

    def do_api_keys(self, arg: str) -> None:
        """Manage API keys securely.

        Usage:
            api_keys list                  - List all registered API key services (masked)
            api_keys set <service> <key>   - Store an API key for a service
            api_keys delete <service>      - Delete an API key for a service
            api_keys unlock                - Unlock the key manager manually
        """
        args = arg.strip().split()
        if not args:
            info("Usage:")
            info(
                "\tapi_keys list                  - List all registered API key services (masked)"
            )
            info("\tapi_keys set <service> <key>   - Store an API key for a service")
            info("\tapi_keys delete <service>      - Delete an API key for a service")
            info("\tapi_keys unlock                - Unlock the key manager manually")
            return

        subcommand = args[0].lower()

        if subcommand == "list":
            if not self.config.is_unlocked():
                if not self.ensure_key_manager_unlocked():
                    return

            keys = self.config.get_all_api_keys()
            if not keys:
                info("No API keys found.")
                return

            table = Table(
                show_header=True,
                header_style="bold blue",
                title="Stored API Keys",
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )
            table.add_column("Service", justify="left", style="cyan", no_wrap=True)
            table.add_column("API Key (Masked)", justify="left", style="white")
            table.add_column("Saved At", justify="left", style="dim white")

            for k in keys:
                svc = k["service"]
                val = k["api_key"]
                ts = k.get("timestamp", "N/A")
                masked = (
                    val[:4] + "*" * (len(val) - 4) if len(val) > 4 else "*" * len(val)
                )
                table.add_row(svc, masked, ts)

            console = Console()
            console.print(table)
            return

        elif subcommand == "set":
            if len(args) < 3:
                error("Usage: api_keys set <service> <key>")
                return

            service = args[1].lower()
            key_val = " ".join(args[2:])

            if not self.config.is_unlocked():
                if not self.ensure_key_manager_unlocked():
                    return

            try:
                self.config.set_api_key(service, key_val)
                success(f"API key for service '{service}' saved successfully!")
                if self.current_module:
                    self.current_module.load_api_keys(self.config)
            except Exception as e:
                error(f"Failed to save API key: {e}")
            return

        elif subcommand == "delete":
            if len(args) < 2:
                error("Usage: api_keys delete <service>")
                return

            service = args[1].lower()
            if not self.config.is_unlocked():
                if not self.ensure_key_manager_unlocked():
                    return

            try:
                self.config.delete_api_key(service)
                success(f"API key for service '{service}' deleted successfully!")
                if self.current_module:
                    for opt_key in self.current_module.metadata.get("options", {}):
                        if (
                            opt_key.lower().endswith(service)
                            or opt_key.lower().endswith(service + "_apikey")
                            or opt_key.lower().endswith(service + "_api_key")
                        ):
                            self.current_module.options[opt_key] = ""
            except Exception as e:
                error(f"Failed to delete API key: {e}")
            return

        elif subcommand == "unlock":
            self.ensure_key_manager_unlocked()
            return

        else:
            error(
                f"Unknown subcommand '{subcommand}'. Use 'api_keys' without arguments to see usage."
            )

    def do_pref(self, arg: str) -> None:
        """Manage configuration preferences.

        Usage:
            pref list                  - List all preferences
            pref set <key> <value>     - Set a preference
            pref get <key>             - Get a preference value
        """
        args = arg.strip().split()
        if not args:
            info("Usage:")
            info("\tpref list                  - List all preferences")
            info("\tpref set <key> <value>     - Set a preference")
            info("\tpref get <key>             - Get a preference value")
            return

        subcommand = args[0].lower()
        blocked_keys = ["last_workspace", "api_keys_salt", "master_password_check"]

        if subcommand == "list":
            cursor = self.config.conn.cursor()
            cursor.execute("SELECT key, value FROM preferences")
            rows = cursor.fetchall()

            table = Table(
                show_header=True,
                header_style="bold blue",
                title="Preferences",
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )
            table.add_column("Key", justify="left", style="cyan", no_wrap=True)
            table.add_column("Value", justify="left", style="white")

            for row in rows:
                key = row[0]
                val = row[1]
                if key in blocked_keys:
                    continue
                table.add_row(key, val)

            console = Console()
            console.print(table)
            return

        elif subcommand == "get":
            if len(args) < 2:
                error("Usage: pref get <key>")
                return
            key = args[1]
            if key in blocked_keys:
                error("Access denied for this preference.")
                return

            val = self.config.get_preference(key)
            if val is not None:
                info(f"{key} = {val}")
            else:
                info(f"Preference '{key}' not found.")
            return

        elif subcommand == "set":
            if len(args) < 3:
                error("Usage: pref set <key> <value>")
                return
            key = args[1]
            val = " ".join(args[2:])
            if key in blocked_keys:
                error("Cannot modify this preference.")
                return

            self.config.set_preference(key, val)
            success(f"Preference '{key}' set to '{val}'.")
            return

        else:
            error(f"Unknown subcommand '{subcommand}'.")

    def complete_proxy(self, text, line, begidx, endidx):
        """Tab-completion for the 'proxy' command."""
        subcommands = ["list", "add", "delete", "load", "test", "set-mode"]
        modes = ["random", "round-robin", "sticky", "off"]
        args = line.split()

        # If user typed 'proxy ', suggest subcommands
        if len(args) == 1 or (len(args) == 2 and not line.endswith(" ")):
            return [sc for sc in subcommands if sc.startswith(text.lower())]

        # If user typed 'proxy set-mode ', suggest rotation modes
        if len(args) >= 2 and args[1].lower() == "set-mode":
            if len(args) == 2 or (len(args) == 3 and not line.endswith(" ")):
                return [m for m in modes if m.startswith(text.lower())]

        return []

    def do_proxy(self, arg: str) -> None:
        """Manage and route traffic through a unified Proxy System.

        Usage:
            proxy list                                - List all configured proxies with latency
            proxy add <url>                           - Add a new proxy URL (e.g. http://ip:port or SOCKS)
            proxy delete <id>                         - Delete a proxy by ID
            proxy load <path>                         - Bulk import proxies from a text file
            proxy test                                - Concurrently test connectivity of all proxies
            proxy set-mode <random|round-robin|sticky|off> - Change rotation or deactivate proxy system
        """
        args = arg.strip().split()
        if not args:
            info("Usage:")
            info(
                "\tproxy list                                - List all configured proxies"
            )
            info("\tproxy add <url>                           - Add a new proxy URL")
            info("\tproxy delete <id>                         - Delete a proxy by ID")
            info(
                "\tproxy load <path>                         - Bulk load proxies from file"
            )
            info(
                "\tproxy test                                - Concurrently test proxy connectivity"
            )
            info(
                "\tproxy set-mode <mode>                     - Set rotation mode (random|round-robin|sticky|off)"
            )
            return

        def mask_url(url: str) -> str:
            from urllib.parse import urlparse

            try:
                parsed = urlparse(url)
                if parsed.password or parsed.username:
                    netloc = ""
                    if parsed.username:
                        netloc += parsed.username
                    if parsed.password:
                        netloc += ":****"
                    netloc += f"@{parsed.hostname}"
                    if parsed.port:
                        netloc += f":{parsed.port}"
                    return parsed._replace(netloc=netloc).geturl()
            except Exception:
                pass
            return url

        subcommand = args[0].lower()

        if subcommand == "list":
            proxies = self.config.get_all_proxies()
            if not proxies:
                info(
                    "No proxies loaded. Add one using 'proxy add <url>' or bulk load with 'proxy load <path>'."
                )
                return

            table = Table(
                show_header=True,
                header_style="bold blue",
                title="Configured Proxies",
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )
            table.add_column("ID", justify="center", style="yellow", width=6)
            table.add_column("Proxy URL", justify="left", style="white")
            table.add_column("Status", justify="center", style="bold")
            table.add_column("Latency", justify="right", style="cyan")
            table.add_column("Enabled", justify="center", style="magenta")

            for p in proxies:
                status = p.get("status", "unknown")
                latency_val = p.get("latency", -1)

                # Dynamic coloring for latency/status
                if status == "online":
                    status_str = stylize("Online", Style(color=Color.GREEN))
                elif status == "offline":
                    status_str = stylize("Offline", Style(color=Color.RED))
                else:
                    status_str = stylize("Unknown", Style(color=Color.GRAY27))

                if latency_val == -1 or status != "online":
                    latency_str = "-"
                else:
                    latency_str = f"{int(latency_val * 1000)}ms"

                enabled_str = "Yes" if p.get("is_enabled", 1) == 1 else "No"
                table.add_row(
                    str(p["id"]),
                    mask_url(p["url"]),
                    status_str,
                    latency_str,
                    enabled_str,
                )

            console = Console()
            console.print(table)

            # Print current proxy routing status
            is_enabled = self.config.get_preference("proxy_enabled") == "true"
            mode = self.config.get_preference("proxy_rotation_mode") or "round-robin"
            if is_enabled:
                info(f"Proxy Routing: ENABLED (Rotation Mode: {mode})")
            else:
                info("Proxy Routing: DISABLED")
            return

        elif subcommand == "add":
            if len(args) < 2:
                error("Usage: proxy add <url>")
                return
            url = args[1]
            if self.config.add_proxy(url):
                success(f"Proxy '{mask_url(url)}' added successfully.")
            else:
                error("Proxy already exists in the database.")
            return

        elif subcommand == "delete":
            if len(args) < 2:
                error("Usage: proxy delete <id | wildcard_pattern>")
                return
            target = args[1]
            if "*" in target or "?" in target or not target.isdigit():
                # Treat as pattern/wildcard
                deleted_count = self.config.delete_proxies_by_pattern(target)
                if deleted_count > 0:
                    success(
                        f"Deleted {deleted_count} proxies matching pattern '{target}'."
                    )
                else:
                    info(f"No proxies found matching pattern '{target}'.")
            else:
                try:
                    proxy_id = int(target)
                    if self.config.delete_proxy(proxy_id):
                        success(f"Proxy with ID {proxy_id} deleted successfully.")
                    else:
                        error(f"Proxy with ID {proxy_id} not found.")
                except ValueError:
                    error("Invalid proxy ID or pattern format.")
            return

        elif subcommand == "load":
            if len(args) < 2:
                error("Usage: proxy load <path>")
                return
            path = args[1]
            if not os.path.exists(path):
                error(f"File not found: {path}")
                return

            try:
                with open(path, "r", encoding="utf-8") as f:
                    urls = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.strip().startswith("#")
                    ]

                added = 0
                for url in urls:
                    if self.config.add_proxy(url):
                        added += 1
                success(
                    f"Loaded {added} new proxies from file successfully (skipped {len(urls) - added} duplicates)."
                )
            except Exception as e:
                error(f"Failed to load proxies from file: {e}")
            return

        elif subcommand == "set-mode":
            if len(args) < 2:
                error("Usage: proxy set-mode <random | round-robin | sticky | off>")
                return
            mode = args[1].lower()
            if mode == "off":
                self.config.set_preference("proxy_enabled", "false")
                success("Proxy system disabled globally.")
            elif mode in ("random", "round-robin", "sticky"):
                self.config.set_preference("proxy_enabled", "true")
                self.config.set_preference("proxy_rotation_mode", mode)
                success(f"Proxy system enabled. Rotation mode set to: {mode}")
            else:
                error(
                    "Invalid rotation mode. Choose from: random, round-robin, sticky, off."
                )
            return

        elif subcommand == "test":
            proxies = self.config.get_all_proxies()
            if not proxies:
                info("No proxies loaded to test.")
                return

            info(
                f"Verifying {len(proxies)} proxies concurrently against https://httpbin.org/ip..."
            )

            async def test_single_proxy(p, sem):
                import time

                import httpx

                async with sem:
                    url = p["url"]
                    proxy_id = p["id"]
                    start_time = time.time()
                    try:
                        async with httpx.AsyncClient(proxy=url, timeout=5.0) as client:
                            resp = await client.get("https://httpbin.org/ip")
                            if resp.status_code == 200:
                                latency = time.time() - start_time
                                self.config.update_proxy_status(
                                    proxy_id, "online", latency
                                )
                                return True
                            else:
                                self.config.update_proxy_status(proxy_id, "offline", -1)
                                return False
                    except Exception:
                        self.config.update_proxy_status(proxy_id, "offline", -1)
                        return False

            async def run_all_tests():
                # Concurrency limit of 10
                sem = asyncio.Semaphore(10)
                tasks = [test_single_proxy(p, sem) for p in proxies]
                results = await asyncio.gather(*tasks)
                online_count = sum(1 for r in results if r)
                offline_count = len(results) - online_count
                success(
                    f"Test complete: {online_count} Online, {offline_count} Offline."
                )

            try:
                asyncio.run(run_all_tests())
            except Exception as e:
                error(f"Testing execution failed: {e}")
            return

        else:
            error(f"Unknown subcommand '{subcommand}'.")

    def do_magic(self, arg: str) -> None:
        """Run automatic detection and module chaining on a target.

        Usage:
            magic <target>
        """
        target = arg.strip()
        if not target:
            error("Usage: magic <target>")
            return

        if not self.workspace:
            info(
                "No active workspace found. Creating/switching to default 'magic' workspace..."
            )
            db_file = "cases/magic.keen"
            os.makedirs("cases", exist_ok=True)
            self.config.add_workspace(
                "magic", db_file, "Default magic chaining workspace"
            )
            try:
                self.workspace = WorkspaceManager(db_file, name="magic")
                self.config.set_preference("last_workspace", "magic")
                self._update_prompt()
            except Exception as e:
                error(f"Failed to initialize 'magic' workspace: {e}")
                return

        if self.config.has_api_keys():
            if not self.config.is_unlocked():
                self.ensure_key_manager_unlocked()

        from src.core.magic import MagicEngine

        engine = MagicEngine(self)

        info(f"Initializing Magic Chaining for: {target}")
        try:
            asyncio.run(engine.run_chain(target, force=True))
            success("Magic Chaining completed!")
        except KeyboardInterrupt:
            error("\nExecution interrupted by user.")
        except Exception as e:
            error(f"Failed during Magic Chaining: {e}")

    def do_playbook(self, arg: str) -> None:
        """Run a YAML-defined playbook (see internal/BEYOND_MALTEGO.md §3.1) against a trigger value.

        Usage:
            playbook <path/to/playbook.yaml> <trigger_value>
        """
        try:
            import shlex

            args = shlex.split(arg.strip())
        except ValueError as e:
            error(f"Error parsing arguments: {e}")
            return

        if len(args) < 2:
            error("Usage: playbook <path/to/playbook.yaml> <trigger_value>")
            return

        path, trigger_value = args[0], args[1]

        if not self.workspace:
            error("No active workspace. Use 'workspace select <name>' first.")
            return

        if self.config.has_api_keys() and not self.config.is_unlocked():
            self.ensure_key_manager_unlocked()

        from src.core.playbooks import PlaybookEngine, load_playbook

        try:
            playbook = load_playbook(path)
        except (ValueError, OSError) as e:
            error(f"Failed to load playbook: {e}")
            return

        engine = PlaybookEngine(self, self.config)
        info(f"Running playbook '{playbook.get('name', path)}' on: {trigger_value}")
        try:
            results = asyncio.run(engine.run(playbook, trigger_value))
        except KeyboardInterrupt:
            error("\nExecution interrupted by user.")
            return
        except ValueError as e:
            error(f"Invalid playbook: {e}")
            return

        total_nodes = sum(len(nodes) for nodes in results.values())
        success(
            f"Playbook completed: {len(results)} step(s) ran, "
            f"{total_nodes} node(s) discovered."
        )

    def do_use(self, arg: str):
        """Select a module to use. You can use the full path or just the module name (e.g. 'use whois')."""
        module_name: str = arg.strip().lower()

        if not module_name:
            error("Usage: use <module_name>")
            return

        if module_name in self.modules:
            module_class = self.modules[module_name]
            self.current_module = module_class()
            self.current_module.shell = self

            # Check if this module uses API keys
            has_api_key_opts = any(
                k.upper().endswith(BaseModule.API_KEY_OPTION_SUFFIXES)
                for k in getattr(module_class, "metadata", {}).get("options", {})
            )
            if has_api_key_opts and self.config.has_api_keys():
                if not self.config.is_unlocked():
                    self.ensure_key_manager_unlocked()

            if self.config.is_unlocked():
                self.current_module.load_api_keys(self.config)

            self._update_prompt()
        else:
            error(
                f"Module '{module_name}' not found. Type 'list modules' to see available modules."
            )

    def do_set(self, arg: str) -> None:
        """Set a module option or a global setting (e.g., debug)."""
        try:
            key, value = arg.split(" ", 1)
            key_lower = key.lower()
            value_lower = value.lower()

            if key_lower == "debug":
                if value_lower in ["true", "on", "1"]:
                    self.debug_mode = True
                    set_debug_mode(True)
                    info("Global debug mode ENABLED.")
                elif value_lower in ["false", "off", "0"]:
                    self.debug_mode = False
                    set_debug_mode(False)
                    info("Global debug mode DISABLED.")
                else:
                    error("Invalid value for debug. Use true/false.")
                return

            if not self.current_module:
                error(
                    "No module selected. Use 'use <module>' first to set module options."
                )
                return

            if self.current_module.set_option(key_lower, value):
                info(f"{key.upper()} => {value}")
            else:
                error(f"Invalid option: {key.upper()}")
        except ValueError:
            error("Usage: set <option> <value>")

    def do_run(self, arg: str):
        """Execute the current module.

        Usage:
            run                    - Execute, prompting for confirmation if the
                                      module is classified active/intrusive
            run --i-understand     - Pre-confirm an active/intrusive module
                                      (skips the interactive y/N prompt)
        """
        if self.current_module:
            self.current_module.shell = self
            flags = {tok.strip().lower() for tok in arg.split()}
            if flags & {"--i-understand", "-y", "--yes"}:
                self.current_module.confirm_execution()
            info("Executing...\n")

            # Record this run in job_history (see `jobs` command) so CLI runs
            # show up in the same history as web-initiated ones. The shell
            # only ever catches KeyboardInterrupt here (per convention, modules
            # are expected to catch/report their own errors) so any other
            # exception still propagates uncaught -- the job just stays
            # "running" in that edge case rather than the shell papering over it.
            job_id = None
            job_workspace = self.workspace
            if job_workspace:
                target = (
                    self.current_module.get_target()
                    if hasattr(self.current_module, "get_target")
                    else ""
                )
                job_id = job_workspace.create_job(
                    self.current_module.metadata.get("name", "module"), str(target)
                )
                job_workspace.update_job(job_id, status="running")

            from src.utils.notifications import notify_job_completion

            try:
                asyncio.run(self.current_module.run())
            except KeyboardInterrupt:
                error("\nExecution interrupted by user.")
                if job_id and job_workspace:
                    job_workspace.update_job(job_id, status="cancelled")
                    asyncio.run(notify_job_completion(self.config, job_workspace, job_id))
                return

            if job_id and job_workspace:
                job_workspace.update_job(job_id, status="completed", progress=1.0)
                asyncio.run(notify_job_completion(self.config, job_workspace, job_id))
        else:
            error("No module selected.")

    def do_back(self, arg: str) -> None:
        """Go back to the main menu."""
        if self.current_module:
            self.current_module = None
        elif self.workspace:
            self.workspace = None
            self.config.set_preference("last_workspace", "")

        self._update_prompt()

    def do_show(self, arg: str) -> None:
        """Show available <options | modules | info | banner>."""
        if not arg:
            error("Usage: show <options | modules | info | banner>")
            return

        if arg.lower() == "options":
            if self.current_module:
                self.current_module.print_options()
            else:
                error("No module selected.")
        elif arg.lower() == "modules":
            self.do_list("modules")
        elif arg.lower() == "info":
            if self.current_module:
                self.current_module.show_metadata()
            else:
                error("No module selected.")
        elif arg.lower() == "banner":
            print(get_banner(self.version))
        else:
            error("Usage: show <options | modules | info | banner>")

    def do_list(self, arg: str) -> None:
        """List available <modules | options | api_keys>."""
        if not arg:
            error("Usage: list <modules | options | api_keys>")
            return

        arg_lower = arg.lower()
        if arg_lower == "modules":
            table = Table(
                show_header=True,
                header_style="bold blue",
                title="Available Modules",
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )
            table.add_column("Module", justify="left", style="cyan", no_wrap=True)
            table.add_column("Description", justify="left", style="white")

            seen = set()
            count = 0
            for key, cls in self.modules.items():
                if cls not in seen:
                    seen.add(cls)
                    count += 1
                    desc = getattr(cls, "metadata", {}).get("description", "")
                    table.add_row(key, desc)

            info(f"Available modules ({count}):")
            console = Console()
            console.print(table)

        elif arg_lower == "options":
            if self.current_module:
                self.current_module.print_options()
            else:
                error("No module selected.")
        elif arg_lower == "api_keys":
            self.do_api_keys("list")
        else:
            error("Usage: list <modules | options | api_keys>")

    def do_clear(self, arg: str) -> None:
        """Clear the screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def do_workspace(self, arg: str) -> None:
        """Manage workspaces.

        Usage:
            workspace                                            - Show active workspace
            workspace list                                       - List all workspaces & active metrics
            workspace select <name>                              - Switch/use an existing workspace
            workspace create <name> [desc] [--scope T:V]...      - Create & register a workspace,
                                                                    optionally declaring scope entries
                                                                    (T: domain|ip|cidr|organization|person)
            workspace set-desc <description>                     - Update current workspace's description
            workspace delete <name>                              - Unregister a workspace (retains database)
            workspace rename <name> <new_name>                   - Rename a workspace
            workspace export <type> <path>                       - Export current workspace (PDF, HTML, Markdown, JSON/STIX2)

        See also the 'scope' command for viewing/editing an existing workspace's scope.
        """
        try:
            import shlex

            args = shlex.split(arg.strip())
        except ValueError as e:
            error(f"Error parsing arguments: {e}")
            return
        if not args:
            if self.workspace:
                info(
                    f"Current workspace: {stylize(self.workspace.name, Style(color=Color.GREEN))}"
                )
            else:
                info(
                    "No workspace currently selected. Use 'workspace list' or 'workspace create <name>'."
                )
                info("Available commands:")
                info("\tworkspace list")
                info("\tworkspace create <name> [description] [--scope <type>:<value>]...")
                info("\tworkspace select <name>")
                info("\tworkspace set-desc <description>")
                info("\tworkspace delete <name>")
                info("\tworkspace rename <name> <new_name>")
                info("\tworkspace export <type> <path>")
            return

        subcommand = args[0].lower()

        if subcommand == "list":
            workspaces = self.config.get_all_workspaces()
            # Auto-discover any unregistered .keen files in cases/
            registered_paths = {w["path"] for w in workspaces}
            discovered = False
            if os.path.exists("cases"):
                for file in os.listdir("cases"):
                    if file.endswith(".keen"):
                        path = f"cases/{file}"
                        norm_path = os.path.normpath(path).replace("\\", "/")
                        if norm_path not in registered_paths:
                            name = os.path.splitext(file)[0]
                            self.config.add_workspace(
                                name, norm_path, "Auto-discovered workspace"
                            )
                            discovered = True

            if discovered:
                workspaces = self.config.get_all_workspaces()

            if not workspaces:
                info(
                    "No workspaces available. Create one with 'workspace create <name>'."
                )
                return

            table = Table(
                show_header=True,
                header_style="bold blue",
                title="Available Workspaces",
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )
            table.add_column("Active", justify="center", style="bold green", width=6)
            table.add_column("Name", justify="left", style="cyan", no_wrap=True)
            table.add_column("Nodes", justify="right", style="yellow")
            table.add_column("Edges", justify="right", style="magenta")
            table.add_column("Scope", justify="right", style="magenta")
            table.add_column("Description", justify="left", style="white")
            table.add_column("Path", justify="left", style="dim white")

            for w in workspaces:
                name = w["name"]
                path = w["path"]
                desc = w["description"] or "No description provided."

                # Check active status
                is_active = (
                    "●" if self.workspace and self.workspace.name == name else ""
                )

                # Count nodes/edges/scope entries from the db file
                nodes_count = 0
                edges_count = 0
                scope_count = 0
                try:
                    if self.workspace and self.workspace.name == name:
                        nodes_count = self.workspace.get_node_count()
                        edges_count = self.workspace.get_edge_count()
                        scope_count = len(self.workspace.list_scope())
                    elif os.path.exists(path):
                        temp_wm = WorkspaceManager(path, name=name)
                        nodes_count = temp_wm.get_node_count()
                        edges_count = temp_wm.get_edge_count()
                        scope_count = len(temp_wm.list_scope())
                        temp_wm.conn.close()
                except Exception as e:
                    desc += f" (Error: {e})"

                scope_display = str(scope_count) if scope_count else "-"
                table.add_row(
                    is_active,
                    name,
                    str(nodes_count),
                    str(edges_count),
                    scope_display,
                    desc,
                    path,
                )

            console = Console()
            console.print(table)
            return
        elif subcommand == "create":
            if len(args) < 2:
                error(
                    "Usage: workspace create <name> [description] [--scope <type>:<value>]..."
                )
                return
            name = args[1]

            # Pull out repeatable --scope <type>:<value> flags (type is one of
            # domain/ip/cidr/organization/person) before treating whatever's
            # left as the free-text description.
            desc_parts: list[str] = []
            scope_specs: list[tuple[str, str]] = []
            rest = args[2:]
            i = 0
            while i < len(rest):
                if rest[i] == "--scope":
                    if i + 1 >= len(rest):
                        error(
                            "--scope requires a value: --scope <type>:<value> "
                            "(type: domain|ip|cidr|organization|person)"
                        )
                        return
                    spec = rest[i + 1]
                    if ":" not in spec:
                        error(f"Invalid --scope value '{spec}'. Expected <type>:<value>.")
                        return
                    scope_type, value = spec.split(":", 1)
                    scope_type = scope_type.lower()
                    if scope_type not in (
                        "domain",
                        "ip",
                        "cidr",
                        "organization",
                        "person",
                    ):
                        error(
                            f"Invalid scope type '{scope_type}' in '--scope {spec}'. "
                            "Must be one of: domain, ip, cidr, organization, person."
                        )
                        return
                    scope_specs.append((scope_type, value))
                    i += 2
                else:
                    desc_parts.append(rest[i])
                    i += 1
            desc = " ".join(desc_parts)

            if not all(c.isalnum() or c in " _-" for c in name):
                error(
                    "Workspace name must be alphanumeric (underscores/hyphens/spaces allowed)."
                )
                return

            from src.utils.config_util import get_valid_name

            filename = get_valid_name(name)
            db_file = f"cases/{filename}.keen"
            try:
                self.config.add_workspace(name, db_file, desc)
            except ValueError as e:
                error(str(e))
                return

            self.workspace = WorkspaceManager(db_file, name=name)
            self.config.set_preference("last_workspace", name)
            self._update_prompt()

            for scope_type, value in scope_specs:
                self.workspace.add_scope_entry(scope_type, value)

            info(
                f"Created and switched to workspace: {stylize(name, Style(color=Color.GREEN))}"
            )
            if desc:
                info(f"Description: {desc}")
            if scope_specs:
                info(
                    f"Declared {len(scope_specs)} scope entr{'y' if len(scope_specs) == 1 else 'ies'}."
                )
                if any(t == "person" for t, _ in scope_specs):
                    from src.utils.print_utils import warn

                    warn(
                        "Person scope entries added this way have no consent basis recorded -- "
                        'add one with \'scope add person "<name>" "<consent basis>"\'.'
                    )
            return
        elif subcommand in ("select", "use"):
            if len(args) < 2:
                error("Usage: workspace select <name>")
                return
            name = args[1]
            w: dict | None = self.config.get_workspace(name)
            if not w:
                filename = name.replace(" ", "_")
                db_file = f"cases/{filename}.keen"
                if os.path.exists(db_file):
                    self.config.add_workspace(
                        name, db_file, "Auto-discovered workspace"
                    )
                    w = self.config.get_workspace(name)
                else:
                    error(
                        f"Workspace '{name}' does not exist. Use 'workspace create \"{name}\"' to create it."
                    )
                    return

            # Defensive check: if w is still None (e.g. due to DB lock or read error), fallback to direct path
            db_path = w["path"] if w else f"cases/{name.replace(' ', '_')}.keen"

            try:
                self.workspace = WorkspaceManager(db_path, name=name)
                self.config.set_preference("last_workspace", name)
                self._update_prompt()
                info(
                    f"Switched to workspace: {stylize(name, Style(color=Color.GREEN))}."
                )
            except Exception as e:
                error(f"Failed to load workspace database at '{db_path}': {e}")
            return
        elif subcommand == "set-desc":
            if not self.workspace:
                error("No active workspace selected. Select a workspace first.")
                return
            if len(args) < 2:
                error("Usage: workspace set-desc <description>")
                return

            parts = arg.strip().split(maxsplit=1)
            description = parts[1] if len(parts) > 1 else ""

            self.config.update_workspace_description(self.workspace.name, description)
            info(f"Description updated for workspace '{self.workspace.name}'.")
            return
        elif subcommand == "delete":
            if len(args) < 2:
                error("Usage: workspace delete <name>")
                return
            name = args[1]
            w = self.config.get_workspace(name)
            if not w:
                error(f"Workspace '{name}' not found.")
                return

            if self.workspace and self.workspace.name == name:
                self.workspace = None
                self.config.set_preference("last_workspace", "")
                self._update_prompt()

            self.config.delete_workspace(name)
            info(
                f"Unregistered workspace: '{name}'. (Database file '{w['path']}' was kept)."
            )
            return
        elif subcommand == "rename":
            if len(args) < 3:
                error("Usage: workspace rename <name> <new_name>")
                return
            name = args[1]
            new_name = args[2]
            w = self.config.get_workspace(name)
            if not w:
                error(f"Workspace '{name}' not found.")
                return
            self.config.rename_workspace(name, new_name)
            info(f"Renamed workspace '{name}' to '{new_name}'.")
            return
        elif subcommand == "export":
            if not self.workspace:
                error("No active workspace selected. Select a workspace first.")
                return

            if len(args) < 3:
                error(
                    "Usage: workspace export <type> <path>\nTypes: pdf, html, markdown, json, stix2"
                )
                return

            type = args[1]
            path = args[2]

            self.workspace.export(type, path)

            info(f"Exported workspace '{self.workspace.name}' to '{path}'.")
            return
        else:
            # Fallback direct switch/creation matching original behavior
            name = args[0]
            w = self.config.get_workspace(name)
            if w:
                self.workspace = WorkspaceManager(w["path"], name=name)
                self.config.set_preference("last_workspace", name)
                self._update_prompt()
                info(
                    f"Switched to workspace: {stylize(name, Style(color=Color.GREEN))}."
                )
            else:
                from src.utils.config_util import get_valid_name

                filename = get_valid_name(name)
                db_file = f"cases/{filename}.keen"
                if os.path.exists(db_file):
                    try:
                        self.config.add_workspace(
                            name, db_file, "Auto-discovered workspace"
                        )
                    except ValueError as e:
                        error(str(e))
                        return
                    self.workspace = WorkspaceManager(db_file, name=name)
                    self.config.set_preference("last_workspace", name)
                    self._update_prompt()
                    info(
                        f"Discovered and switched to workspace: {stylize(name, Style(color=Color.GREEN))}."
                    )
                else:
                    if not all(c.isalnum() or c in " _-" for c in name):
                        error(
                            "Workspace name must be alphanumeric (underscores/hyphens/spaces allowed)."
                        )
                        return
                    try:
                        self.config.add_workspace(
                            name, db_file, f"Workspace for {name}"
                        )
                    except ValueError as e:
                        error(str(e))
                        return
                    self.workspace = WorkspaceManager(db_file, name=name)
                    self.config.set_preference("last_workspace", name)
                    self._update_prompt()
                    info(
                        f"Created and switched to workspace: {stylize(name, Style(color=Color.GREEN))}."
                    )

    def do_jobs(self, arg: str) -> None:
        """Manage the active workspace's job history (job_history table).

        Usage:
            jobs list                 - Show pending/running jobs
            jobs history [status]     - Show all jobs, optionally filtered by status
            jobs cancel <job_id>      - Request cancellation of a running job
            jobs logs <job_id>        - Show captured log lines for a job
        """
        if not self.workspace:
            error("No active workspace. Use 'workspace select <name>' first.")
            return

        try:
            import shlex

            args = shlex.split(arg.strip())
        except ValueError as e:
            error(f"Error parsing arguments: {e}")
            return

        if not args:
            error("Usage: jobs <list | history | cancel <job_id> | logs <job_id>>")
            return

        subcommand = args[0].lower()

        def _print_jobs_table(jobs: list, title: str) -> None:
            if not jobs:
                info("No jobs found.")
                return
            table = Table(
                show_header=True,
                header_style="bold blue",
                title=title,
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )
            table.add_column("Job ID", justify="left", style="cyan", no_wrap=True)
            table.add_column("Module", justify="left", style="white")
            table.add_column("Target", justify="left", style="white")
            table.add_column("Status", justify="center", style="magenta")
            table.add_column("Progress", justify="right", style="yellow")
            table.add_column("Started", justify="left", style="dim white")
            for job in jobs:
                table.add_row(
                    job["job_id"][:8],
                    job["module_name"],
                    job["target_value"],
                    job["status"],
                    f"{job.get('progress') or 0.0:.0%}",
                    str(job.get("started_at") or ""),
                )
            console = Console()
            console.print(table)

        if subcommand == "list":
            jobs = [
                j
                for j in self.workspace.list_jobs()
                if j["status"] in ("pending", "running")
            ]
            _print_jobs_table(jobs, "Active Jobs")
        elif subcommand == "history":
            status = args[1] if len(args) > 1 else None
            jobs = self.workspace.list_jobs(status=status)
            _print_jobs_table(jobs, "Job History")
        elif subcommand == "cancel":
            if len(args) < 2:
                error("Usage: jobs cancel <job_id>")
                return
            job_id = self._resolve_job_id(args[1])
            if not job_id:
                error(f"No job found matching '{args[1]}'.")
                return
            if self.workspace.cancel_job(job_id):
                info(f"Job {job_id} marked cancelled.")
            else:
                error(f"Job '{args[1]}' not found.")
        elif subcommand == "logs":
            if len(args) < 2:
                error("Usage: jobs logs <job_id>")
                return
            job_id = self._resolve_job_id(args[1])
            job = self.workspace.get_job(job_id) if job_id else None
            if not job:
                error(f"Job '{args[1]}' not found.")
                return
            info(f"Logs for job {job['job_id']} ({job['module_name']}):")
            for line in job.get("logs", []):
                print(line)
            if job.get("error_message"):
                error(f"Error: {job['error_message']}")
        else:
            error("Usage: jobs <list | history | cancel <job_id> | logs <job_id>>")

    def _resolve_job_id(self, partial_id: str) -> str | None:
        """Resolve a full or 8-char-prefix job id (as shown in the jobs table) to a full job_id."""
        if not self.workspace:
            return None
        if self.workspace.get_job(partial_id):
            return partial_id
        for job in self.workspace.list_jobs():
            if job["job_id"].startswith(partial_id):
                return job["job_id"]
        return None

    def do_scope(self, arg: str) -> None:
        """Manage the active workspace's declared scope (see internal/BEYOND_MALTEGO.md §1.1).

        A case with no declared scope has enforcement opted out -- every
        discovery is treated as in-scope. Declaring at least one entry turns
        enforcement on: any discovered node that doesn't match a declared
        domain/IP/CIDR/organization/person is still ingested, but flagged as
        quarantined (see 'scope quarantined') rather than silently trusted.

        Usage:
            scope list                                - List declared scope entries
            scope add <type> <value> [consent_basis]  - Add an entry (type: domain|ip|cidr|organization|person)
            scope remove <id>                         - Remove a scope entry
            scope quarantined                         - List nodes quarantined as out-of-scope
        """
        if not self.workspace:
            error("No active workspace. Use 'workspace select <name>' first.")
            return

        try:
            import shlex

            args = shlex.split(arg.strip())
        except ValueError as e:
            error(f"Error parsing arguments: {e}")
            return

        if not args:
            error(
                "Usage: scope <list | add <type> <value> [consent_basis] | remove <id> | quarantined>"
            )
            return

        subcommand = args[0].lower()

        if subcommand == "list":
            entries = self.workspace.list_scope()
            if not entries:
                info(
                    "No scope declared -- enforcement is opted out; every discovery is treated as in-scope."
                )
                return
            table = Table(
                show_header=True,
                header_style="bold blue",
                title="Declared Scope",
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )
            table.add_column("ID", justify="right", style="cyan")
            table.add_column("Type", justify="left", style="magenta")
            table.add_column("Value", justify="left", style="white")
            table.add_column("Consent Basis", justify="left", style="dim white")
            for e in entries:
                table.add_row(
                    str(e["id"]), e["scope_type"], e["value"], e.get("consent_basis") or ""
                )
            console = Console()
            console.print(table)
        elif subcommand == "add":
            if len(args) < 3:
                error("Usage: scope add <type> <value> [consent_basis]")
                return
            scope_type, value = args[1].lower(), args[2]
            if scope_type not in ("domain", "ip", "cidr", "organization", "person"):
                error("Type must be one of: domain, ip, cidr, organization, person")
                return
            consent_basis = " ".join(args[3:]) if len(args) > 3 else ""
            entry_id = self.workspace.add_scope_entry(scope_type, value, consent_basis)
            success(f"Added scope entry #{entry_id}: {scope_type} '{value}'.")
        elif subcommand == "remove":
            if len(args) < 2:
                error("Usage: scope remove <id>")
                return
            try:
                entry_id = int(args[1])
            except ValueError:
                error("Scope entry id must be a number (see 'scope list').")
                return
            if self.workspace.remove_scope_entry(entry_id):
                success(f"Removed scope entry #{entry_id}.")
            else:
                error(f"No scope entry with id {entry_id}.")
        elif subcommand == "quarantined":
            nodes = self.workspace.get_quarantined_nodes()
            if not nodes:
                info("No quarantined nodes.")
                return
            table = Table(
                show_header=True,
                header_style="bold blue",
                title="Quarantined Nodes",
                title_style="bold cyan",
                show_lines=True,
                expand=True,
            )
            table.add_column("ID", justify="right", style="cyan")
            table.add_column("Type", justify="left", style="magenta")
            table.add_column("Value", justify="left", style="white")
            table.add_column("Reason", justify="left", style="yellow")
            for n in nodes:
                table.add_row(
                    str(n["id"]), n["type"], n["value"], n.get("quarantine_reason") or ""
                )
            console = Console()
            console.print(table)
        else:
            error(
                "Usage: scope <list | add <type> <value> [consent_basis] | remove <id> | quarantined>"
            )

    def do_merge(self, arg: str) -> None:
        """Merge nodes into one identity (Entity Resolution, see internal/BEYOND_MALTEGO.md §2.4).

        Re-points every edge from the absorbed node(s) onto the canonical
        node, unions their metadata, and logs one provenance ledger entry.
        This is always a deliberate, explicit operator action -- nothing in
        Keen merges nodes automatically.

        Usage:
            merge <canonical_value> <absorbed_value> [absorbed_value...]
        """
        if not self.workspace:
            error("No active workspace. Use 'workspace select <name>' first.")
            return

        try:
            import shlex

            args = shlex.split(arg.strip())
        except ValueError as e:
            error(f"Error parsing arguments: {e}")
            return

        if len(args) < 2:
            error("Usage: merge <canonical_value> <absorbed_value> [absorbed_value...]")
            return

        canonical_value, absorbed_values = args[0], args[1:]

        canonical_id = self.workspace.get_node_id(canonical_value)
        if canonical_id is None:
            error(f"No node found with value '{canonical_value}'.")
            return

        absorbed_ids = []
        for value in absorbed_values:
            node_id = self.workspace.get_node_id(value)
            if node_id is None:
                error(f"No node found with value '{value}'.")
                return
            absorbed_ids.append(node_id)

        if self.workspace.merge_nodes(canonical_id, absorbed_ids, actor="operator"):
            success(f"Merged {len(absorbed_ids)} node(s) into '{canonical_value}'.")
        else:
            error("Merge failed -- canonical node not found or no absorbed nodes matched.")

    def do_web(self, arg: str) -> None:
        """Start the Keen API web server.

        Usage:
            web start [--host <host>] [--port <port>]
        """
        args = arg.strip().split()
        if not args or args[0].lower() != "start":
            error("Usage: web start [--host <host>] [--port <port>]")
            return

        host = "127.0.0.1"
        port = 8000

        try:
            if "--host" in args:
                idx = args.index("--host")
                host = args[idx + 1]
            if "--port" in args:
                idx = args.index("--port")
                port = int(args[idx + 1])
        except (ValueError, IndexError):
            error("Invalid arguments. Usage: web start [--host <host>] [--port <port>]")
            return

        from src.api.server import start_server

        info(f"Starting web server on {host}:{port}...")
        start_server(host=host, port=port, debug=self.debug_mode)

    def do_exit(self, args: str) -> None:
        """Exit the shell."""
        self.do_quit("")
        sys.exit(0)
