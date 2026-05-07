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

    def do_use(self, module_name: str):
        """Select a module to use."""
        if module_name in self.modules:
            self.current_module = self.modules[module_name]()
            self.prompt = f"keen({module_name}) > "
        else:
            error(f"Module {module_name} not found.")

    def do_set(self, arg: str) -> None:
        """Set a module option."""
        if not self.current_module:
            error("No module selected. Use 'use <module>' first.")
            return

        try:
            key, value = arg.split(" ", 1)
            if self.current_module.set_option(key.upper(), value):
                info(f"{key} => {value}")
            else:
                error(f"Invalid option: {key}")
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
        else:
            error("Usage: show options | modules")

    def do_list(self, arg: str) -> None:
        """List available <modules | options>. Another alias to show."""
        if not arg:
            error("Usage: list <modules | options>")
            return

        if arg.lower() == "modules":
            info(f"Available modules ({len(self.modules)}):\n")

            for module in self.modules:
                info(module)
        elif arg.lower() == "options":
            if self.current_module:
                self.current_module.print_options()
            else:
                error("No module selected.")
        else:
            error("Usage: list <modules | options>")
