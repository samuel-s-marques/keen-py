"""YAML-defined playbook interpreter.

A playbook is a small DAG of steps, each invoking one Keen module:

    name: Infrastructure Pivot & Threat Scan
    trigger_type: domain-name
    steps:
      - id: dns_sweep
        module: discovery/dns_enum
        inputs: { TARGET: "{{ trigger.value }}" }
      - id: shodan_ports
        module: intel/shodan_host
        depends_on: dns_sweep
        inputs: { TARGET: "{{ dns_sweep.node_value }}" }
        condition: "node.type == 'ipv4-addr' and not node.is_private"

Steps with no ``depends_on`` run immediately, seeded from ``trigger.value``.
A step with ``depends_on`` runs once per node any of its dependencies
discovered -- a fan-in union across parents, deduped by node value, not a
cartesian product -- (optionally filtered by ``condition``, evaluated with
that node bound to ``node``), re-rendering its ``inputs`` templates against
that specific node each time. Steps whose dependencies are already satisfied
run concurrently, mirroring MagicEngine's per-depth concurrency.

Execution itself goes through :func:`src.core.magic.run_module_on_target` --
the same shared, safety-gated module-execution path MagicEngine uses -- so a
playbook cannot run an active/intrusive module any more freely than a human
`run` or an auto-chained magic pivot can.

Condition expressions are evaluated by a small whitelisted AST interpreter
(:func:`safe_eval_condition`), never Python's `eval()` -- playbooks are
user-authored YAML (and, per the roadmap's Phase 5 "community playbook
marketplace", may eventually come from strangers), so arbitrary code
execution from a condition string is not an acceptable risk.
"""

import ast
import asyncio
import re
from typing import Any, Callable, Optional

from src.core.loader import load_modules
from src.core.magic import run_module_on_target
from src.core.options import as_option
from src.utils.print_utils import warn


class UnsafeExpressionError(ValueError):
    """Raised when a playbook ``condition`` uses unsupported/unsafe syntax."""


_ALLOWED_COMPARE_OPS = (
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def _eval_ast(node: ast.AST, context: dict) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body, context)
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise UnsafeExpressionError("Unsupported boolean operator")
        values = [_eval_ast(v, context) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, ast.Not):
            raise UnsafeExpressionError("Unsupported unary operator")
        return not _eval_ast(node.operand, context)
    if isinstance(node, ast.Compare):
        left = _eval_ast(node.left, context)
        result = True
        for op, comparator in zip(node.ops, node.comparators):
            if not isinstance(op, _ALLOWED_COMPARE_OPS):
                raise UnsafeExpressionError("Unsupported comparison operator")
            right = _eval_ast(comparator, context)
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.In):
                ok = left in right
            elif isinstance(op, ast.NotIn):
                ok = left not in right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            else:  # ast.GtE
                ok = left >= right
            result = result and ok
            left = right
        return result
    if isinstance(node, ast.Attribute):
        base = _eval_ast(node.value, context)
        if isinstance(base, dict):
            return base.get(node.attr)
        return getattr(base, node.attr, None)
    if isinstance(node, ast.Name):
        if node.id not in context:
            raise UnsafeExpressionError(f"Unknown identifier '{node.id}'")
        return context[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_eval_ast(e, context) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_ast(e, context) for e in node.elts)
    raise UnsafeExpressionError(f"Unsupported expression: {type(node).__name__}")


def safe_eval_condition(expression: str, context: dict) -> bool:
    """Evaluate a playbook ``condition`` string against ``context``.

    Supports boolean operators (``and``/``or``/``not``), comparisons (``==``,
    ``!=``, ``in``, ``not in``, ``<``, ``<=``, ``>``, ``>=``), attribute/dict-key
    access, name lookups restricted to keys already in ``context``, and
    literals (strings/numbers/booleans/lists/tuples). Anything else --
    function calls, imports, comprehensions, arbitrary attribute chains on
    non-context objects -- raises :class:`UnsafeExpressionError` rather than
    silently doing something unexpected.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise UnsafeExpressionError(f"Invalid condition syntax: {e}") from e
    return bool(_eval_ast(tree, context))


_TEMPLATE_RE = re.compile(r"\{\{\s*([\w]+(?:\.[\w]+)*)\s*\}\}")


def render_template(template: str, context: dict) -> str:
    """Render ``{{ dotted.path }}`` placeholders in ``template`` from ``context``.

    Deliberately not Jinja2 -- a small, dependency-free, dotted-path-only
    substitution with no arbitrary expressions and no code execution, since
    template strings are as user-authored as condition expressions.
    """

    def _replace(match: "re.Match[str]") -> str:
        value: Any = context
        for part in match.group(1).split("."):
            value = (
                value.get(part)
                if isinstance(value, dict)
                else getattr(value, part, None)
            )
            if value is None:
                return ""
        return str(value)

    return _TEMPLATE_RE.sub(_replace, template)


def load_playbook(path: str) -> dict:
    """Parse a playbook YAML file. Raises ``ValueError`` if it lacks a ``steps`` list."""
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        playbook = yaml.safe_load(f)
    if not isinstance(playbook, dict) or not playbook.get("steps"):
        raise ValueError(f"Invalid playbook '{path}': missing a non-empty 'steps' list")
    return playbook


def _depends_on_list(step: dict) -> list:
    dep = step.get("depends_on")
    if not dep:
        return []
    return [dep] if isinstance(dep, str) else list(dep)


def _detect_cycle(steps_by_id: dict) -> Optional[list]:
    """Return one cyclic path (list of step ids) if the DAG has a cycle, else None."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {step_id: WHITE for step_id in steps_by_id}
    path: list = []

    def visit(step_id: str) -> Optional[list]:
        color[step_id] = GRAY
        path.append(step_id)
        for dep in _depends_on_list(steps_by_id[step_id]):
            if dep not in steps_by_id:
                continue
            if color[dep] == GRAY:
                return path[path.index(dep):] + [dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        path.pop()
        color[step_id] = BLACK
        return None

    for step_id in steps_by_id:
        if color[step_id] == WHITE:
            found = visit(step_id)
            if found:
                return found
    return None


def validate_playbook(playbook: Any) -> dict:
    """Structurally validate a playbook without executing it.

    Returns ``{"errors": [...], "warnings": [...]}``. Errors mean the
    playbook can't run at all (bad shape, unknown ``depends_on``, a
    dependency cycle, duplicate step ids); warnings flag things that won't
    crash a run but likely aren't what the author intended (an unresolvable
    module reference, a ``condition`` with invalid syntax). Used by the web
    API's save/validate endpoints so authoring mistakes surface immediately
    instead of only at run time.
    """
    errors: list = []
    warnings: list = []

    if not isinstance(playbook, dict):
        return {"errors": ["Playbook must be a YAML mapping"], "warnings": []}

    steps = playbook.get("steps")
    if not isinstance(steps, list) or not steps:
        return {"errors": ["Playbook must have a non-empty 'steps' list"], "warnings": []}

    steps_by_id: dict = {}
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or not step.get("id") or not step.get("module"):
            errors.append(f"Step #{i + 1} must be a mapping with 'id' and 'module'")
            continue
        if step["id"] in steps_by_id:
            errors.append(f"Duplicate step id '{step['id']}'")
            continue
        steps_by_id[step["id"]] = step

    if errors:
        return {"errors": errors, "warnings": warnings}

    for step_id, step in steps_by_id.items():
        for dep in _depends_on_list(step):
            if dep not in steps_by_id:
                errors.append(f"Step '{step_id}' depends_on unknown step '{dep}'")

    if not errors:
        cycle = _detect_cycle(steps_by_id)
        if cycle:
            errors.append(f"Dependency cycle: {' -> '.join(cycle)}")

    if not errors:
        modules = load_modules()
        for step_id, step in steps_by_id.items():
            module_key = step["module"]
            if module_key not in modules and module_key.split("/")[-1] not in modules:
                warnings.append(f"Step '{step_id}' references unknown module '{module_key}'")
            condition = step.get("condition")
            if condition:
                try:
                    ast.parse(condition, mode="eval")
                except SyntaxError as e:
                    warnings.append(f"Step '{step_id}' has an invalid condition: {e}")

            timeout = step.get("timeout_seconds")
            if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
                warnings.append(
                    f"Step '{step_id}' has an invalid 'timeout_seconds' (must be a positive number)"
                )

            retry_cfg = step.get("retry")
            if retry_cfg is not None:
                if not isinstance(retry_cfg, dict):
                    warnings.append(f"Step '{step_id}' has an invalid 'retry' block (must be a mapping)")
                else:
                    max_attempts = retry_cfg.get("max_attempts", 1)
                    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
                        warnings.append(
                            f"Step '{step_id}' has an invalid retry.max_attempts (must be a positive integer)"
                        )
                    backoff = retry_cfg.get("backoff_seconds", 0)
                    if not isinstance(backoff, (int, float)) or isinstance(backoff, bool) or backoff < 0:
                        warnings.append(
                            f"Step '{step_id}' has an invalid retry.backoff_seconds (must be >= 0)"
                        )

    return {"errors": errors, "warnings": warnings}


class PlaybookEngine:
    """Executes a parsed playbook's step DAG against a trigger value."""

    def __init__(self, shell, config):
        self.shell = shell
        self.config = config
        self.modules = load_modules()
        self._event_sink: Optional[Callable[[dict], None]] = None

    def _emit(self, event: dict) -> None:
        """Push a structured event (``playbook_started``/``step_started``/
        ``step_completed``) to ``self._event_sink`` if a caller (the web
        server's WebSocket streaming, mirroring ``BaseModule._emit``) has set
        one. Best-effort: a broken sink must never break a playbook run.
        """
        sink = self._event_sink
        if not sink:
            return
        try:
            sink(event)
        except Exception:
            pass

    @staticmethod
    def _depends_on(step: dict) -> list:
        return _depends_on_list(step)

    def _validate_dag(self, steps_by_id: dict) -> None:
        for step_id, step in steps_by_id.items():
            for dep in self._depends_on(step):
                if dep not in steps_by_id:
                    raise ValueError(
                        f"Step '{step_id}' depends_on unknown step '{dep}'"
                    )

    def _resolve_module(self, module_key: str):
        return self.modules.get(module_key) or self.modules.get(
            module_key.split("/")[-1]
        )

    @staticmethod
    def _target_option(mod_class) -> str:
        for opt_key, opt_val in (
            getattr(mod_class, "metadata", {}).get("options", {}).items()
        ):
            if as_option(opt_val).validator:
                return opt_key
        return "TARGET"

    def _render_inputs(self, step: dict, context: dict) -> dict:
        rendered = {}
        for key, template in (step.get("inputs") or {}).items():
            rendered[key] = (
                render_template(template, context)
                if isinstance(template, str)
                else template
            )
        return rendered

    async def _run_step_once(self, step: dict, mod_class, context: dict) -> list:
        inputs = self._render_inputs(step, context)
        target_option = self._target_option(mod_class)
        target_value = str(inputs.get(target_option, ""))
        auto_confirm_active = (
            self.config.get_preference("magic_allow_active_modules") == "true"
        )

        timeout = step.get("timeout_seconds")
        retry_cfg = step.get("retry") or {}
        max_attempts = max(1, int(retry_cfg.get("max_attempts", 1)))
        backoff = float(retry_cfg.get("backoff_seconds", 0))

        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_attempts + 1):
            try:
                coro = run_module_on_target(
                    mod_class,
                    target_value,
                    self.shell,
                    self.config,
                    log_prefix=f"[playbook] step '{step['id']}'",
                    auto_confirm_active=auto_confirm_active,
                    extra_options=inputs,
                )
                if timeout:
                    return await asyncio.wait_for(coro, timeout=float(timeout))
                return await coro
            except asyncio.TimeoutError as e:
                last_exc = e
                warn(
                    f"[playbook] step '{step['id']}' timed out after {timeout}s "
                    f"(attempt {attempt}/{max_attempts})"
                )
            except Exception as e:
                last_exc = e
                warn(
                    f"[playbook] step '{step['id']}' failed (attempt {attempt}/{max_attempts}): {e}"
                )
            if attempt < max_attempts and backoff > 0:
                await asyncio.sleep(backoff)

        assert last_exc is not None
        raise last_exc

    async def _run_step(self, step: dict, context: dict, prior_results: dict) -> list:
        mod_class = self._resolve_module(step["module"])
        if not mod_class:
            warn(f"[playbook] Unknown module '{step['module']}' in step '{step['id']}'")
            return []

        deps = self._depends_on(step)
        if not deps:
            return await self._run_step_once(step, mod_class, context)

        # Depends on one or more prior steps: run once per node discovered by
        # ANY of them (fan-in union, not a cartesian product across parents --
        # e.g. "run shodan_scan on every IP discovered by DNS enum *or* cert
        # transparency"), deduped by node value so a node surfaced by more
        # than one parent only triggers this step once. Each iteration binds
        # the current node under EVERY declared dependency's name (not just
        # whichever parent actually produced it), so an `inputs` template
        # like `{{ dns_sweep.node_value }}` resolves correctly no matter which
        # parent supplied the node currently being processed -- otherwise a
        # step depending on multiple parents could only ever template against
        # whichever dep happens to be listed first.
        condition = step.get("condition")
        discovered: list = []
        seen_values: set = set()
        for dep in deps:
            for node in prior_results.get(dep, []):
                value = node.get("value")
                if value is not None and value in seen_values:
                    continue
                if condition:
                    try:
                        if not safe_eval_condition(condition, {"node": node}):
                            continue
                    except UnsafeExpressionError as e:
                        warn(f"[playbook] Rejecting condition in step '{step['id']}': {e}")
                        return discovered
                if value is not None:
                    seen_values.add(value)
                node_ctx = {"node_value": node.get("value"), "node": node}
                step_context = dict(context)
                for d in deps:
                    step_context[d] = node_ctx
                discovered.extend(await self._run_step_once(step, mod_class, step_context))
        return discovered

    async def run(self, playbook: dict, trigger_value: str) -> dict:
        """Execute every step, returning ``{step_id: [discovered nodes]}``.

        Steps run in dependency layers: everything whose ``depends_on`` is
        already satisfied executes concurrently (``asyncio.gather``), then the
        next layer becomes eligible -- the same per-depth concurrency model
        MagicEngine uses for BFS chaining.
        """
        steps = playbook.get("steps", [])
        steps_by_id = {s["id"]: s for s in steps}
        self._validate_dag(steps_by_id)
        self._emit({"type": "playbook_started", "step_ids": list(steps_by_id.keys())})

        context: dict = {"trigger": {"value": trigger_value}}
        results: dict = {}
        done: set = set()
        remaining = dict(steps_by_id)

        while remaining:
            ready = [
                s
                for s in remaining.values()
                if all(dep in done for dep in self._depends_on(s))
            ]
            if not ready:
                warn(
                    "[playbook] Unresolved dependency cycle involving: "
                    + ", ".join(remaining.keys())
                )
                break

            for s in ready:
                self._emit({"type": "step_started", "step_id": s["id"]})

            batch = await asyncio.gather(
                *(self._run_step(s, context, results) for s in ready),
                return_exceptions=True,
            )
            for step, outcome in zip(ready, batch):
                status = "completed"
                if isinstance(outcome, BaseException):
                    warn(f"[playbook] Step '{step['id']}' failed: {outcome}")
                    status = "failed"
                    outcome = []
                results[step["id"]] = outcome
                if outcome:
                    context[step["id"]] = {
                        "node_value": outcome[0].get("value"),
                        "nodes": outcome,
                    }
                done.add(step["id"])
                remaining.pop(step["id"], None)
                self._emit(
                    {
                        "type": "step_completed",
                        "step_id": step["id"],
                        "status": status,
                        "node_count": len(outcome),
                        "nodes": outcome,
                    }
                )

        self._emit({"type": "playbook_finished", "step_count": len(done)})
        return results
