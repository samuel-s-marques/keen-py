import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.core.result_builder import NodeFactory
from src.modules.analysis.geolocation_estimator import GeolocationEstimator
from src.utils import rate_limiter

TEST_DIR = os.path.expanduser("~/.keen_test_geolocation_estimator_tmp")
SHA256 = "a" * 64

VISION_RESPONSE = {
    "responses": [
        {
            "landmarkAnnotations": [
                {
                    "description": "Carnaby Street",
                    "score": 0.87,
                    "locations": [
                        {"latLng": {"latitude": 51.5136, "longitude": -0.1402}}
                    ],
                },
                {
                    "description": "Soho",
                    "score": 0.42,
                    "locations": [],
                },
            ]
        }
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


def _seed_media_node(ws: WorkspaceManager, attachment_ref="images/a.jpg"):
    node = NodeFactory.media(
        SHA256,
        media_type="image",
        original_filename="a.jpg",
        size_bytes=123,
        attachment_ref=attachment_ref,
    )
    ws.get_or_add_node(node["type"], node["value"], node["metadata"])
    dest_dir = os.path.dirname(os.path.join(ws.attachments_dir(), attachment_ref))
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(ws.attachments_dir(), attachment_ref), "wb") as f:
        f.write(b"placeholder-bytes")


def _seed_exif_location(ws: WorkspaceManager, name="51.50000, -0.14000"):
    media_id = ws.get_node_id(SHA256)
    loc_node = NodeFactory.location(name, latitude=51.5, longitude=-0.14)
    loc_id = ws.get_or_add_node(loc_node["type"], loc_node["value"], loc_node["metadata"])
    assert media_id is not None
    assert loc_id is not None
    ws.add_edge(media_id, loc_id, "depicts-location")
    return name


def test_execution_safety_defaults_to_passive():
    module = GeolocationEstimator()
    assert module.execution_safety == "passive"


def test_execution_safety_escalates_when_api_key_set():
    module = GeolocationEstimator()
    module.set_option("GOOGLE_VISION_APIKEY", "key123")
    assert module.execution_safety == "active"


def test_parse_landmarks_extracts_and_sorts_by_confidence():
    candidates = GeolocationEstimator._parse_landmarks(VISION_RESPONSE)
    assert len(candidates) == 2
    assert candidates[0]["name"] == "Carnaby Street"
    assert candidates[0]["confidence"] == pytest.approx(0.87)
    assert candidates[0]["latitude"] == pytest.approx(51.5136)
    assert candidates[1]["name"] == "Soho"
    assert candidates[1]["latitude"] is None


def test_parse_landmarks_empty_without_annotations():
    assert GeolocationEstimator._parse_landmarks({"responses": [{}]}) == []
    assert GeolocationEstimator._parse_landmarks({"responses": []}) == []


@pytest.mark.asyncio
async def test_execute_reports_existing_exif_location_without_calling_vision(
    monkeypatch,
):
    ws, config = _make_workspace()
    try:
        _seed_media_node(ws)
        _seed_exif_location(ws)

        module = GeolocationEstimator()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", SHA256)
        module.set_option("GOOGLE_VISION_APIKEY", "key123")
        module.confirm_execution()

        called = []
        monkeypatch.setattr(
            GeolocationEstimator,
            "_detect_landmarks",
            lambda self, *a, **k: called.append(1),
        )

        edges_before = ws.get_edge_count()
        await module.run()

        assert called == []
        # No new edge/node from the Vision path -- only the pre-existing EXIF edge.
        assert ws.get_edge_count() == edges_before
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_no_signal_without_exif_or_api_key():
    ws, config = _make_workspace()
    try:
        _seed_media_node(ws)

        module = GeolocationEstimator()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", SHA256)

        await module.run()

        assert ws.get_edge_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_ingests_landmark_candidates(monkeypatch):
    ws, config = _make_workspace()
    try:
        _seed_media_node(ws)

        module = GeolocationEstimator()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", SHA256)
        module.set_option("GOOGLE_VISION_APIKEY", "key123")
        module.confirm_execution()

        async def fake_detect(self, file_path, api_key, max_results):
            return GeolocationEstimator._parse_landmarks(VISION_RESPONSE)

        monkeypatch.setattr(GeolocationEstimator, "_detect_landmarks", fake_detect)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes WHERE type = 'location'")
        locations = {row["value"] for row in cursor.fetchall()}
        assert "Carnaby Street" in locations
        assert "Soho" in locations

        cursor.execute(
            "SELECT confidence FROM edge WHERE relationship = 'probable-location-of'"
        )
        confidences = sorted(row["confidence"] for row in cursor.fetchall())
        assert confidences == sorted([0.87, 0.42])
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_skips_non_image_media():
    ws, config = _make_workspace()
    try:
        node = NodeFactory.media(SHA256, media_type="document")
        ws.get_or_add_node(node["type"], node["value"], node["metadata"])

        module = GeolocationEstimator()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", SHA256)
        module.set_option("GOOGLE_VISION_APIKEY", "key123")
        module.confirm_execution()

        await module.run()

        assert ws.get_edge_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_errors_on_unknown_media_node():
    ws, config = _make_workspace()
    try:
        module = GeolocationEstimator()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "b" * 64)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)
