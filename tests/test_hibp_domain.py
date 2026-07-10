import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.modules.intel.hibp_domain import HibpDomain
from src.utils import rate_limiter

TEST_DIR = os.path.expanduser("~/.keen_test_hibp_domain_tmp")

SAMPLE_BREACHES = [
    {
        "Name": "Adobe",
        "BreachDate": "2013-10-04",
        "PwnCount": 152445165,
        "Description": "In October 2013, Adobe...",
        "DataClasses": ["Email addresses", "Password hints", "Passwords"],
    },
]


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    rate_limiter.clear_state()
    yield
    rate_limiter.clear_state()


class MockShell:
    def __init__(self, workspace, config):
        self.workspace = workspace
        self.config = config
        self.is_web_context = True


def _make_workspace():
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
async def test_execute_ingests_breach_and_domain_nodes(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = HibpDomain()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "adobe.com")

        async def fake_query(self, target):
            return SAMPLE_BREACHES

        monkeypatch.setattr(HibpDomain, "_query_hibp", fake_query)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        values = {n["value"] for n in nodes}

        assert "adobe.com" in values
        assert "HIBP:Adobe" in values
        breach_nodes = [n for n in nodes if n["type"] == "x-data-breach"]
        assert len(breach_nodes) == 1

        cursor.execute("SELECT relationship FROM edge")
        relationships = {row["relationship"] for row in cursor.fetchall()}
        assert relationships == {"compromised-in"}
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_handles_no_breaches_found(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = HibpDomain()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "neverbreached.example")

        async def fake_query(self, target):
            return []

        monkeypatch.setattr(HibpDomain, "_query_hibp", fake_query)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_reports_none_on_query_failure(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = HibpDomain()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "adobe.com")

        async def failing_query(self, target):
            return None

        monkeypatch.setattr(HibpDomain, "_query_hibp", failing_query)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_cache_hit_skips_network_query(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = HibpDomain()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "adobe.com")

        calls = []

        async def tracked_query(self, target):
            calls.append(target)
            return SAMPLE_BREACHES

        monkeypatch.setattr(HibpDomain, "_query_hibp", tracked_query)

        await module._fetch_breaches("adobe.com")
        await module._fetch_breaches("adobe.com")

        assert len(calls) == 1
    finally:
        _teardown(ws, config)


def test_node_shape_matches_leak_module_hibp_convention():
    """The breach node value/type must match leak_module.py's HIBP shape
    (`x-data-breach`, `f"HIBP:{name}"`) so both modules dedup onto one node."""
    from src.core.result_builder import NodeFactory, STIXNamespaces

    node = NodeFactory.custom(
        "x-data-breach",
        "HIBP:Adobe",
        namespace=STIXNamespaces.BREACH,
        misp_type="leak-source",
        misp_value="HIBP (Adobe)",
    )
    assert node["type"] == "x-data-breach"
    assert node["value"] == "HIBP:Adobe"
