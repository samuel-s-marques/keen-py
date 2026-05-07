from cmd2 import Cmd, Color, stylize
from rich.console import Console
from rich.table import Table
from rich.style import Style
from pyfiglet import Figlet
import os

from src.core.loader import load_modules
from src.utils.print_utils import error, info


class Shell(Cmd):
    def __init__(self) -> None:
        super().__init__()
        self.version = "1.0.0"
        self.prompt = f"{stylize('keen', Style(color=Color.BLUE))} > "
        self.modules = load_modules()
        self.current_module = None

        banner = Figlet(font="slant").renderText("Keen")
        banner_styled = stylize(
            banner,
            Style(
                color=Color.BLUE,
            ),
        )

        version_styled = stylize(
            f"Version: {self.version}",
            Style(
                color=Color.YELLOW,
            ),
        )

        welcome_styled = stylize(
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
        module_name = str(arg).strip().lower()

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
            self.prompt = f"{keen_part}{module_part} > "
        else:
            error(
                f"Module '{module_name}' not found. Type 'list modules' to see available modules."
            )

    def do_set(self, arg: str) -> None:
        """Set a module option."""
        if not self.current_module:
            error("No module selected. Use 'use <module>' first.")
            return

        try:
            key, value = arg.split(" ", 1)
            if self.current_module.set_option(key.lower(), value):
                info(f"{key.upper()} => {value}")
            else:
                error(f"Invalid option: {key.upper()}")
        except ValueError:
            error("Usage: set <option> <value>")

    def do_run(self, arg: str):
        """Execute the current module."""
        if self.current_module:
            info("Executing...")
            self.current_module.run()
        else:
            error("No module selected.")

    def do_back(self, arg: str) -> None:
        """Go back to the main menu."""
        self.current_module = None
        self.prompt = f"{stylize('keen', Style(color=Color.BLUE))} > "

    def do_show(self, arg: str) -> None:
        """Show available <modules | options | info>. Another alias to list."""
        if not arg:
            error("Usage: show <options | modules | info>")
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
        else:
            error("Usage: show <options | modules | info>")

    def do_list(self, arg: str) -> None:
        """List available <modules | options>. Another alias to show."""
        if not arg:
            error("Usage: list <modules | options>")
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
            error("Usage: list <modules | options>")

    def do_clear(self, arg: str) -> None:
        """Clear the screen."""
        os.system("cls" if os.name == "nt" else "clear")
