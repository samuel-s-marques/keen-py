from src.core.managers import WorkspaceManager
from src.core.managers import ConfigManager
from pyfiglet import FigletString
from cmd2 import Cmd, Color, stylize
from rich.console import Console
from rich.table import Table
from rich.style import Style
from pyfiglet import Figlet
import os
import asyncio

from src.core.loader import load_modules
from src.utils.print_utils import error, info
from src.utils.logger import set_debug_mode


class Shell(Cmd):
    def __init__(self, debug_mode: bool = False) -> None:
        super().__init__()
        self.debug_mode = debug_mode
        self.version = "1.0.0"
        self.prompt = f"{stylize('keen', Style(color=Color.BLUE))} > "
        self.modules = load_modules()
        self.current_module = None

        # Creates a ConfigManager to handle API keys and user preferences.
        self.config = ConfigManager("~/.keen/config.db")
        # Starts empty, set by user via the 'workspace' command.
        self.workspace = None

        banner: FigletString = Figlet(font="slant").renderText("Keen")
        banner_styled: str = stylize(
            banner,
            Style(
                color=Color.BLUE,
            ),
        )

        version_styled: str = stylize(
            f"Version: {self.version}",
            Style(
                color=Color.YELLOW,
            ),
        )

        welcome_styled: str = stylize(
            "Welcome to Keen, an information gathering tool.",
            Style(
                color=Color.GREEN,
            ),
        )

        self.intro = f"\n{banner_styled}\n{version_styled}\n{welcome_styled}\n"

    def complete_use(self, text, line, begidx, endidx):
        """Tab-completion for the 'use' command."""
        # Suggest names that don't look like internal python paths
        return [
            name
            for name in self.modules
            if name.startswith(text.lower()) and "src.modules" not in name
        ]

    def do_use(self, arg: str):
        """Select a module to use. You can use the full path or just the module name (e.g. 'use whois')."""
        module_name: str = arg.strip().lower()

        if not module_name:
            error("Usage: use <module_name>")
            return

        if module_name in self.modules:
            self.current_module = self.modules[module_name]()
            category = self.current_module.metadata.get("category", "")
            name = self.current_module.metadata.get("name", "").lower()

            if category and category != ".":
                display_path = f"{category}/{name}"
            else:
                display_path = name

            keen_part = stylize("keen", Style(color=Color.BLUE))
            module_part = stylize(f"({display_path})", Style(color=Color.RED))

            if self.workspace:
                workspace_part = stylize(
                    f"[{self.workspace.name}]", Style(color=Color.GREEN)
                )
                self.prompt = f"{keen_part}{workspace_part}{module_part} > "
            else:
                self.prompt = f"{keen_part}{module_part} > "
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

        if self.workspace:
            self.prompt = f"{stylize('keen', Style(color=Color.BLUE))}{stylize(f'({self.workspace.name})', Style(color=Color.GREEN))} > "
        else:
            self.prompt = f"{stylize('keen', Style(color=Color.BLUE))} > "

    def do_show(self, arg: str) -> None:
        """Show available <modules | options | info | banner>."""
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
            print(self.intro)
        else:
            error("Usage: show <options | modules | info | banner>")

    def do_list(self, arg: str) -> None:
        """List available <modules | options | api_keys>."""
        if not arg:
            error("Usage: list <modules | options | api_keys>")
            return

        if arg.lower() == "modules":
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
                    # key will be the first one inserted (category/name if it exists)
                    desc = getattr(cls, "metadata", {}).get("description", "")
                    table.add_row(key, desc)

            info(f"Available modules ({count}):")
            console = Console()
            console.print(table)

        elif arg.lower() == "options":
            if self.current_module:
                self.current_module.print_options()
            else:
                error("No module selected.")
        else:
            error("Usage: list <modules | options | api_keys>")

    def do_clear(self, arg: str) -> None:
        """Clear the screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def do_workspace(self, name: str) -> None:
        """Create a new workspace."""
        if not name:
            error("Usage: workspace <name>")
            return

        db_file = f"cases/{name}.keen"
        self.workspace = WorkspaceManager(db_file)

        keen_part = stylize("keen", Style(color=Color.BLUE))
        workspace_part = stylize(f"[{name}]", Style(color=Color.GREEN))
        self.prompt = f"{keen_part}{workspace_part} > "

        info(f"Switched to workspace: {stylize(name, Style(color=Color.GREEN))}.")

    def do_exit(self) -> None:
        """Exit the shell."""
        self.do_quit("Exiting the shell. Goodbye!")
