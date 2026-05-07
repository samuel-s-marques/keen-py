from cmd2 import Cmd, Color, stylize
from rich.style import Style
from pyfiglet import Figlet

from src.core.loader import load_modules
from src.utils.print_utils import error, info, success, warn


class Shell(Cmd):
    def __init__(self) -> None:
        super().__init__()
        self.prompt = "keen > "
        self.modules = load_modules()
        self.current_module = None
        banner = Figlet(font="slant").renderText("Keen")
        self.intro = stylize(
            f"\n{banner}\nWelcome to Keen, an information gathering tool.",
            Style(color=Color.CYAN),
        )

    def complete_use(self, text, line, begidx, endidx):
        """Tab-completion for the 'use' command."""
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
            display_name = self.current_module.info.get("name", module_name)
            self.prompt = f"keen({display_name}) > "
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
        self.prompt = "keen > "

    def do_show(self, arg: str) -> None:
        """Show available <modules | options>. Another alias to list."""
        if not arg:
            error("Usage: show <options | modules>")
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
                self.current_module.show_info()
            else:
                error("No module selected.")
        else:
            error("Usage: show options | modules | info")

    def do_list(self, arg: str) -> None:
        """List available <modules | options>. Another alias to show."""
        if not arg:
            error("Usage: list <modules | options>")
            return

        if arg.lower() == "modules":
            # Deduplicate: multiple keys can point to the same class
            seen = set()
            unique_modules = []
            for key, cls in self.modules.items():
                if cls not in seen:
                    seen.add(cls)
                    unique_modules.append((key, cls))

            info(f"Available modules ({len(unique_modules)}):")

            for key, cls in unique_modules:
                mod_info = getattr(cls, "info", {})
                name = mod_info.get("name", key)
                desc = mod_info.get("description", "")
                info(f"  {name:<20} {desc}")
        elif arg.lower() == "options":
            if self.current_module:
                self.current_module.print_options()
            else:
                error("No module selected.")
        else:
            error("Usage: list <modules | options>")
