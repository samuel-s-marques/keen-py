import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.base_module import BaseModule
from src.core.magic import run_module_on_target
from src.core.managers import ConfigManager, WorkspaceManager

TEST_DIR = os.path.expanduser("~/.keen_test_run_module_on_target_tmp")


class MockShell:
    def __init__(self, workspace, config):
        self.workspace = workspace
        self.config = config
        self.is_web_context = True
        self._magic_running = True


class PassiveMod(BaseModule):
    metadata = {
        "name": "Passive Mod",
        "description": "",
        "options": {
            "TARGET": ["", True, "Target", "domain"],
            "EXTRA": ["default", False, "Extra option", None],
        },
    }

    async def run(self):
        extra = self.options.get("EXTRA")
        await self.post_run(
            {
                "nodes": [
                    {"type": "domain-name", "value": self.get_target(), "metadata": {}},
                    {"type": "x-note", "value": f"extra:{extra}", "metadata": {}},
                ],
                "edges": [],
            }
        )


class ActiveMod(BaseModule):
    metadata = {
        "name": "Active Mod",
        "description": "",
        "execution_safety": "active",
        "options": {"TARGET": ["", True, "Target", "domain"]},
    }

    async def run(self):
        await self.post_run(
            {"nodes": [{"type": "domain-name", "value": self.get_target(), "metadata": {}}], "edges": []}
        )


def _setup():
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    ws = WorkspaceManager(os.path.join(TEST_DIR, "ws.keen"), name="ws")
    config = ConfigManager(os.path.join(TEST_DIR, "config.db"))
    return ws, config


def _teardown(ws, config):
    ws.close()
    config.close()
    shutil.rmtree(TEST_DIR)


@pytest.mark.asyncio
async def test_passive_module_runs_and_returns_discovered_nodes():
    ws, config = _setup()
    try:
        shell = MockShell(ws, config)
        nodes = await run_module_on_target(PassiveMod, "example.com", shell, config)
        values = {n["value"] for n in nodes}
        assert "example.com" in values
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_extra_options_are_applied():
    ws, config = _setup()
    try:
        shell = MockShell(ws, config)
        nodes = await run_module_on_target(
            PassiveMod,
            "example.com",
            shell,
            config,
            extra_options={"EXTRA": "custom-value"},
        )
        values = {n["value"] for n in nodes}
        assert "extra:custom-value" in values
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_active_module_skipped_without_auto_confirm():
    ws, config = _setup()
    try:
        shell = MockShell(ws, config)
        nodes = await run_module_on_target(ActiveMod, "example.com", shell, config)
        assert nodes == []
        assert ws.get_node_id("example.com") is None
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_active_module_runs_with_auto_confirm():
    ws, config = _setup()
    try:
        shell = MockShell(ws, config)
        nodes = await run_module_on_target(
            ActiveMod, "example.com", shell, config, auto_confirm_active=True
        )
        values = {n["value"] for n in nodes}
        assert "example.com" in values
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_successful_run_records_completed_job():
    """Every module run through the shared engine leaves a job_history row --
    this is what makes magic-chained and playbook-driven runs show up in
    `jobs list`/the Web UI task panel, not just direct top-level `run`."""
    ws, config = _setup()
    try:
        shell = MockShell(ws, config)
        await run_module_on_target(PassiveMod, "example.com", shell, config)

        jobs = ws.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["module_name"] == "Passive Mod"
        assert jobs[0]["target_value"] == "example.com"
        assert jobs[0]["status"] == "completed"
        assert jobs[0]["nodes_added"] == 2
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_skipped_active_module_records_skipped_job():
    ws, config = _setup()
    try:
        shell = MockShell(ws, config)
        await run_module_on_target(ActiveMod, "example.com", shell, config)

        jobs = ws.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["status"] == "skipped"
        assert jobs[0]["ended_at"] is not None
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_failing_module_records_failed_job_and_still_raises():
    class BoomMod(BaseModule):
        metadata = {
            "name": "Boom Mod",
            "description": "",
            "options": {"TARGET": ["", True, "Target", "domain"]},
        }

        async def run(self):
            raise RuntimeError("boom")

    ws, config = _setup()
    try:
        shell = MockShell(ws, config)
        with pytest.raises(RuntimeError, match="boom"):
            await run_module_on_target(BoomMod, "example.com", shell, config)

        jobs = ws.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["status"] == "failed"
        assert jobs[0]["error_message"] == "boom"
    finally:
        _teardown(ws, config)
