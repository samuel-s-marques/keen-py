import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.core.result_builder import NodeFactory
from src.modules.analysis.reverse_image_search import ReverseImageSearch
from src.utils import rate_limiter

TEST_DIR = os.path.expanduser("~/.keen_test_reverse_image_search_tmp")
SHA256 = "c" * 64

SERPAPI_RESPONSE = {
    "visual_matches": [
        {
            "link": "https://example.com/carnaby-street",
            "title": "Carnaby Street, London",
            "source": "example.com",
        },
        {
            "link": "https://example.org/soho-shops",
            "title": "Soho Shopping Guide",
            "source": "example.org",
        },
    ]
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


def _teardown(ws: WorkspaceManager, config: ConfigManager) -> None:
    ws.close()
    config.close()
    shutil.rmtree(TEST_DIR)


def _seed_media_node(ws: WorkspaceManager):
    node = NodeFactory.media(
        SHA256, media_type="image", original_filename="a.jpg", attachment_ref="images/c.jpg"
    )
    ws.get_or_add_node(node["type"], node["value"], node["metadata"])


def test_metadata_declares_no_magic_consumes():
    assert "magic_consumes" not in ReverseImageSearch.metadata


def test_metadata_execution_safety_is_active():
    module = ReverseImageSearch()
    assert module.execution_safety == "active"


def test_parse_matches_extracts_rank_based_confidence():
    matches = ReverseImageSearch._parse_matches(SERPAPI_RESPONSE, max_results=10)
    assert len(matches) == 2
    assert matches[0]["link"] == "https://example.com/carnaby-street"
    assert matches[0]["confidence"] == pytest.approx(0.9)
    assert matches[1]["confidence"] == pytest.approx(0.82)


def test_parse_matches_respects_max_results():
    matches = ReverseImageSearch._parse_matches(SERPAPI_RESPONSE, max_results=1)
    assert len(matches) == 1


def test_parse_matches_skips_entries_without_link():
    data = {"visual_matches": [{"title": "no link here"}]}
    assert ReverseImageSearch._parse_matches(data, max_results=10) == []


@pytest.mark.asyncio
async def test_execute_requires_source_image_url():
    ws, config = _make_workspace()
    try:
        _seed_media_node(ws)

        module = ReverseImageSearch()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", SHA256)
        module.set_option("SERPAPI_APIKEY", "key123")
        module.confirm_execution()

        await module.run()

        assert ws.get_edge_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_requires_api_key():
    ws, config = _make_workspace()
    try:
        _seed_media_node(ws)

        module = ReverseImageSearch()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", SHA256)
        module.set_option("SOURCE_IMAGE_URL", "https://cdn.example.com/a.jpg")
        module.confirm_execution()

        await module.run()

        assert ws.get_edge_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_ingests_visual_matches(monkeypatch):
    ws, config = _make_workspace()
    try:
        _seed_media_node(ws)

        module = ReverseImageSearch()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", SHA256)
        module.set_option("SOURCE_IMAGE_URL", "https://cdn.example.com/a.jpg")
        module.set_option("SERPAPI_APIKEY", "key123")
        module.confirm_execution()

        async def fake_search(self, source_url, api_key, max_results):
            return ReverseImageSearch._parse_matches(SERPAPI_RESPONSE, max_results)

        monkeypatch.setattr(ReverseImageSearch, "_search", fake_search)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes WHERE type = 'x-reverse-image-match'")
        values = {row["value"] for row in cursor.fetchall()}
        assert "https://example.com/carnaby-street" in values
        assert "https://example.org/soho-shops" in values

        cursor.execute(
            "SELECT relationship FROM edge WHERE relationship = 'possibly-same-place-as'"
        )
        assert len(cursor.fetchall()) == 2
    finally:
        _teardown(ws, config)
