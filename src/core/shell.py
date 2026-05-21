from src.utils.banner import get_banner
import sys
from src.core.managers import WorkspaceManager
from src.core.managers import ConfigManager
from cmd2 import Cmd, Color, stylize
from rich.console import Console
from rich.table import Table
from rich.style import Style
import os
import asyncio

from src.core.loader import load_modules
from src.utils.print_utils import error, info, success
from src.utils.logger import set_debug_mode


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
        from src.utils.print_utils import success, warn, error

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
        except Exception as e:
            error(f"Failed during Magic Chaining: {e}")

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
                k.endswith("_APIKEY") or k.endswith("_API_KEY")
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
        """Execute the current module."""
        if self.current_module:
            self.current_module.shell = self
            info("Executing...\n")
            asyncio.run(self.current_module.run())
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
            workspace                           - Show active workspace
            workspace list                      - List all workspaces & active metrics
            workspace select <name>             - Switch/use an existing workspace
            workspace create <name> [desc]      - Create & register a workspace
            workspace set-desc <description>    - Update current workspace's description
            workspace delete <name>             - Unregister a workspace (retains database)
            workspace rename <name> <new_name>  - Rename a workspace
            workspace export <type> <path>      - Export current workspace (PDF, HTML, Markdown, JSON/STIX2)
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
                info("\tworkspace create <name> [description]")
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

                # Count nodes/edges from the db file
                nodes_count = 0
                edges_count = 0
                try:
                    if self.workspace and self.workspace.name == name:
                        nodes_count = self.workspace.get_node_count()
                        edges_count = self.workspace.get_edge_count()
                    elif os.path.exists(path):
                        temp_wm = WorkspaceManager(path, name=name)
                        nodes_count = temp_wm.get_node_count()
                        edges_count = temp_wm.get_edge_count()
                        temp_wm.conn.close()
                except Exception as e:
                    desc += f" (Error: {e})"

                table.add_row(
                    is_active, name, str(nodes_count), str(edges_count), desc, path
                )

            console = Console()
            console.print(table)
            return

        elif subcommand == "create":
            if len(args) < 2:
                error("Usage: workspace create <name> [description]")
                return
            name = args[1]
            desc = " ".join(args[2:]) if len(args) > 2 else ""

            if not all(c.isalnum() or c in " _-" for c in name):
                error(
                    "Workspace name must be alphanumeric (underscores/hyphens/spaces allowed)."
                )
                return

            filename = name.replace(" ", "_")
            db_file = f"cases/{filename}.keen"
            self.config.add_workspace(name, db_file, desc)

            self.workspace = WorkspaceManager(db_file, name=name)
            self.config.set_preference("last_workspace", name)
            self._update_prompt()

            info(
                f"Created and switched to workspace: {stylize(name, Style(color=Color.GREEN))}"
            )
            if desc:
                info(f"Description: {desc}")
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
                error("Usage: workspace export <type> <path>")
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
                filename = name.replace(" ", "_")
                db_file = f"cases/{filename}.keen"
                if os.path.exists(db_file):
                    self.config.add_workspace(
                        name, db_file, "Auto-discovered workspace"
                    )
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
                    self.config.add_workspace(name, db_file, f"Workspace for {name}")
                    self.workspace = WorkspaceManager(db_file, name=name)
                    self.config.set_preference("last_workspace", name)
                    self._update_prompt()
                    info(
                        f"Created and switched to workspace: {stylize(name, Style(color=Color.GREEN))}."
                    )

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
