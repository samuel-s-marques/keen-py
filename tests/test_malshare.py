import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.modules.intel.malshare import Malshare
from src.utils import rate_limiter

TEST_DIR = os.path.expanduser("~/.keen_test_malshare_tmp")

SAMPLE_HASH = "d41d8cd98f00b204e9800998ecf8427e"

SAMPLE_DETAILS = {
    "MD5": SAMPLE_HASH,
    "F_TYPE": "PE32 executable",
    "SSDEEP": "3:abc:def",
    "SOURCES": ["vt", "malwarebazaar"],
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
    module.set_option("TARGET", SAMPLE_HASH)
    module.set_option("MALSHARE_APIKEY", "fake-key")


@pytest.mark.asyncio
async def test_execute_ingests_hash_and_sample_on_hit(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = Malshare()
        module.shell = MockShell(ws, config)
        _configure(module)

        async def fake_query(self, target, api_key):
            return SAMPLE_DETAILS

        monkeypatch.setattr(Malshare, "_query_malshare", fake_query)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        values = {n["value"] for n in nodes}

        assert SAMPLE_HASH in values
        assert f"malshare:{SAMPLE_HASH}" in values

        cursor.execute("SELECT relationship FROM edge")
        assert {row["relationship"] for row in cursor.fetchall()} == {"matches"}
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_treats_error_payload_as_miss_not_failure(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = Malshare()
        module.shell = MockShell(ws, config)
        _configure(module)

        async def fake_query(self, target, api_key):
            return {}  # _query_malshare already normalizes ERROR payloads to {}

        monkeypatch.setattr(Malshare, "_query_malshare", fake_query)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_requires_api_key():
    ws, config = _make_workspace()
    try:
        module = Malshare()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", SAMPLE_HASH)
        # No MALSHARE_APIKEY set.

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_query_normalizes_error_payload_to_empty_dict(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = Malshare()
        module.shell = MockShell(ws, config)
        _configure(module)

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"ERROR": "Sample not found by hash. Try again"}

        async def fake_request(self, client, method, url, **kwargs):
            return FakeResponse()

        monkeypatch.setattr(Malshare, "request", fake_request)

        result = await module._query_malshare(SAMPLE_HASH, "fake-key")
        assert result == {}
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_cache_hit_skips_network_query(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = Malshare()
        module.shell = MockShell(ws, config)
        _configure(module)

        calls = []

        async def tracked_query(self, target, api_key):
            calls.append(target)
            return SAMPLE_DETAILS

        monkeypatch.setattr(Malshare, "_query_malshare", tracked_query)

        await module._fetch_sample(SAMPLE_HASH, "fake-key")
        await module._fetch_sample(SAMPLE_HASH, "fake-key")

        assert len(calls) == 1
    finally:
        _teardown(ws, config)
