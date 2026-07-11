import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.modules.web.wayback_snapshot import WaybackSnapshot
from src.utils import rate_limiter

TEST_DIR = os.path.expanduser("~/.keen_test_wayback_snapshot_tmp")

SAMPLE_AVAILABLE = {
    "archived_snapshots": {
        "closest": {
            "available": True,
            "url": "http://web.archive.org/web/20260101000000/https://example.com",
            "timestamp": "20260101000000",
            "status": "200",
        }
    }
}

SAMPLE_UNAVAILABLE = {"archived_snapshots": {}}


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    rate_limiter.clear_state()
    yield
    rate_limiter.clear_state()


class MockShell:
    def __init__(self, workspace, config, is_web_context=True, magic_running=False):
        self.workspace = workspace
        self.config = config
        self.is_web_context = is_web_context
        self._magic_running = magic_running


def _make_workspace():
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    ws = WorkspaceManager(os.path.join(TEST_DIR, "ws.keen"), name="ws")
    config = ConfigManager(os.path.join(TEST_DIR, "config.db"))
    return ws, config


def _teardown(ws: WorkspaceManager, config: ConfigManager) -> None:
    ws.close()
    config.close()
    shutil.rmtree(TEST_DIR)


def test_parse_availability_returns_none_when_no_snapshot():
    assert WaybackSnapshot._parse_availability(SAMPLE_UNAVAILABLE) is None


def test_parse_availability_extracts_snapshot():
    parsed = WaybackSnapshot._parse_availability(SAMPLE_AVAILABLE)
    assert parsed is not None
    assert parsed["archived_url"].startswith("http://web.archive.org/web/")
    assert parsed["timestamp"] == "20260101000000"


def test_execution_safety_defaults_to_passive():
    module = WaybackSnapshot()
    assert module.execution_safety == "passive"


def test_execution_safety_escalates_when_submit_enabled():
    module = WaybackSnapshot()
    module.set_option("SUBMIT_NEW_SNAPSHOT", "true")
    assert module.execution_safety == "active"


def test_submit_enabled_module_blocked_without_confirmation_in_web_context():
    module = WaybackSnapshot()
    module.set_option("TARGET", "https://example.com")
    module.set_option("SUBMIT_NEW_SNAPSHOT", "true")
    module.is_web_context = True
    module.shell = MockShell(None, None, is_web_context=True)
    assert module.pre_run() is False


@pytest.mark.asyncio
async def test_execute_check_only_ingests_existing_snapshot(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = WaybackSnapshot()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "https://example.com")

        async def fake_check(self, url):
            return WaybackSnapshot._parse_availability(SAMPLE_AVAILABLE)

        monkeypatch.setattr(WaybackSnapshot, "_check_availability", fake_check)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        types = {n["type"] for n in nodes}
        assert "url" in types
        assert "x-archive-snapshot" in types

        cursor.execute("SELECT relationship FROM edge")
        relationships = {row["relationship"] for row in cursor.fetchall()}
        assert "archived-as" in relationships
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_check_only_no_snapshot_does_not_submit(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = WaybackSnapshot()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "https://example.com")

        async def fake_check(self, url):
            return None

        submit_calls = []

        async def fake_submit(self, url):
            submit_calls.append(url)
            return None

        monkeypatch.setattr(WaybackSnapshot, "_check_availability", fake_check)
        monkeypatch.setattr(WaybackSnapshot, "_submit_snapshot", fake_submit)

        await module.run()

        assert submit_calls == []
        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_submits_when_no_snapshot_and_opted_in(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = WaybackSnapshot()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "https://example.com")
        module.set_option("SUBMIT_NEW_SNAPSHOT", "true")
        module.confirm_execution()

        async def fake_check(self, url):
            return None

        async def fake_submit(self, url):
            return WaybackSnapshot._parse_availability(SAMPLE_AVAILABLE)

        monkeypatch.setattr(WaybackSnapshot, "_check_availability", fake_check)
        monkeypatch.setattr(WaybackSnapshot, "_submit_snapshot", fake_submit)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type FROM nodes")
        types = {row["type"] for row in cursor.fetchall()}
        assert "x-archive-snapshot" in types
    finally:
        _teardown(ws, config)
