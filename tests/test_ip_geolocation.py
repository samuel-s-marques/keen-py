import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.modules.helpers.ip_geolocation import IpGeolocation
from src.utils import rate_limiter

TEST_DIR = os.path.expanduser("~/.keen_test_ip_geolocation_tmp")

SAMPLE_RESPONSE = {
    "ip": "93.184.216.34",
    "city": "Norwell",
    "region": "Massachusetts",
    "country_name": "United States",
    "latitude": 42.1596,
    "longitude": -70.8217,
    "org": "EdgeCast Networks",
    "asn": "AS15133",
}

SAMPLE_ERROR_RESPONSE = {"error": True, "reason": "Reserved IP Address"}


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


def _teardown(ws: WorkspaceManager, config: ConfigManager) -> None:
    ws.close()
    config.close()
    shutil.rmtree(TEST_DIR)


def test_parse_extracts_expected_fields():
    parsed = IpGeolocation._parse(SAMPLE_RESPONSE)
    assert parsed["city"] == "Norwell"
    assert parsed["region"] == "Massachusetts"
    assert parsed["country"] == "United States"
    assert parsed["latitude"] == 42.1596
    assert parsed["longitude"] == -70.8217
    assert parsed["org"] == "EdgeCast Networks"


@pytest.mark.asyncio
async def test_execute_ingests_location_and_organization_nodes(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = IpGeolocation()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "93.184.216.34")

        async def fake_lookup(self, ip):
            return IpGeolocation._parse(SAMPLE_RESPONSE)

        monkeypatch.setattr(IpGeolocation, "_lookup", fake_lookup)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        types = {n["type"] for n in nodes}

        assert "ipv4-addr" in types
        assert "location" in types
        assert "organization" in types

        location_node = next(n for n in nodes if n["type"] == "location")
        assert "Norwell" in location_node["value"]

        cursor.execute("SELECT relationship FROM edge")
        relationships = {row["relationship"] for row in cursor.fetchall()}
        assert "geolocated-to" in relationships
        assert "hosted-by" in relationships
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_reports_error_on_reserved_ip(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = IpGeolocation()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "10.0.0.1")

        async def fake_lookup(self, ip):
            return None

        monkeypatch.setattr(IpGeolocation, "_lookup", fake_lookup)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_ipv6_target_gets_ipv6_node_type(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = IpGeolocation()
        module.shell = MockShell(ws, config)
        ipv6 = "2606:2800:220:1:248:1893:25c8:1946"
        module.set_option("TARGET", ipv6)

        async def fake_lookup(self, ip):
            return IpGeolocation._parse(SAMPLE_RESPONSE)

        monkeypatch.setattr(IpGeolocation, "_lookup", fake_lookup)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type FROM nodes WHERE value = ?", (ipv6,))
        row = cursor.fetchone()
        assert row["type"] == "ipv6-addr"
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_lookup_returns_none_for_error_payload(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = IpGeolocation()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "10.0.0.1")

        class FakeResponse:
            status_code = 200

            def json(self):
                return SAMPLE_ERROR_RESPONSE

        async def fake_request(self, client, method, url, **kwargs):
            return FakeResponse()

        monkeypatch.setattr(IpGeolocation, "request", fake_request)

        result = await module._lookup("10.0.0.1")
        assert result is None
    finally:
        _teardown(ws, config)
