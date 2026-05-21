from src.core.managers import WorkspaceManager
from typing import Any
from typing import Callable
from typing import Literal
from rich.console import Console
from rich.table import Table

from src.utils.validator import InputValidator
from src.utils.print_utils import error


class BaseModule:
    """Base class for all modules.

    Attributes:
        metadata (dict): Dictionary containing module metadata.
        options (dict): Dictionary containing module options.
    """

    metadata = {
        "name": "Base",
        "description": "Base Module",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {},
    }

    def __init__(self) -> None:
        from loguru import logger

        self.options = {}
        self.logger = logger.bind(module=self.metadata["name"])
        self.shell = None
        self.is_web_context = False
        self.active_processes = set()

    def set_option(self, key: str, value) -> bool:
        # Search for the key in a case-insensitive way
        for opt_key in self.metadata["options"]:
            if opt_key.lower() == key.lower():
                # Strip quotes if the value is a string
                if isinstance(value, str):
                    value = value.strip("\"'")

                    # If this option has a validator (i.e. it's a target option),
                    # strip any platform prefix (e.g. "github:username" -> "username")
                    opt_meta = self.metadata["options"].get(opt_key)
                    if opt_meta and opt_meta[3]:
                        from src.utils.utils import clean_node_value

                        value = clean_node_value(value)

                self.options[opt_key] = value
                return True
        return False


    def show_metadata(self) -> None:
        """Show information about the module."""
        table = Table(
            show_header=True,
            header_style="bold blue",
            title="Module Information",
            title_style="bold cyan",
            show_lines=True,
            expand=True,
        )

        table.add_column("Property", justify="left", style="cyan", no_wrap=True)
        table.add_column("Value", justify="left", style="white")

        for key, value in self.metadata.items():
            if key == "options":
                continue
            table.add_row(key.capitalize(), str(value))

        console: Console = Console()
        console.print(table)

    def print_options(self) -> None:
        """Show the module options."""
        table = Table(
            show_header=True,
            header_style="bold blue",
            title="Module Options",
            title_style="bold cyan",
            show_lines=True,
            expand=True,
        )

        table.add_column("Option", justify="left", style="cyan", no_wrap=True)
        table.add_column("Current Value", justify="left", style="white")
        table.add_column("Required", justify="center", style="magenta")
        table.add_column("Description", justify="left", style="white")

        for key, value in self.metadata["options"].items():
            # value = [default, required, description, validator]
            required: Literal["Yes", "No"] = "Yes" if value[1] else "No"
            current_value = self.options.get(key, value[0])
            table.add_row(key, str(current_value), required, str(value[2]))

        console: Console = Console()
        console.print(table)

    async def run(self) -> None:
        """
        This method should be implemented by each module.
        """
        raise NotImplementedError("Each module must implement its own 'run' method.")

    def check_required_options(self) -> bool:
        """Check if all required options are set."""
        for key, value in self.metadata["options"].items():
            if value[1] and not self.options.get(key, None):
                error(f"Required option '{key}' is not set.")
                return False
        return True

    def validate_options(self) -> bool:
        """Check if the module options are valid."""
        for key, value in self.metadata["options"].items():
            validator = value[3]
            option_value: str = str(self.options.get(key, None))

            if validator:
                # Support list/tuple or comma-separated string of validators
                if isinstance(validator, (list, tuple)):
                    validators_list = list(validator)
                else:
                    validators_list = [
                        v.strip() for v in str(validator).split(",") if v.strip()
                    ]

                if validators_list:
                    known_validators = [
                        v for v in validators_list if v in InputValidator.VALIDATORS
                    ]

                    if known_validators:
                        passed_at_least_one = any(
                            InputValidator.VALIDATORS[v](option_value)
                            for v in known_validators
                        )
                        if not passed_at_least_one:
                            error(
                                f"Invalid value for {key.upper()}. It should match at least one of: {', '.join(validators_list)}."
                            )
                            return False
                    else:
                        pass
        return True

    def pre_run(self) -> bool:
        """Pre-run checks."""
        if not self.check_required_options():
            return False

        if not self.validate_options():
            return False

        return True

    def load_api_keys(self, config_manager) -> None:
        """Automatically load matching API keys from the configuration manager."""
        for key in self.metadata.get("options", {}):
            if key.endswith("_APIKEY") or key.endswith("_API_KEY"):
                # If the option is not currently set or is empty/falsy, try to fetch it
                if not self.options.get(key):
                    service_names = [key, key.lower()]
                    for suffix in ["_apikey", "_api_key"]:
                        if key.lower().endswith(suffix):
                            short_name = key.lower()[: -len(suffix)]
                            service_names.append(short_name)

                    api_key = None
                    for svc in service_names:
                        api_key = config_manager.get_api_key(svc)
                        if api_key:
                            break

                    if api_key:
                        self.options[key] = api_key

    async def loading(self, title: str, task: Callable, *args, **kwargs) -> Any:
        """Show loading animation."""
        with Console().status(f"[bold green]{title}") as status:
            result: Any = await task(*args, **kwargs)
            status.update(f"[bold green]{title}")
            return result

    @property
    def workspace(self) -> WorkspaceManager | None:
        """Helper property to easily access the active workspace from shell."""
        if not self.shell:
            return None
        return self.shell.workspace

    async def post_run(self, results: dict) -> None:
        """
        Ingestion engine. Automatically save nodes and edges
        to the active workspace after a module finishes.
        """
        workspace = self.workspace
        if not workspace:
            self.logger.warning(
                "No active workspace selected. Module results were not saved."
            )
            return

        node_map = {}
        for node in results.get("nodes", []):
            node_id = workspace.get_or_add_node(
                node_type=node["type"],
                value=node["value"],
                metadata=node.get("metadata", {}),
            )
            node_map[node["value"]] = node_id

        for edge in results.get("edges", []):
            source_id = node_map.get(edge["source"])
            target_id = node_map.get(edge["target"])

            if not source_id:
                source_id = workspace.get_node_id(edge["source"])

            if not target_id:
                target_id = workspace.get_node_id(edge["target"])

            if source_id and target_id:
                workspace.add_edge(
                    source_id=source_id,
                    target_id=target_id,
                    relationship=edge.get("relationship", "RELATED"),
                    metadata=edge.get("metadata", {}),
                )

        # Check if magic chaining is enabled and not already running
        if self.shell and getattr(self.shell, "_magic_running", False) is not True:
            config = getattr(self.shell, "config", None)
            if not config:
                from src.core.managers import ConfigManager

                config = ConfigManager("~/.keen/config.db")

            if config.get_preference("magic_enabled") == "true":
                from src.core.magic import MagicEngine

                self.shell._magic_running = True
                try:
                    engine = MagicEngine(self.shell, config=config)
                    # Run on all nodes returned by this module
                    for node in results.get("nodes", []):
                        val = node.get("value")
                        t = node.get("type")
                        if val:
                            await engine.run_chain(val, initial_type=t, force=False)
                finally:
                    self.shell._magic_running = False

    def register_process(self, process) -> None:
        """Register a subprocess for cleanup on cancellation."""
        if not hasattr(self, "active_processes"):
            self.active_processes = set()
        self.active_processes.add(process)

    def unregister_process(self, process) -> None:
        """Unregister a subprocess after it completes."""
        if hasattr(self, "active_processes"):
            self.active_processes.discard(process)

    async def run_subprocess(
        self, cmd: list[str], stdout=None, stderr=None
    ) -> tuple[int, bytes, bytes]:
        """Run an external subprocess asynchronously, ensuring it is terminated/killed on cancellation."""
        import asyncio

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=stdout or asyncio.subprocess.PIPE,
            stderr=stderr or asyncio.subprocess.PIPE,
        )
        self.register_process(process)

        try:
            stdout_data, stderr_data = await process.communicate()
            return (
                process.returncode if process.returncode is not None else -1,
                stdout_data,
                stderr_data,
            )
        except asyncio.CancelledError:
            if process.returncode is None:
                try:
                    process.terminate()
                    # Wait briefly to allow clean termination
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
            raise
        finally:
            self.unregister_process(process)

    def cleanup(self) -> None:
        """Terminate all active subprocesses registered by this module."""
        if hasattr(self, "active_processes"):
            for process in list(self.active_processes):
                if process.returncode is None:
                    try:
                        process.terminate()
                    except Exception:
                        try:
                            process.kill()
                        except Exception:
                            pass
            self.active_processes.clear()
