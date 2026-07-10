import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.modules.intel.shodan_host import ShodanHost
from src.utils import rate_limiter

TEST_DIR = os.path.expanduser("~/.keen_test_shodan_host_tmp")

SAMPLE_HOST = {
    "ip_str": "1.2.3.4",
    "org": "Example Org",
    "data": [
        {
            "port": 443,
            "transport": "tcp",
            "product": "nginx",
            "version": "1.18.0",
            "ssl": {
                "cert": {
                    "fingerprint": {"sha256": "deadbeef"},
                    "issuer": {"CN": "Let's Encrypt"},
                    "subject": {"CN": "example.com"},
                    "expires": "20260401000000",
                }
            },
        },
        {"port": 22, "transport": "tcp", "product": "OpenSSH", "version": "8.2"},
    ],
}


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
async def test_execute_ingests_ports_org_and_cert(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = ShodanHost()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "1.2.3.4")
        module.set_option("SHODAN_APIKEY", "fake-key")

        async def fake_query(self, target, api_key):
            return SAMPLE_HOST

        monkeypatch.setattr(ShodanHost, "_query_shodan", fake_query)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        values = {n["value"] for n in nodes}

        assert "1.2.3.4" in values
        assert "Example Org" in values
        assert "1.2.3.4:443/tcp" in values
        assert "1.2.3.4:22/tcp" in values
        assert "shodan:deadbeef" in values

        cert_nodes = [n for n in nodes if n["type"] == "x-ssl-certificate"]
        assert len(cert_nodes) == 1

        cursor.execute("SELECT relationship FROM edge")
        relationships = {row["relationship"] for row in cursor.fetchall()}
        assert relationships == {
            "belongs-to-org",
            "has-open-port",
            "issued-for",
            "secured-by",
        }
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_requires_api_key():
    ws, config = _make_workspace()
    try:
        module = ShodanHost()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "1.2.3.4")
        # No SHODAN_APIKEY set.

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_handles_404_gracefully(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = ShodanHost()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "1.2.3.4")
        module.set_option("SHODAN_APIKEY", "fake-key")

        async def fake_query(self, target, api_key):
            return {}

        monkeypatch.setattr(ShodanHost, "_query_shodan", fake_query)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_cache_hit_skips_network_query(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = ShodanHost()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "1.2.3.4")
        module.set_option("SHODAN_APIKEY", "fake-key")

        calls = []

        async def tracked_query(self, target, api_key):
            calls.append(target)
            return SAMPLE_HOST

        monkeypatch.setattr(ShodanHost, "_query_shodan", tracked_query)

        await module._fetch_host("1.2.3.4", "fake-key")
        await module._fetch_host("1.2.3.4", "fake-key")

        assert len(calls) == 1
    finally:
        _teardown(ws, config)
