import hashlib
import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager
from src.core.media_import import classify_media_extension as _classify_media_extension
from src.core.media_import import import_media_file

TEST_DIR = os.path.expanduser("~/.keen_test_media_import_tmp")


def _make_workspace(name: str) -> WorkspaceManager:
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    return WorkspaceManager(os.path.join(TEST_DIR, f"{name}.keen"), name=name)


def test_classify_media_extension():
    assert _classify_media_extension(".JPG") == "image"
    assert _classify_media_extension("mp3") == "audio"
    assert _classify_media_extension("mp4") == "video"
    assert _classify_media_extension("pdf") == "document"


def test_import_media_file_creates_media_node_and_attachment():
    ws = _make_workspace("import_basic")
    try:
        src_path = os.path.join(TEST_DIR, "avatar.jpg")
        data = b"fake-jpeg-bytes"
        with open(src_path, "wb") as f:
            f.write(data)

        node_id = import_media_file(ws, src_path)
        assert node_id is not None

        expected_hash = hashlib.sha256(data).hexdigest()
        cursor = ws.conn.cursor()
        cursor.execute(
            "SELECT type, value, metadata FROM nodes WHERE id = ?", (node_id,)
        )
        row = cursor.fetchone()
        assert row["type"] == "media"
        assert row["value"] == expected_hash

        import json

        meta = json.loads(row["metadata"])
        assert meta["media_type"] == "image"
        assert meta["stix2"]["name"] == "avatar.jpg"

        attachment_path = os.path.join(
            ws.attachments_dir("images"), f"{expected_hash}.jpg"
        )
        assert os.path.exists(attachment_path)
        with open(attachment_path, "rb") as f:
            assert f.read() == data

        entries = ws.get_ledger_entries()
        assert any(e["action"] == "media_import" for e in entries)
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_import_media_file_dedupes_identical_content():
    ws = _make_workspace("import_dedup")
    try:
        data = b"same-bytes-twice"
        path_a = os.path.join(TEST_DIR, "one.png")
        path_b = os.path.join(TEST_DIR, "two.png")
        for p in (path_a, path_b):
            with open(p, "wb") as f:
                f.write(data)

        id_a = import_media_file(ws, path_a)
        id_b = import_media_file(ws, path_b)

        assert id_a == id_b
        assert ws.get_node_count() == 1
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_import_media_file_missing_path_returns_none():
    ws = _make_workspace("import_missing")
    try:
        assert (
            import_media_file(ws, os.path.join(TEST_DIR, "does_not_exist.jpg")) is None
        )
        assert ws.get_node_count() == 0
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)
