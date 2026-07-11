import os
import shutil
import sys

import imagehash
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager
from src.core.media_import import import_media_file
from src.core.result_builder import NodeFactory
from src.modules.analysis.avatar_correlation import AvatarCorrelation

TEST_DIR = os.path.expanduser("~/.keen_test_avatar_correlation_tmp")

TARGET_SHA = "1" * 64
OTHER_SHA = "2" * 64
FAR_SHA = "3" * 64

HASH_A = "0000000000000000"
# Differs from HASH_A by exactly 3 bits -- well under a lenient threshold.
HASH_B = "0000000000000007"
# Differs from HASH_A by 32 bits (half the bits flipped) -- well over threshold.
HASH_FAR = "ffffffff00000000"


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


def _make_synthetic_image(path: str, size: tuple[int, int]) -> None:
    """Render a small synthetic photo-like image to disk.

    Flat-color squares hash identically regardless of content, so this draws
    a couple of shapes to give pHash's DCT step actual structure to work
    with -- good enough to stand in for a real photo without needing a
    committed binary fixture.
    """
    from PIL import Image, ImageDraw

    os.makedirs(os.path.dirname(path), exist_ok=True)
    w, h = size
    img = Image.new("RGB", size, color=(235, 235, 235))
    draw = ImageDraw.Draw(img)
    draw.rectangle([w * 0.1, h * 0.1, w * 0.6, h * 0.6], fill=(180, 60, 60))
    draw.ellipse([w * 0.3, h * 0.4, w * 0.9, h * 0.9], fill=(60, 60, 180))
    img.save(path)


def _seed_image_node(ws: WorkspaceManager, sha: str, phash: str | None = None, attachment_ref="images/x.jpg"):
    node = NodeFactory.media(
        sha, media_type="image", original_filename="x.jpg", attachment_ref=attachment_ref
    )
    if phash:
        node["metadata"]["phash"] = phash
    ws.get_or_add_node(node["type"], node["value"], node["metadata"])
    dest_dir = os.path.dirname(os.path.join(ws.attachments_dir(), attachment_ref))
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(ws.attachments_dir(), attachment_ref), "wb") as f:
        f.write(b"placeholder-bytes")


def test_real_hamming_distance_between_fixtures_is_expected():
    # Sanity check the fixtures actually encode the distances the test names claim.
    assert imagehash.hex_to_hash(HASH_A) - imagehash.hex_to_hash(HASH_B) == 3
    assert imagehash.hex_to_hash(HASH_A) - imagehash.hex_to_hash(HASH_FAR) == 32


def test_find_similar_returns_matches_under_threshold():
    ws, config = _make_workspace()
    try:
        _seed_image_node(ws, TARGET_SHA, phash=HASH_A)
        _seed_image_node(ws, OTHER_SHA, phash=HASH_B)
        _seed_image_node(ws, FAR_SHA, phash=HASH_FAR)

        matches = AvatarCorrelation._find_similar(ws, TARGET_SHA, HASH_A, max_distance=10)
        assert len(matches) == 1
        assert matches[0]["value"] == OTHER_SHA
        assert matches[0]["distance"] == 3
        assert matches[0]["confidence"] == pytest.approx(1 - 3 / 64, abs=1e-4)
    finally:
        _teardown(ws, config)


def test_find_similar_excludes_self():
    ws, config = _make_workspace()
    try:
        _seed_image_node(ws, TARGET_SHA, phash=HASH_A)
        matches = AvatarCorrelation._find_similar(ws, TARGET_SHA, HASH_A, max_distance=64)
        assert matches == []
    finally:
        _teardown(ws, config)


def test_find_similar_skips_non_image_media():
    ws, config = _make_workspace()
    try:
        _seed_image_node(ws, TARGET_SHA, phash=HASH_A)
        doc_node = NodeFactory.media(OTHER_SHA, media_type="document")
        doc_node["metadata"]["phash"] = HASH_B
        ws.get_or_add_node(doc_node["type"], doc_node["value"], doc_node["metadata"])

        matches = AvatarCorrelation._find_similar(ws, TARGET_SHA, HASH_A, max_distance=64)
        assert matches == []
    finally:
        _teardown(ws, config)


def test_find_similar_computes_missing_phash_on_the_fly():
    """Regression test: a comparison target with no stored pHash yet (this
    module was never run against it) must not be silently skipped -- its
    pHash should be computed from the attachment bytes on the spot, not
    treated as "no match" regardless of max_distance.
    """
    ws, config = _make_workspace()
    try:
        _seed_image_node(ws, TARGET_SHA, phash=HASH_A)
        # OTHER_SHA has no phash in metadata and a real image file on disk --
        # simulates a media node this module was never explicitly run on.
        _seed_image_node(
            ws, OTHER_SHA, phash=None, attachment_ref="images/other.png"
        )
        real_path = os.path.join(ws.attachments_dir(), "images/other.png")
        _make_synthetic_image(real_path, (128, 128))

        import imagehash
        from PIL import Image

        with Image.open(real_path) as img:
            expected_hash = str(imagehash.phash(img))

        matches = AvatarCorrelation._find_similar(
            ws, TARGET_SHA, HASH_A, max_distance=64
        )
        assert len(matches) == 1
        assert matches[0]["value"] == OTHER_SHA

        # The computed hash should now be persisted on OTHER_SHA's own metadata.
        meta = ws.get_node_metadata(OTHER_SHA)
        assert meta is not None
        assert meta["phash"] == expected_hash
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_detects_identical_images_regardless_of_run_order():
    """End-to-end regression test using two genuinely-identical images at
    different resolutions (one generated, one a resize of the same source)
    -- reproduces the reported bug: running this module against only ONE of
    two visually identical images must still surface the match, even though
    the other image's node was never separately correlated.
    """
    ws, config = _make_workspace()
    try:
        from PIL import Image

        large_path = os.path.join(TEST_DIR, "large.png")
        small_path = os.path.join(TEST_DIR, "small.png")
        _make_synthetic_image(large_path, (512, 512))
        # Same visual content as large_path, saved at a different resolution
        # -- distinct file bytes (and therefore a distinct SHA-256), which is
        # exactly what a perceptual hash should still match despite a real
        # cryptographic hash mismatch.
        with Image.open(large_path) as img:
            img.resize((128, 128)).save(small_path)

        large_id = import_media_file(ws, large_path)
        small_id = import_media_file(ws, small_path)
        assert large_id is not None
        assert small_id is not None
        assert large_id != small_id  # distinct content hashes, same visual image

        cursor = ws.conn.cursor()
        cursor.execute("SELECT value FROM nodes WHERE id = ?", (small_id,))
        small_sha = cursor.fetchone()["value"]

        module = AvatarCorrelation()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", small_sha)
        module.set_option("MAX_HAMMING_DISTANCE", "30")

        await module.run()

        cursor.execute(
            "SELECT relationship FROM edge WHERE relationship = 'visually-similar-to'"
        )
        assert len(cursor.fetchall()) == 1
    finally:
        _teardown(ws, config)


def test_store_phash_persists_to_node_metadata():
    ws, config = _make_workspace()
    try:
        _seed_image_node(ws, TARGET_SHA)
        AvatarCorrelation._store_phash(ws, TARGET_SHA, HASH_A)
        meta = ws.get_node_metadata(TARGET_SHA)
        assert meta is not None
        assert meta["phash"] == HASH_A
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_ingests_visually_similar_to_edge(monkeypatch):
    ws, config = _make_workspace()
    try:
        _seed_image_node(ws, TARGET_SHA)
        _seed_image_node(ws, OTHER_SHA, phash=HASH_B)

        module = AvatarCorrelation()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", TARGET_SHA)

        def fake_compute(self, file_path):
            return HASH_A

        monkeypatch.setattr(AvatarCorrelation, "_compute_phash", fake_compute)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute(
            "SELECT relationship, confidence FROM edge WHERE relationship = 'visually-similar-to'"
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["confidence"] == pytest.approx(1 - 3 / 64, abs=1e-4)

        # The target node's own phash should now be persisted too.
        meta = ws.get_node_metadata(TARGET_SHA)
        assert meta is not None
        assert meta["phash"] == HASH_A
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_skips_non_image_target():
    ws, config = _make_workspace()
    try:
        node = NodeFactory.media(TARGET_SHA, media_type="document")
        ws.get_or_add_node(node["type"], node["value"], node["metadata"])

        module = AvatarCorrelation()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", TARGET_SHA)

        await module.run()

        assert ws.get_edge_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_errors_on_unknown_media_node():
    ws, config = _make_workspace()
    try:
        module = AvatarCorrelation()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", "9" * 64)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)
