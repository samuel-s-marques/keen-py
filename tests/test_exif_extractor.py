import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.core.result_builder import NodeFactory
from src.modules.analysis.exif_extractor import ExifExtractor

TEST_DIR = os.path.expanduser("~/.keen_test_exif_extractor_tmp")
SHA256 = "d" * 64


class FakeRatio:
    def __init__(self, num, den=1):
        self.num = num
        self.den = den


class FakeTag:
    def __init__(self, printable, values=None):
        self._printable = printable
        self.values = values or []

    def __str__(self):
        return self._printable


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


def _seed_media_node(ws: WorkspaceManager, attachment_ref: str, media_type="image"):
    node = NodeFactory.media(
        SHA256,
        media_type=media_type,
        original_filename="photo.jpg",
        size_bytes=123,
        attachment_ref=attachment_ref,
    )
    ws.get_or_add_node(node["type"], node["value"], node["metadata"])
    dest_dir = os.path.dirname(os.path.join(ws.attachments_dir(), attachment_ref))
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(ws.attachments_dir(), attachment_ref), "wb") as f:
        f.write(b"placeholder-bytes")


def test_convert_gps_north_east_is_positive():
    lat_tag = FakeTag("37,46,30", values=[FakeRatio(37), FakeRatio(46), FakeRatio(30)])
    ref = FakeTag("N")
    result = ExifExtractor._convert_gps(lat_tag, ref)
    assert result == pytest.approx(37.775, abs=1e-3)


def test_convert_gps_south_west_is_negative():
    lon_tag = FakeTag("122,25,0", values=[FakeRatio(122), FakeRatio(25), FakeRatio(0)])
    ref = FakeTag("W")
    result = ExifExtractor._convert_gps(lon_tag, ref)
    assert result == pytest.approx(-122.41666, abs=1e-3)


def test_convert_gps_missing_tag_returns_none():
    assert ExifExtractor._convert_gps(None, FakeTag("N")) is None


def test_parse_exif_tags_extracts_camera_and_gps():
    raw_tags = {
        "Image Make": FakeTag("Canon"),
        "Image Model": FakeTag("EOS 5D"),
        "EXIF DateTimeOriginal": FakeTag("2026:01:15 10:30:00"),
        "GPS GPSLatitude": FakeTag(
            "37,46,30", values=[FakeRatio(37), FakeRatio(46), FakeRatio(30)]
        ),
        "GPS GPSLatitudeRef": FakeTag("N"),
        "GPS GPSLongitude": FakeTag(
            "122,25,0", values=[FakeRatio(122), FakeRatio(25), FakeRatio(0)]
        ),
        "GPS GPSLongitudeRef": FakeTag("W"),
    }
    parsed = ExifExtractor._parse_exif_tags(raw_tags)
    assert parsed["camera_make"] == "Canon"
    assert parsed["camera_model"] == "EOS 5D"
    assert parsed["captured_at"] == "2026:01:15 10:30:00"
    assert parsed["latitude"] == pytest.approx(37.775, abs=1e-3)
    assert parsed["longitude"] == pytest.approx(-122.41666, abs=1e-3)


def test_parse_exif_tags_empty_without_relevant_tags():
    assert ExifExtractor._parse_exif_tags({}) == {}


@pytest.mark.asyncio
async def test_execute_ingests_camera_and_location_nodes(monkeypatch):
    ws, config = _make_workspace()
    try:
        _seed_media_node(ws, "images/d.jpg")

        module = ExifExtractor()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", SHA256)

        def fake_read(self, file_path):
            return {
                "camera_make": "Canon",
                "camera_model": "EOS 5D",
                "captured_at": "2026:01:15 10:30:00",
                "latitude": 37.775,
                "longitude": -122.41666,
            }

        monkeypatch.setattr(ExifExtractor, "_read_exif_tags", fake_read)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        types = {n["type"] for n in nodes}
        assert "x-camera-model" in types
        assert "location" in types

        cursor.execute("SELECT relationship FROM edge")
        relationships = {row["relationship"] for row in cursor.fetchall()}
        assert "captured-with" in relationships
        assert "depicts-location" in relationships

        media_meta = ws.get_node_metadata(SHA256)
        assert media_meta is not None
        assert media_meta["captured_at"] == "2026:01:15 10:30:00"
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_skips_non_image_media():
    ws, config = _make_workspace()
    try:
        _seed_media_node(ws, "documents/d.pdf", media_type="document")

        module = ExifExtractor()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", SHA256)

        await module.run()

        assert ws.get_edge_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_errors_on_unknown_media_node():
    ws, config = _make_workspace()
    try:
        module = ExifExtractor()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "e" * 64)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)
