import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.base_module import BaseModule
from src.core.managers import ConfigManager, WorkspaceManager
from src.core.playbooks import (
    PlaybookEngine,
    UnsafeExpressionError,
    load_playbook,
    render_template,
    safe_eval_condition,
    validate_playbook,
)

TEST_DIR = os.path.expanduser("~/.keen_test_playbooks_tmp")


# --------------------------------------------------------------------------
# safe_eval_condition
# --------------------------------------------------------------------------


def test_condition_equality_and_boolean_ops():
    node = {"type": "ipv4-addr", "is_private": False}
    assert safe_eval_condition("node.type == 'ipv4-addr' and not node.is_private", {"node": node}) is True
    assert safe_eval_condition("node.type == 'domain-name'", {"node": node}) is False


def test_condition_in_operator():
    node = {"type": "ipv4-addr"}
    assert safe_eval_condition("node.type in ['ipv4-addr', 'ipv6-addr']", {"node": node}) is True
    assert safe_eval_condition("node.type not in ['domain-name']", {"node": node}) is True


def test_condition_rejects_function_calls():
    with pytest.raises(UnsafeExpressionError):
        safe_eval_condition("__import__('os').system('echo hi')", {"node": {}})


def test_condition_rejects_unknown_identifiers():
    with pytest.raises(UnsafeExpressionError):
        safe_eval_condition("os.path.exists('/etc/passwd')", {"node": {}})


def test_condition_rejects_syntax_errors():
    with pytest.raises(UnsafeExpressionError):
        safe_eval_condition("node.type ==", {"node": {}})


def test_condition_rejects_comprehensions():
    with pytest.raises(UnsafeExpressionError):
        safe_eval_condition("[x for x in node.values()]", {"node": {}})


# --------------------------------------------------------------------------
# render_template
# --------------------------------------------------------------------------


def test_render_template_dotted_path():
    context = {"trigger": {"value": "example.com"}}
    assert render_template("{{ trigger.value }}", context) == "example.com"


def test_render_template_missing_key_renders_empty():
    context = {"trigger": {"value": "example.com"}}
    assert render_template("{{ trigger.missing }}", context) == ""


def test_render_template_mixed_text():
    context = {"trigger": {"value": "example.com"}}
    assert render_template("target=({{ trigger.value }})", context) == "target=(example.com)"


# --------------------------------------------------------------------------
# load_playbook
# --------------------------------------------------------------------------


def test_load_playbook_reads_valid_yaml(tmp_path):
    path = tmp_path / "test.yaml"
    path.write_text(
        "name: Test Playbook\ntrigger_type: domain-name\nsteps:\n  - id: a\n    module: x\n"
    )
    playbook = load_playbook(str(path))
    assert playbook["name"] == "Test Playbook"
    assert len(playbook["steps"]) == 1


def test_load_playbook_rejects_missing_steps(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("name: No Steps\n")
    with pytest.raises(ValueError):
        load_playbook(str(path))


# --------------------------------------------------------------------------
# PlaybookEngine execution
# --------------------------------------------------------------------------


class DnsSweepMod(BaseModule):
    metadata = {
        "name": "DNS Sweep",
        "description": "",
        "options": {"TARGET": ["", True, "Target", "domain"]},
    }

    async def run(self):
        target = self.get_target()
        await self.post_run(
            {
                "nodes": [
                    {"type": "ipv4-addr", "value": "10.0.0.1", "metadata": {"is_private": True}},
                    {"type": "ipv4-addr", "value": "1.2.3.4", "metadata": {"is_private": False}},
                ],
                "edges": [],
            }
        )


class ShodanPortsMod(BaseModule):
    metadata = {
        "name": "Shodan Ports",
        "description": "",
        "options": {"TARGET": ["", True, "Target", "ip"]},
    }

    async def run(self):
        target = self.get_target()
        await self.post_run(
            {"nodes": [{"type": "x-shodan-scan", "value": f"scanned:{target}", "metadata": {}}], "edges": []}
        )


class CertLogMod(BaseModule):
    metadata = {
        "name": "Cert Log",
        "description": "",
        "options": {"TARGET": ["", True, "Target", "domain"]},
    }

    async def run(self):
        target = self.get_target()
        await self.post_run(
            {
                "nodes": [
                    # 1.2.3.4 overlaps with DnsSweepMod's public IP -- this is
                    # what exercises fan-in dedup across two parents.
                    {"type": "ipv4-addr", "value": "1.2.3.4", "metadata": {"is_private": False}},
                    {"type": "ipv4-addr", "value": "5.6.7.8", "metadata": {"is_private": False}},
                ],
                "edges": [],
            }
        )


class CountingScanMod(BaseModule):
    """Records its own invocation count so a test can prove fan-in dedup
    collapses a node discovered by more than one parent into one call."""

    metadata = {
        "name": "Counting Scan",
        "description": "",
        "options": {"TARGET": ["", True, "Target", "ip"]},
    }
    call_count = 0

    async def run(self):
        target = self.get_target()
        CountingScanMod.call_count += 1
        await self.post_run(
            {"nodes": [{"type": "x-scan", "value": f"scanned:{target}", "metadata": {}}], "edges": []}
        )


class FlakyMod(BaseModule):
    """Fails on its first N invocations, then succeeds -- for retry tests."""

    metadata = {
        "name": "Flaky",
        "description": "",
        "options": {"TARGET": ["", True, "Target", "domain"]},
    }
    call_count = 0
    fail_until_attempt = 2

    async def run(self):
        FlakyMod.call_count += 1
        if FlakyMod.call_count < FlakyMod.fail_until_attempt:
            raise RuntimeError(f"simulated failure #{FlakyMod.call_count}")
        await self.post_run(
            {"nodes": [{"type": "x-flaky-result", "value": "recovered", "metadata": {}}], "edges": []}
        )


class SlowMod(BaseModule):
    """Sleeps longer than any reasonable timeout -- for timeout tests."""

    metadata = {
        "name": "Slow",
        "description": "",
        "options": {"TARGET": ["", True, "Target", "domain"]},
    }

    async def run(self):
        import asyncio as _asyncio

        await _asyncio.sleep(5)
        await self.post_run({"nodes": [], "edges": []})


def _fake_load_modules():
    return {
        "discovery/dns_sweep": DnsSweepMod,
        "dns_sweep": DnsSweepMod,
        "intel/shodan_ports": ShodanPortsMod,
        "shodan_ports": ShodanPortsMod,
        "discovery/cert_log": CertLogMod,
        "cert_log": CertLogMod,
        "intel/counting_scan": CountingScanMod,
        "counting_scan": CountingScanMod,
        "test/flaky": FlakyMod,
        "flaky": FlakyMod,
        "test/slow": SlowMod,
        "slow": SlowMod,
    }


class MockShell:
    def __init__(self, workspace, config):
        self.workspace = workspace
        self.config = config
        self.is_web_context = True
        self._magic_running = True


def _setup(monkeypatch):
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    ws = WorkspaceManager(os.path.join(TEST_DIR, "ws.keen"), name="ws")
    config = ConfigManager(os.path.join(TEST_DIR, "config.db"))
    monkeypatch.setattr("src.core.playbooks.load_modules", _fake_load_modules)
    return ws, config


def _teardown(ws, config):
    ws.close()
    config.close()
    shutil.rmtree(TEST_DIR)


@pytest.mark.asyncio
async def test_playbook_runs_independent_steps(monkeypatch):
    ws, config = _setup(monkeypatch)
    try:
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [
                {
                    "id": "dns_sweep",
                    "module": "discovery/dns_sweep",
                    "inputs": {"TARGET": "{{ trigger.value }}"},
                }
            ]
        }
        results = await engine.run(playbook, "example.com")
        values = {n["value"] for n in results["dns_sweep"]}
        assert values == {"10.0.0.1", "1.2.3.4"}
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_dependent_step_filters_by_condition(monkeypatch):
    ws, config = _setup(monkeypatch)
    try:
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [
                {
                    "id": "dns_sweep",
                    "module": "discovery/dns_sweep",
                    "inputs": {"TARGET": "{{ trigger.value }}"},
                },
                {
                    "id": "shodan_ports",
                    "module": "intel/shodan_ports",
                    "depends_on": "dns_sweep",
                    "inputs": {"TARGET": "{{ dns_sweep.node_value }}"},
                    "condition": "node.type == 'ipv4-addr' and not node.metadata.is_private",
                },
            ]
        }
        results = await engine.run(playbook, "example.com")
        # Only the public IP (1.2.3.4) should have passed the condition and
        # been scanned -- the private 10.0.0.1 must not reach shodan_ports.
        scanned_values = {n["value"] for n in results["shodan_ports"]}
        assert scanned_values == {"scanned:1.2.3.4"}
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_rejects_unknown_depends_on(monkeypatch):
    ws, config = _setup(monkeypatch)
    try:
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [
                {"id": "a", "module": "discovery/dns_sweep", "depends_on": "nonexistent"},
            ]
        }
        with pytest.raises(ValueError):
            await engine.run(playbook, "example.com")
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_detects_dependency_cycle(monkeypatch):
    ws, config = _setup(monkeypatch)
    try:
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [
                {"id": "a", "module": "discovery/dns_sweep", "depends_on": "b"},
                {"id": "b", "module": "discovery/dns_sweep", "depends_on": "a"},
            ]
        }
        # Must not hang -- the cycle is detected and the engine gives up
        # gracefully rather than looping forever.
        results = await engine.run(playbook, "example.com")
        assert results == {}
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_unknown_module_skips_step_without_crashing(monkeypatch):
    ws, config = _setup(monkeypatch)
    try:
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [{"id": "a", "module": "does/not_exist", "inputs": {"TARGET": "x"}}]
        }
        results = await engine.run(playbook, "example.com")
        assert results["a"] == []
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_step_runs_record_job_history(monkeypatch):
    """Playbook steps execute via the shared run_module_on_target() helper,
    so they must show up in job_history just like CLI `run` and magic
    chaining do -- previously the playbook interpreter was invisible to
    `jobs list`/the Web UI task panel."""
    ws, config = _setup(monkeypatch)
    try:
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [
                {
                    "id": "dns_sweep",
                    "module": "discovery/dns_sweep",
                    "inputs": {"TARGET": "{{ trigger.value }}"},
                }
            ]
        }
        await engine.run(playbook, "example.com")

        jobs = ws.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["target_value"] == "example.com"
        assert jobs[0]["status"] == "completed"
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_multi_parent_fan_in_dedups_shared_node(monkeypatch):
    """A step depending on two parents runs once per node from EITHER parent
    (union, not cartesian product), and a node both parents discover
    (1.2.3.4) must only trigger one invocation, not two."""
    ws, config = _setup(monkeypatch)
    try:
        CountingScanMod.call_count = 0
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [
                {
                    "id": "dns_sweep",
                    "module": "discovery/dns_sweep",
                    "inputs": {"TARGET": "{{ trigger.value }}"},
                },
                {
                    "id": "cert_log",
                    "module": "discovery/cert_log",
                    "inputs": {"TARGET": "{{ trigger.value }}"},
                },
                {
                    "id": "scan",
                    "module": "intel/counting_scan",
                    "depends_on": ["dns_sweep", "cert_log"],
                    "inputs": {"TARGET": "{{ dns_sweep.node_value }}"},
                    "condition": "node.type == 'ipv4-addr' and not node.metadata.is_private",
                },
            ]
        }
        results = await engine.run(playbook, "example.com")

        # dns_sweep -> {10.0.0.1 (private), 1.2.3.4}; cert_log -> {1.2.3.4, 5.6.7.8}.
        # Public-IP union across both, deduped, is {1.2.3.4, 5.6.7.8}: exactly
        # two invocations, not three.
        scanned_values = {n["value"] for n in results["scan"]}
        assert scanned_values == {"scanned:1.2.3.4", "scanned:5.6.7.8"}
        assert CountingScanMod.call_count == 2
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_multi_parent_templates_resolve_regardless_of_source(monkeypatch):
    """inputs templates referencing a specific dep id must resolve correctly
    even for nodes that came from a *different* declared dependency -- every
    declared dep is bound to the current node, not just the one that found it."""
    ws, config = _setup(monkeypatch)
    try:
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [
                {"id": "dns_sweep", "module": "discovery/dns_sweep", "inputs": {"TARGET": "{{ trigger.value }}"}},
                {"id": "cert_log", "module": "discovery/cert_log", "inputs": {"TARGET": "{{ trigger.value }}"}},
                {
                    "id": "scan",
                    "module": "intel/shodan_ports",
                    "depends_on": ["dns_sweep", "cert_log"],
                    # Templated against the dns_sweep dep name even for nodes
                    # actually produced by cert_log.
                    "inputs": {"TARGET": "{{ dns_sweep.node_value }}"},
                    "condition": "node.type == 'ipv4-addr' and not node.metadata.is_private",
                },
            ]
        }
        results = await engine.run(playbook, "example.com")
        scanned_values = {n["value"] for n in results["scan"]}
        # 5.6.7.8 only exists via cert_log -- if the template only resolved
        # against the literal "dns_sweep" context key, this would render as
        # dns_sweep's stale first-node fallback instead of 5.6.7.8 itself.
        assert "scanned:5.6.7.8" in scanned_values
        assert "scanned:1.2.3.4" in scanned_values
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_step_retries_until_success(monkeypatch):
    ws, config = _setup(monkeypatch)
    try:
        FlakyMod.call_count = 0
        FlakyMod.fail_until_attempt = 2
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [
                {
                    "id": "a",
                    "module": "test/flaky",
                    "inputs": {"TARGET": "{{ trigger.value }}"},
                    "retry": {"max_attempts": 3, "backoff_seconds": 0},
                }
            ]
        }
        results = await engine.run(playbook, "example.com")
        assert [n["value"] for n in results["a"]] == ["recovered"]
        assert FlakyMod.call_count == 2
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_step_exhausts_retries_and_fails(monkeypatch):
    ws, config = _setup(monkeypatch)
    try:
        FlakyMod.call_count = 0
        FlakyMod.fail_until_attempt = 10  # never recovers within the retry budget
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [
                {
                    "id": "a",
                    "module": "test/flaky",
                    "inputs": {"TARGET": "{{ trigger.value }}"},
                    "retry": {"max_attempts": 2, "backoff_seconds": 0},
                }
            ]
        }
        results = await engine.run(playbook, "example.com")
        assert results["a"] == []
        assert FlakyMod.call_count == 2

        jobs = ws.list_jobs()
        assert jobs[-1]["status"] == "failed"
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_step_timeout_cancels_job_cleanly(monkeypatch):
    """A step exceeding timeout_seconds must not leave its job_history row
    stuck at status='running' forever -- asyncio.CancelledError (raised by
    wait_for's internal cancellation) is a BaseException, not an Exception,
    so run_module_on_target must handle it explicitly (see magic.py)."""
    ws, config = _setup(monkeypatch)
    try:
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        playbook = {
            "steps": [
                {
                    "id": "a",
                    "module": "test/slow",
                    "inputs": {"TARGET": "{{ trigger.value }}"},
                    "timeout_seconds": 0.05,
                }
            ]
        }
        results = await engine.run(playbook, "example.com")
        assert results["a"] == []

        jobs = ws.list_jobs()
        assert jobs[-1]["status"] == "cancelled"
    finally:
        _teardown(ws, config)


# --------------------------------------------------------------------------
# validate_playbook
# --------------------------------------------------------------------------


def test_validate_playbook_accepts_well_formed_playbook(monkeypatch):
    monkeypatch.setattr("src.core.playbooks.load_modules", _fake_load_modules)
    playbook = {
        "steps": [
            {"id": "dns_sweep", "module": "discovery/dns_sweep", "inputs": {"TARGET": "{{ trigger.value }}"}},
            {
                "id": "shodan_ports",
                "module": "intel/shodan_ports",
                "depends_on": "dns_sweep",
                "condition": "node.type == 'ipv4-addr'",
            },
        ]
    }
    result = validate_playbook(playbook)
    assert result == {"errors": [], "warnings": []}


def test_validate_playbook_rejects_missing_steps():
    assert validate_playbook({"name": "no steps"})["errors"]
    assert validate_playbook("not a dict")["errors"]


def test_validate_playbook_rejects_step_missing_id_or_module():
    result = validate_playbook({"steps": [{"module": "x"}]})
    assert any("id" in e for e in result["errors"])


def test_validate_playbook_rejects_duplicate_step_ids():
    result = validate_playbook(
        {"steps": [{"id": "a", "module": "x"}, {"id": "a", "module": "y"}]}
    )
    assert any("Duplicate" in e for e in result["errors"])


def test_validate_playbook_rejects_unknown_depends_on():
    result = validate_playbook(
        {"steps": [{"id": "a", "module": "x", "depends_on": "nonexistent"}]}
    )
    assert any("unknown step" in e for e in result["errors"])


def test_validate_playbook_detects_cycle():
    result = validate_playbook(
        {
            "steps": [
                {"id": "a", "module": "x", "depends_on": "b"},
                {"id": "b", "module": "x", "depends_on": "a"},
            ]
        }
    )
    assert any("cycle" in e.lower() for e in result["errors"])


def test_validate_playbook_warns_on_unknown_module(monkeypatch):
    monkeypatch.setattr("src.core.playbooks.load_modules", _fake_load_modules)
    result = validate_playbook({"steps": [{"id": "a", "module": "does/not_exist"}]})
    assert result["errors"] == []
    assert any("unknown module" in w for w in result["warnings"])


def test_validate_playbook_warns_on_invalid_condition_syntax(monkeypatch):
    monkeypatch.setattr("src.core.playbooks.load_modules", _fake_load_modules)
    result = validate_playbook(
        {"steps": [{"id": "a", "module": "discovery/dns_sweep", "condition": "node.type =="}]}
    )
    assert result["errors"] == []
    assert any("invalid condition" in w for w in result["warnings"])


def test_validate_playbook_warns_on_invalid_timeout_seconds(monkeypatch):
    monkeypatch.setattr("src.core.playbooks.load_modules", _fake_load_modules)
    result = validate_playbook(
        {"steps": [{"id": "a", "module": "discovery/dns_sweep", "timeout_seconds": -1}]}
    )
    assert result["errors"] == []
    assert any("timeout_seconds" in w for w in result["warnings"])

    result_ok = validate_playbook(
        {"steps": [{"id": "a", "module": "discovery/dns_sweep", "timeout_seconds": 30}]}
    )
    assert result_ok["warnings"] == []


def test_validate_playbook_warns_on_invalid_retry_block(monkeypatch):
    monkeypatch.setattr("src.core.playbooks.load_modules", _fake_load_modules)

    result = validate_playbook(
        {"steps": [{"id": "a", "module": "discovery/dns_sweep", "retry": "not-a-mapping"}]}
    )
    assert any("retry" in w for w in result["warnings"])

    result_bad_attempts = validate_playbook(
        {"steps": [{"id": "a", "module": "discovery/dns_sweep", "retry": {"max_attempts": 0}}]}
    )
    assert any("max_attempts" in w for w in result_bad_attempts["warnings"])

    result_bad_backoff = validate_playbook(
        {
            "steps": [
                {
                    "id": "a",
                    "module": "discovery/dns_sweep",
                    "retry": {"max_attempts": 2, "backoff_seconds": -1},
                }
            ]
        }
    )
    assert any("backoff_seconds" in w for w in result_bad_backoff["warnings"])

    result_ok = validate_playbook(
        {
            "steps": [
                {
                    "id": "a",
                    "module": "discovery/dns_sweep",
                    "retry": {"max_attempts": 3, "backoff_seconds": 1.5},
                }
            ]
        }
    )
    assert result_ok["warnings"] == []


# --------------------------------------------------------------------------
# PlaybookEngine._event_sink / _emit
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_playbook_run_emits_step_lifecycle_events(monkeypatch):
    ws, config = _setup(monkeypatch)
    try:
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)
        events: list = []
        engine._event_sink = events.append
        playbook = {
            "steps": [
                {
                    "id": "dns_sweep",
                    "module": "discovery/dns_sweep",
                    "inputs": {"TARGET": "{{ trigger.value }}"},
                }
            ]
        }
        await engine.run(playbook, "example.com")

        types = [e["type"] for e in events]
        assert types == ["playbook_started", "step_started", "step_completed", "playbook_finished"]
        completed = events[2]
        assert completed["step_id"] == "dns_sweep"
        assert completed["status"] == "completed"
        assert completed["node_count"] == 2
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_playbook_run_survives_broken_event_sink(monkeypatch):
    ws, config = _setup(monkeypatch)
    try:
        shell = MockShell(ws, config)
        engine = PlaybookEngine(shell, config)

        def _boom(_event):
            raise RuntimeError("sink is broken")

        engine._event_sink = _boom
        playbook = {
            "steps": [
                {
                    "id": "dns_sweep",
                    "module": "discovery/dns_sweep",
                    "inputs": {"TARGET": "{{ trigger.value }}"},
                }
            ]
        }
        # Must not raise even though every _emit() call's sink throws.
        results = await engine.run(playbook, "example.com")
        assert len(results["dns_sweep"]) == 2
    finally:
        _teardown(ws, config)
