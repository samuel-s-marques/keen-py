import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.modules.helpers.domain_to_ip import DomainToIp

TEST_DIR = os.path.expanduser("~/.keen_test_domain_to_ip_tmp")


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


def _teardown(ws: WorkspaceManager, config: ConfigManager) -> None:
    ws.close()
    config.close()
    shutil.rmtree(TEST_DIR)


@pytest.mark.asyncio
async def test_execute_ingests_ip_nodes_and_resolves_to_edges(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = DomainToIp()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "example.com")

        async def fake_resolve(self, domain):
            return [
                {"ip": "93.184.216.34", "version": 4},
                {"ip": "2606:2800:220:1:248:1893:25c8:1946", "version": 6},
            ]

        monkeypatch.setattr(DomainToIp, "_resolve", fake_resolve)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        values = {n["value"] for n in nodes}

        assert "example.com" in values
        assert "93.184.216.34" in values
        assert "2606:2800:220:1:248:1893:25c8:1946" in values

        ip_nodes = [n for n in nodes if n["type"] in ("ipv4-addr", "ipv6-addr")]
        assert len(ip_nodes) == 2

        cursor.execute("SELECT relationship FROM edge")
        relationships = {row["relationship"] for row in cursor.fetchall()}
        assert relationships == {"resolves-to"}
        assert ws.get_edge_count() == 2
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_reports_nothing_ingested_on_no_records(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = DomainToIp()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "example.com")

        async def fake_resolve(self, domain):
            return []

        monkeypatch.setattr(DomainToIp, "_resolve", fake_resolve)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


def test_metadata_declares_domain_name_magic_consumer():
    assert DomainToIp.metadata["magic_consumes"] == ["domain-name"]
    assert DomainToIp.metadata["execution_safety"] == "passive"
