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


def _fake_load_modules():
    return {
        "discovery/dns_sweep": DnsSweepMod,
        "dns_sweep": DnsSweepMod,
        "intel/shodan_ports": ShodanPortsMod,
        "shodan_ports": ShodanPortsMod,
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
