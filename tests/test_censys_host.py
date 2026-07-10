import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.modules.intel.censys_host import CensysHost
from src.utils import rate_limiter

TEST_DIR = os.path.expanduser("~/.keen_test_censys_host_tmp")

SAMPLE_RESULT = {
    "ip": "1.2.3.4",
    "autonomous_system": {"name": "Example Org", "asn": 12345},
    "services": [
        {
            "port": 443,
            "transport_protocol": "TCP",
            "service_name": "HTTP",
            "software": [{"product": "nginx", "version": "1.18.0"}],
            "cert": {
                "fingerprint_sha256": "cafebabe",
                "issuer": "Let's Encrypt",
                "subject": "example.com",
                "not_after": "2026-04-01",
            },
        },
        {
            "port": 22,
            "transport_protocol": "TCP",
            "service_name": "SSH",
            "software": [{"product": "OpenSSH", "version": "8.2"}],
        },
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


def _configure(module):
    module.set_option("TARGET", "1.2.3.4")
    module.set_option("CENSYS_API_ID", "fake-id")
    module.set_option("CENSYS_APIKEY", "fake-secret")


@pytest.mark.asyncio
async def test_execute_ingests_ports_org_and_cert(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = CensysHost()
        module.shell = MockShell(ws, config)
        _configure(module)

        async def fake_query(self, target, api_id, api_secret):
            return SAMPLE_RESULT

        monkeypatch.setattr(CensysHost, "_query_censys", fake_query)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        values = {n["value"] for n in nodes}

        assert "1.2.3.4" in values
        assert "Example Org" in values
        assert "1.2.3.4:443/tcp" in values
        assert "1.2.3.4:22/tcp" in values
        assert "censys:cafebabe" in values

        cert_nodes = [n for n in nodes if n["type"] == "x-ssl-certificate"]
        assert len(cert_nodes) == 1
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_requires_both_api_credentials():
    ws, config = _make_workspace()
    try:
        module = CensysHost()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "1.2.3.4")
        module.set_option("CENSYS_API_ID", "fake-id")
        # CENSYS_APIKEY intentionally left unset.

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_port_node_value_matches_shodan_convention(monkeypatch):
    """Same ip/port/transport must produce the identical x-port node value
    shodan_host.py would, so both modules' data merges onto one node."""
    ws, config = _make_workspace()
    try:
        module = CensysHost()
        module.shell = MockShell(ws, config)
        _configure(module)

        async def fake_query(self, target, api_id, api_secret):
            return SAMPLE_RESULT

        monkeypatch.setattr(CensysHost, "_query_censys", fake_query)
        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT value FROM nodes WHERE type = 'x-port'")
        port_values = {row["value"] for row in cursor.fetchall()}
        assert port_values == {"1.2.3.4:443/tcp", "1.2.3.4:22/tcp"}
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_cache_hit_skips_network_query(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = CensysHost()
        module.shell = MockShell(ws, config)
        _configure(module)

        calls = []

        async def tracked_query(self, target, api_id, api_secret):
            calls.append(target)
            return SAMPLE_RESULT

        monkeypatch.setattr(CensysHost, "_query_censys", tracked_query)

        await module._fetch_host("1.2.3.4", "fake-id", "fake-secret")
        await module._fetch_host("1.2.3.4", "fake-id", "fake-secret")

        assert len(calls) == 1
    finally:
        _teardown(ws, config)
