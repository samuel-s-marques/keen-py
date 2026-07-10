import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.modules.discovery.cert_transparency import CertTransparency
from src.utils import rate_limiter

TEST_DIR = os.path.expanduser("~/.keen_test_cert_transparency_tmp")


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    # The rate limiter's pacing state is process-global by design (see
    # rate_limiter.py) -- reset it so one test's "crtsh" call doesn't force
    # the next test to sleep out a leftover minimum-interval wait.
    rate_limiter.clear_state()
    yield
    rate_limiter.clear_state()


SAMPLE_ROWS = [
    {
        "id": 111,
        "issuer_name": "Let's Encrypt",
        "not_before": "2026-01-01",
        "not_after": "2026-04-01",
        "name_value": "example.com\nwww.example.com",
    },
    {
        "id": 111,
        "issuer_name": "Let's Encrypt",
        "not_before": "2026-01-01",
        "not_after": "2026-04-01",
        "name_value": "example.com",
    },
    {
        "id": 222,
        "issuer_name": "DigiCert",
        "not_before": "2025-01-01",
        "not_after": "2026-01-01",
        "name_value": "*.example.com\napi.example.com",
    },
]


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
    # A dedicated ConfigManager so cache_get/cache_set/rate_limit don't read
    # from or pollute the real ~/.keen/config.db.
    config = ConfigManager(os.path.join(TEST_DIR, "config.db"))
    return ws, config


def _teardown(ws: WorkspaceManager, config: ConfigManager) -> None:
    ws.close()
    config.close()
    shutil.rmtree(TEST_DIR)


def test_parse_certs_groups_rows_and_dedupes_names():
    parsed = CertTransparency._parse_certs(SAMPLE_ROWS)
    by_id = {c["id"]: c for c in parsed}

    assert set(by_id) == {"111", "222"}
    assert by_id["111"]["names"] == ["example.com", "www.example.com"]
    assert by_id["222"]["names"] == ["api.example.com"]  # wildcard entry dropped
    assert by_id["222"]["issuer"] == "DigiCert"


@pytest.mark.asyncio
async def test_execute_ingests_cert_and_domain_nodes(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = CertTransparency()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "example.com")

        async def fake_query_crtsh(self, target):
            return SAMPLE_ROWS

        monkeypatch.setattr(CertTransparency, "_query_crtsh", fake_query_crtsh)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        values = {n["value"] for n in nodes}

        assert "example.com" in values
        assert "www.example.com" in values
        assert "api.example.com" in values
        assert "crt.sh:111" in values
        assert "crt.sh:222" in values

        cert_nodes = [n for n in nodes if n["type"] == "x-ssl-certificate"]
        assert len(cert_nodes) == 2

        cursor.execute("SELECT relationship FROM edge")
        relationships = {row["relationship"] for row in cursor.fetchall()}
        assert "issued-for" in relationships
        assert "secured-by" in relationships
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_reports_none_on_query_failure(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = CertTransparency()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "example.com")

        async def failing_query(self, target):
            return None

        monkeypatch.setattr(CertTransparency, "_query_crtsh", failing_query)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_cache_hit_skips_network_query(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = CertTransparency()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "example.com")

        calls = []

        async def tracked_query(self, target):
            calls.append(target)
            return SAMPLE_ROWS

        monkeypatch.setattr(CertTransparency, "_query_crtsh", tracked_query)

        await module._fetch_certs("example.com")
        await module._fetch_certs("example.com")

        assert len(calls) == 1
    finally:
        _teardown(ws, config)
