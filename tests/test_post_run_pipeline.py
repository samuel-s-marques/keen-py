import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.base_module import BaseModule
from src.core.managers import WorkspaceManager

TEST_DIR = os.path.expanduser("~/.keen_test_post_run_pipeline_tmp")


class MockShell:
    """Mirrors tests/test_magic.py's MockShell: web context + magic chaining
    suppressed by default so ingestion can be tested in isolation."""

    def __init__(self, workspace, config=None):
        self.workspace = workspace
        self.config = config
        self._magic_running = True
        self.is_web_context = True


class MockRecon(BaseModule):
    metadata = {
        "name": "Mock Recon",
        "description": "Mock recon module for pipeline tests",
        "options": {"TARGET": ["", True, "Target domain", "domain"]},
    }


class MockIntrusiveModule(BaseModule):
    metadata = {
        "name": "Mock Intrusive",
        "description": "Mock intrusive module",
        "execution_safety": "intrusive",
        "options": {"TARGET": ["", True, "Target domain", "domain"]},
    }


def _make_workspace(name: str) -> WorkspaceManager:
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    return WorkspaceManager(os.path.join(TEST_DIR, f"{name}.keen"), name=name)


def test_execution_safety_defaults_to_passive():
    module = MockRecon()
    assert module.execution_safety == "passive"


def test_execution_safety_reads_declared_metadata():
    module = MockIntrusiveModule()
    assert module.execution_safety == "intrusive"


def test_execution_safety_rejects_unknown_value():
    class MockBadTag(BaseModule):
        metadata = {"name": "Bad", "description": "", "execution_safety": "nonsense"}

    assert MockBadTag().execution_safety == "passive"


@pytest.mark.asyncio
async def test_post_run_quarantines_out_of_scope_node_but_still_ingests_it():
    ws = _make_workspace("pipeline_scope")
    try:
        ws.add_scope_entry("domain", "example.com")

        module = MockRecon()
        module.shell = MockShell(ws)
        module.set_option("TARGET", "example.com")

        await module.post_run(
            {
                "nodes": [{"type": "domain-name", "value": "evil.com", "metadata": {}}],
                "edges": [],
            }
        )

        quarantined = ws.get_quarantined_nodes()
        assert len(quarantined) == 1
        assert quarantined[0]["value"] == "evil.com"
        # Still ingested, not dropped.
        assert ws.get_node_id("evil.com") is not None
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


@pytest.mark.asyncio
async def test_post_run_records_provenance_ledger_entry():
    ws = _make_workspace("pipeline_ledger")
    try:
        module = MockRecon()
        module.shell = MockShell(ws)
        module.set_option("TARGET", "example.com")

        await module.post_run(
            {
                "nodes": [{"type": "domain-name", "value": "example.com", "metadata": {}}],
                "edges": [],
            },
            raw={"whois": "raw response text"},
        )

        entries = ws.get_ledger_entries()
        assert len(entries) == 1
        assert entries[0]["actor"] == "Mock Recon"
        assert entries[0]["action"] == "run"
        assert entries[0]["target_value"] == "example.com"
        assert "raw response text" in entries[0]["raw_payload"]
        assert ws.verify_ledger_integrity() is True
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


@pytest.mark.asyncio
async def test_post_run_falls_back_to_summary_when_no_raw_payload_given():
    ws = _make_workspace("pipeline_ledger_summary")
    try:
        module = MockRecon()
        module.shell = MockShell(ws)
        module.set_option("TARGET", "example.com")

        await module.post_run(
            {
                "nodes": [{"type": "domain-name", "value": "example.com", "metadata": {}}],
                "edges": [],
            }
        )

        entries = ws.get_ledger_entries()
        payload = json.loads(entries[0]["raw_payload"])
        assert payload == {"nodes_added": 1, "edges_added": 0}
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


@pytest.mark.asyncio
async def test_post_run_stores_edge_confidence():
    ws = _make_workspace("pipeline_confidence")
    try:
        module = MockRecon()
        module.shell = MockShell(ws)
        module.set_option("TARGET", "a.com")

        await module.post_run(
            {
                "nodes": [
                    {"type": "domain-name", "value": "a.com", "metadata": {}},
                    {"type": "domain-name", "value": "b.com", "metadata": {}},
                ],
                "edges": [
                    {
                        "source": "a.com",
                        "target": "b.com",
                        "relationship": "possibly_same_org",
                        "confidence": 0.6,
                    }
                ],
            }
        )

        cursor = ws.conn.cursor()
        cursor.execute("SELECT confidence FROM edge")
        row = cursor.fetchone()
        assert row["confidence"] == pytest.approx(0.6)
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


@pytest.mark.asyncio
async def test_magic_chaining_skips_quarantined_nodes():
    """A quarantined discovery must not silently continue expanding the crawl."""
    ws = _make_workspace("pipeline_magic_skip")
    try:
        from src.core.managers import ConfigManager

        config_path = os.path.join(TEST_DIR, "config.db")
        config = ConfigManager(config_path)
        config.set_preference("magic_enabled", "true")

        shell = MockShell(ws, config=config)
        shell._magic_running = False  # allow chaining to actually attempt to run

        module = MockRecon()
        module.shell = shell
        module.set_option("TARGET", "in-scope.com")

        chained_values = []

        class RecordingEngine:
            def __init__(self, *args, **kwargs):
                pass

            async def run_chain(self, value, initial_type=None, force=False):
                chained_values.append(value)

        import src.core.magic as magic_module

        original_engine = magic_module.MagicEngine
        magic_module.MagicEngine = RecordingEngine
        try:
            ws.add_scope_entry("domain", "in-scope.com")
            await module.post_run(
                {
                    "nodes": [
                        {"type": "domain-name", "value": "in-scope.com", "metadata": {}},
                        {"type": "domain-name", "value": "out-of-scope.com", "metadata": {}},
                    ],
                    "edges": [],
                }
            )
        finally:
            magic_module.MagicEngine = original_engine
            config.close()

        assert "in-scope.com" in chained_values
        assert "out-of-scope.com" not in chained_values
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)
