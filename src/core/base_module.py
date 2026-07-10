from contextlib import contextmanager
from typing import Any, Callable, Literal

from rich.console import Console
from rich.table import Table

from src.core.managers import WorkspaceManager
from src.core.options import as_option
from src.utils.print_utils import error
from src.utils.validator import InputValidator

# Strong references to fire-and-forget background tasks
_BACKGROUND_TASKS: set = set()


class BaseModule:
    """Base class for all modules.

    Attributes:
        metadata (dict): Dictionary containing module metadata.
        options (dict): Dictionary containing module options.
    """

    metadata: dict[str, Any] = {
        "name": "Base",
        "description": "Base Module",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {},
    }

    def __init__(self) -> None:
        from loguru import logger

        if not isinstance(self.metadata, dict):
            self.metadata = {}

        metadata_copy = dict(self.metadata)

        if "name" not in metadata_copy or not isinstance(metadata_copy["name"], str):
            metadata_copy["name"] = "Base"

        if "options" not in metadata_copy or not isinstance(
            metadata_copy["options"], dict
        ):
            metadata_copy["options"] = {}

        self.metadata = metadata_copy
        options_data = self.metadata["options"]
        if not isinstance(options_data, dict):
            options_data = {}

        self.options = {k: as_option(v).default for k, v in options_data.items()}
        self.logger = logger.bind(module=self.metadata["name"])
        self.shell = None
        self.is_web_context = False
        self.active_processes = set()
        self._safety_confirmed = False
        self._event_sink: Callable[[dict], None] | None = None

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
                    if opt_meta and as_option(opt_meta).validator:
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
            opt = as_option(value)
            required: Literal["Yes", "No"] = "Yes" if opt.required else "No"
            current_value = self.options.get(key, opt.default)
            table.add_row(key, str(current_value), required, opt.description)

        console: Console = Console()
        console.print(table)

    target_option: str = "TARGET"
    lower_target: bool = True

    @property
    def execution_safety(self) -> str:
        """PTES execution-safety classification: ``passive`` (default), ``active``, or ``intrusive``.

        Declared via ``metadata["execution_safety"]``. This only exposes the
        classification a module declares about itself -- enforcement (a
        confirmation gate at the CLI/web/agent call sites before an
        active/intrusive module runs) is separate follow-on work, not
        performed here.
        """
        value = self.metadata.get("execution_safety", "passive")
        if value not in ("passive", "active", "intrusive"):
            return "passive"
        return value

    def get_target(self) -> str:
        """Read and normalize the module's target option (see target_option/lower_target)."""
        raw = str(self.options.get(self.target_option, ""))
        return raw.lower() if self.lower_target else raw.strip()

    def loading_message(self, target: str) -> str:
        """Spinner text shown while execute() runs. Override for a module-specific message."""
        return f"Running {self.metadata.get('name', 'module')} on {target}..."

    def validate_target(self, target: str) -> bool:
        """Extra validation hook run after pre_run(), before execute(). Report via error() and return False to abort."""
        return True

    async def run(self) -> None:
        """Default opener: pre_run() -> get_target() -> validate_target() -> loading(execute).

        Override this wholesale in modules whose flow doesn't fit the shape
        above; otherwise just implement execute(target).
        """
        if not self.pre_run():
            return

        target = self.get_target()

        if not self.validate_target(target):
            return

        await self.loading(self.loading_message(target), self.execute, target)

    async def execute(self, target: str, *args, **kwargs) -> Any:
        """
        This method should be implemented by each module using the default run() opener.

        Signature is deliberately loose (``*args, **kwargs`` / ``Any`` return)
        so modules that override ``run()`` directly can keep an ``execute()``
        with extra parameters or a non-``None`` return without a Liskov
        violation against this stub.
        """
        raise NotImplementedError(
            "Each module must implement its own 'execute' method."
        )

    def check_required_options(self) -> bool:
        """Check if all required options are set."""
        for key, value in self.metadata["options"].items():
            if as_option(value).required and not self.options.get(key, None):
                error(f"Required option '{key}' is not set.")
                return False
        return True

    def validate_options(self) -> bool:
        """Check if the module options are valid."""
        for key, value in self.metadata["options"].items():
            validator = as_option(value).validator
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

        if not self._check_execution_safety():
            return False

        return True

    def confirm_execution(self) -> None:
        """Explicitly acknowledge running a non-``passive`` module.

        A caller that isn't an interactive human at a terminal (a web
        request, an automated chain, an agent) must call this -- after
        getting its own confirmation from whatever source is appropriate for
        that context -- before ``pre_run()`` will let an ``active``/``intrusive``
        module proceed. There is no default "just run it" path for anything
        but a ``passive`` module.
        """
        self._safety_confirmed = True

    def _check_execution_safety(self) -> bool:
        """Gate ``active``/``intrusive`` modules behind explicit confirmation.

        This is the one chokepoint every call site (CLI ``do_run``, the web
        run endpoints, magic chaining, the playbook interpreter, a future
        agent loop) goes through via ``pre_run()``, so none of them can
        silently bypass the PTES passive/active/intrusive guardrail
        just by calling a module a different way.
        """
        if self.execution_safety == "passive" or self._safety_confirmed:
            return True

        # An interactive CLI session (not the web server, not a background
        # magic/agent run) can prompt the operator directly.
        interactive = not getattr(self, "is_web_context", False) and not getattr(
            self.shell, "_magic_running", False
        )
        if interactive:
            target = self.get_target() if hasattr(self, "get_target") else ""
            try:
                answer = input(
                    f"[!] '{self.metadata.get('name', 'module')}' is classified as "
                    f"{self.execution_safety}. Run it against '{target}'? [y/N]: "
                )
            except (KeyboardInterrupt, EOFError):
                print()
                return False
            if answer.strip().lower() in ("y", "yes"):
                self._safety_confirmed = True
                return True
            error(
                f"Execution of '{self.metadata.get('name', 'module')}' was not confirmed."
            )
            return False

        error(
            f"'{self.metadata.get('name', 'module')}' is classified as "
            f"{self.execution_safety} and requires explicit confirmation "
            "(confirm_execution()) before it can run in a non-interactive context."
        )
        return False

    # Option-name suffixes that mark a stored-credential option eligible for
    # automatic loading from the config manager.
    API_KEY_OPTION_SUFFIXES = ("_APIKEY", "_API_KEY", "_TOKEN")

    def load_api_keys(self, config_manager) -> None:
        """Automatically load matching API keys from the configuration manager."""
        for key in self.metadata.get("options", {}):
            if key.upper().endswith(self.API_KEY_OPTION_SUFFIXES):
                # If the option is not currently set or is empty/falsy, try to fetch it
                if not self.options.get(key):
                    service_names = [key, key.lower()]
                    for suffix in ["_apikey", "_api_key", "_token"]:
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
        if getattr(self, "is_web_context", False):
            # No spinner (and no shared-stdout writes) in the web context.
            return await task(*args, **kwargs)
        with Console().status(f"[bold green]{title}") as status:
            result: Any = await task(*args, **kwargs)
            status.update(f"[bold green]{title}")
            return result

    async def gather_bounded(
        self, coros, limit: int = 20, return_exceptions: bool = True
    ) -> list:
        """Await many coroutines with at most ``limit`` running concurrently.

        A single bounded-concurrency primitive to replace ad-hoc thread pools
        and manual chunking across modules. Results preserve input order; by
        default exceptions are returned in place (recon code usually wants to
        keep partial results rather than abort the whole batch).
        """
        import asyncio

        semaphore = asyncio.Semaphore(max(1, limit))

        async def _run(coro):
            async with semaphore:
                return await coro

        return await asyncio.gather(
            *(_run(c) for c in coros), return_exceptions=return_exceptions
        )

    # ------------------------------------------------------------------ #
    # Standardized result rendering (see src/utils/render.py).
    # Modules build tables/panels with these helpers and print them via
    # self.render(), which centralizes the house style and the web-context
    # no-op that was previously duplicated in every display method.
    # ------------------------------------------------------------------ #
    @property
    def console(self) -> Console:
        if getattr(self, "_console", None) is None:
            self._console = Console()
        return self._console

    def render(self, renderable) -> None:
        """Print a Rich renderable to the terminal, unless in web context."""
        if getattr(self, "is_web_context", False):
            return
        self.console.print(renderable)

    def results_table(self, title=None, columns=()):
        """Build a house-style results table (see render.results_table)."""
        from src.utils.render import results_table

        return results_table(title, columns)

    def kv_table(self, title=None):
        """Build a house-style key/value detail table."""
        from src.utils.render import kv_table

        return kv_table(title)

    def result_panel(self, content, title=None, kind: str = "info"):
        """Build a house-style status/summary panel."""
        from src.utils.render import result_panel

        return result_panel(content, title=title, kind=kind)

    def _emit(self, event: dict) -> None:
        """Push a structured event (``progress``/``node_added``/``edge_added``)
        to ``self._event_sink`` if a caller (e.g. the web server's WebSocket
        streaming) has set one. Best-effort: a broken sink must never break
        ingestion.
        """
        sink = getattr(self, "_event_sink", None)
        if not sink:
            return
        try:
            sink(event)
        except Exception:
            pass

    @property
    def workspace(self) -> WorkspaceManager | None:
        """Helper property to easily access the active workspace from shell."""
        if not self.shell:
            return None
        return self.shell.workspace

    @contextmanager
    def _config_ctx(self):
        """Yield a ConfigManager, reusing the shell's if present.

        Centralizes the "use self.shell.config if available, else open a
        throwaway ConfigManager and remember to close it" pattern that was
        duplicated across post_run and get_http_client.
        """
        from src.core.managers import ConfigManager

        config = None
        should_close = False
        if self.shell and getattr(self.shell, "config", None):
            config = self.shell.config
        else:
            config = ConfigManager("~/.keen/config.db")
            should_close = True
        try:
            yield config
        finally:
            if should_close and config:
                config.close()

    async def post_run(self, results: dict, raw: Any = None) -> None:
        """Post-processing pipeline run after a module finishes.

        Four focused stages, each isolated in its own method for clarity and
        testability:
          0. :meth:`_record_provenance` — append a hash-chained ledger entry.
          1. :meth:`_ingest_results` — persist nodes/edges to the workspace,
             quarantining any node outside the case's declared scope.
          2. :meth:`_run_magic_chaining` — auto-chain follow-up modules,
             skipping anything just quarantined by stage 1.
          3. :meth:`_trigger_thinking_partner` — schedule AI pivot suggestions.
        Stages 0, 2, and 3 are best-effort and never abort ingestion.

        ``raw`` is an optional pre-parse payload (e.g. the raw API response)
        to archive in the provenance ledger alongside the parsed results, per
        the "Case Replayability" guardrail. Most modules don't pass this yet
        --- wiring per-module raw capture is separate, mechanical follow-up
        work, not a requirement of this pipeline.
        """
        workspace = self.workspace
        if not workspace:
            self.logger.warning(
                "No active workspace selected. Module results were not saved."
            )
            return

        self._emit({"type": "progress", "progress": 0.1, "stage": "provenance"})
        self._record_provenance(workspace, results, raw)

        self._emit({"type": "progress", "progress": 0.4, "stage": "ingest"})
        quarantined = self._ingest_results(workspace, results)

        self._emit({"type": "progress", "progress": 0.7, "stage": "magic"})
        await self._run_magic_chaining(results, quarantined)

        self._emit({"type": "progress", "progress": 0.9, "stage": "thinking_partner"})
        await self._trigger_thinking_partner(workspace)

        self._emit({"type": "progress", "progress": 1.0, "stage": "done"})

    def _record_provenance(self, workspace, results: dict, raw: Any = None) -> None:
        """Stage 0: append a hash-chained provenance ledger entry for this run."""
        try:
            target = self.options.get(self.target_option, "")
            payload = (
                raw
                if raw is not None
                else {
                    "nodes_added": len(results.get("nodes", [])),
                    "edges_added": len(results.get("edges", [])),
                }
            )
            workspace.append_ledger_entry(
                actor=self.metadata.get("name", "module"),
                action="run",
                target_value=str(target),
                raw_payload=payload,
            )
        except Exception as e:
            self.logger.error(f"Failed to record provenance ledger entry: {e}")

    def _ingest_results(self, workspace, results: dict) -> set:
        """Stage 1: deduplicate and persist nodes and edges into the workspace.

        The whole graph is written inside a single ``workspace.batch()`` so all
        inserts share one transaction/commit instead of committing per row.
        Nodes falling outside the case's declared scope (see
        ``workspace.is_in_scope``) are still ingested -- so the investigator
        can see what was found -- but flagged as quarantined rather than
        silently treated as in-scope. Returns the set of quarantined values so
        stage 2 can exclude them from auto-chaining.
        """
        quarantined: set = set()
        with workspace.batch():
            node_map = {}
            for node in results.get("nodes", []):
                node_id = workspace.get_or_add_node(
                    node_type=node["type"],
                    value=node["value"],
                    metadata=node.get("metadata", {}),
                )
                node_map[node["value"]] = node_id
                self._emit(
                    {
                        "type": "node_added",
                        "node": {
                            "id": node_id,
                            "type": node["type"],
                            "value": node["value"],
                        },
                    }
                )

                if node_id and not workspace.is_in_scope(
                    node["value"], node.get("type")
                ):
                    workspace.quarantine_node(
                        node_id,
                        reason="Discovered value falls outside the case's declared scope.",
                    )
                    quarantined.add(node["value"])

            for edge in results.get("edges", []):
                source_id = node_map.get(edge["source"]) or workspace.get_node_id(
                    edge["source"]
                )
                target_id = node_map.get(edge["target"]) or workspace.get_node_id(
                    edge["target"]
                )

                if source_id and target_id:
                    workspace.add_edge(
                        source_id=source_id,
                        target_id=target_id,
                        relationship=edge.get("relationship", "RELATED"),
                        metadata=edge.get("metadata", {}),
                        confidence=edge.get("confidence"),
                    )
                    self._emit(
                        {
                            "type": "edge_added",
                            "edge": {
                                "source_id": source_id,
                                "target_id": target_id,
                                "relationship": edge.get("relationship", "RELATED"),
                            },
                        }
                    )
        return quarantined

    async def _run_magic_chaining(
        self, results: dict, quarantined: set | None = None
    ) -> None:
        """Stage 2: auto-chain modules on discovered nodes, if enabled.

        Guarded by ``shell._magic_running`` so a chain triggered from within a
        chain doesn't recurse into a second engine. Nodes stage 1 just
        quarantined are excluded -- an out-of-scope discovery must stop the
        crawl there, not silently continue expanding it.
        """
        if not self.shell or getattr(self.shell, "_magic_running", False) is True:
            return

        quarantined = quarantined or set()

        with self._config_ctx() as config:
            if config.get_preference("magic_enabled") != "true":
                return
            from src.core.magic import MagicEngine

            self.shell._magic_running = True
            try:
                engine = MagicEngine(self.shell, config=config)
                for node in results.get("nodes", []):
                    val = node.get("value")
                    if val and val not in quarantined:
                        await engine.run_chain(
                            val, initial_type=node.get("type"), force=False
                        )
            finally:
                self.shell._magic_running = False

    async def _trigger_thinking_partner(self, workspace) -> None:
        """Stage 3: run/schedule the AI Thinking Partner suggestion engine, if enabled."""
        try:
            with self._config_ctx() as config:
                if config.get_preference("llm_thinking_partner_enabled") != "true":
                    return
                import asyncio

                from src.core.thinking_partner import ThinkingPartnerEngine

                ws_name = workspace.name

                async def run_thinking_partner():
                    try:
                        engine = ThinkingPartnerEngine()
                        await engine.generate_suggestions(ws_name)
                    except Exception as e_bg:
                        self.logger.error(
                            f"Error in background AI Thinking Partner task: {e_bg}"
                        )

                if getattr(self, "is_web_context", False):
                    # Long-lived server loop: run in the background without
                    # blocking, keeping a strong reference so the task isn't
                    # garbage-collected before it finishes.
                    task = asyncio.create_task(run_thinking_partner())
                    _BACKGROUND_TASKS.add(task)
                    task.add_done_callback(_BACKGROUND_TASKS.discard)
                else:
                    # CLI: asyncio.run() tears the loop down as soon as run()
                    # returns, which would destroy a fire-and-forget task before
                    # it executed — so await it to completion here instead.
                    await run_thinking_partner()
        except Exception as e:
            self.logger.error(f"Failed to trigger AI Thinking Partner: {e}")

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

    def get_http_client(self, **kwargs):
        """Returns an httpx.AsyncClient configured with active proxy settings if enabled.

        The client is given a sensible default timeout and a transport that
        transparently retries transient *connection* failures (``http_retries``
        preference, default 2). For status-code-aware retries (429/5xx with
        ``Retry-After``), use ``await self.request(client, ...)``.
        """
        import httpx

        proxy_url = kwargs.pop("proxy", None)
        retries = 2
        with self._config_ctx() as config:
            proxy = config.get_next_proxy()
            if proxy and not proxy_url:
                proxy_url = proxy["url"]
            try:
                retries = int(config.get_preference("http_retries") or 2)
            except (ValueError, TypeError):
                retries = 2

        # Sensible default timeout so a hung host can't stall a module forever.
        kwargs.setdefault("timeout", 15.0)
        # Build a transport that retries transient connection errors, carrying
        # the proxy if one is active. Respect a caller-supplied transport.
        if "transport" not in kwargs:
            kwargs["transport"] = httpx.AsyncHTTPTransport(
                retries=max(0, retries), proxy=proxy_url
            )

        return httpx.AsyncClient(**kwargs)

    def cache_get(self, key: str):
        """Read a value from the shared cross-run TTL cache (or None)."""
        with self._config_ctx() as config:
            return config.cache_get(key)

    def cache_set(self, key: str, value: str, ttl: float | None = 3600) -> None:
        """Write a value to the shared cross-run TTL cache."""
        with self._config_ctx() as config:
            config.cache_set(key, value, ttl)

    async def rate_limit(self, service: str) -> None:
        """Pace requests to ``service`` (see ``src/utils/rate_limiter.py``).

        Call once before a module's first request per run to a rate-limited
        third-party provider (e.g. ``await self.rate_limit("shodan")``).
        """
        from src.utils.rate_limiter import acquire

        with self._config_ctx() as config:
            await acquire(service, config)

    async def request(
        self,
        client,
        method: str,
        url: str,
        *,
        retries: int = 3,
        backoff: float = 0.5,
        retry_statuses: tuple = (429, 500, 502, 503, 504),
        **kwargs,
    ):
        """Perform an HTTP request with exponential backoff on transient statuses.

        Retries on ``retry_statuses`` (default 429 + 5xx), honoring the server's
        ``Retry-After`` header when present, otherwise using exponential backoff
        (``backoff * 2**attempt``). Returns the final ``httpx.Response``.
        """
        import asyncio

        response = None
        for attempt in range(retries + 1):
            response = await client.request(method, url, **kwargs)
            if response.status_code not in retry_statuses or attempt >= retries:
                return response

            retry_after = response.headers.get("Retry-After", "")
            if retry_after.isdigit():
                delay = float(retry_after)
            else:
                delay = backoff * (2**attempt)
            self.logger.debug(
                f"{method} {url} -> {response.status_code}; retrying in {delay:.1f}s "
                f"(attempt {attempt + 1}/{retries})"
            )
            await asyncio.sleep(delay)
        return response
