import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager
from src.core.timestamp_analysis import (
    MAX_CLUSTER_SIZE_FOR_EDGES,
    find_hour_of_day_clusters,
    parse_timestamp,
    run_timestamp_clustering,
)

TEST_DIR = os.path.expanduser("~/.keen_test_timestamp_analysis_tmp")


def _make_workspace(name: str) -> WorkspaceManager:
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    return WorkspaceManager(os.path.join(TEST_DIR, f"{name}.keen"), name=name)


def test_parse_timestamp_handles_exif_format():
    dt = parse_timestamp("2026:01:15 03:30:00")
    assert dt is not None
    assert dt.hour == 3


def test_parse_timestamp_handles_iso_format():
    dt = parse_timestamp("2026-01-15T03:30:00")
    assert dt is not None
    assert dt.hour == 3


def test_parse_timestamp_returns_none_for_garbage():
    assert parse_timestamp("not-a-timestamp") is None


def test_find_hour_of_day_clusters_groups_same_hour_across_dates():
    ws = _make_workspace("clusters_basic")
    try:
        ws.get_or_add_node("media", "img-a", {"captured_at": "2026:01:01 03:15:00"})
        ws.get_or_add_node("media", "img-b", {"captured_at": "2026:06:10 03:50:00"})
        # Different hour -- shouldn't join the 3am cluster.
        ws.get_or_add_node("media", "img-c", {"captured_at": "2026:03:01 14:00:00"})
        # No captured_at at all -- ignored, not an error.
        ws.get_or_add_node("domain-name", "example.com", {})

        clusters = find_hour_of_day_clusters(ws)
        assert len(clusters) == 1
        assert clusters[0]["hour_utc"] == 3
        assert clusters[0]["node_values"] == ["img-a", "img-b"]
        assert clusters[0]["count"] == 2
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_find_hour_of_day_clusters_ignores_singleton_hours():
    ws = _make_workspace("clusters_singleton")
    try:
        ws.get_or_add_node("media", "img-a", {"captured_at": "2026:01:01 03:15:00"})
        assert find_hour_of_day_clusters(ws) == []
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_run_timestamp_clustering_creates_confidence_scored_edges():
    ws = _make_workspace("clustering_edges")
    try:
        ws.get_or_add_node("media", "img-a", {"captured_at": "2026:01:01 03:15:00"})
        ws.get_or_add_node("media", "img-b", {"captured_at": "2026:06:10 03:50:00"})

        result = run_timestamp_clustering(ws)
        assert result["edges_created"] == 1
        assert result["skipped_oversized_clusters"] == 0

        cursor = ws.conn.cursor()
        cursor.execute(
            "SELECT relationship, confidence, metadata FROM edge "
            "WHERE relationship = 'temporally-correlated-with'"
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["confidence"] == 0.3

        import json

        meta = json.loads(rows[0]["metadata"])
        assert meta["hour_utc"] == 3
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_run_timestamp_clustering_without_edges_still_reports_clusters():
    ws = _make_workspace("clustering_no_edges")
    try:
        ws.get_or_add_node("media", "img-a", {"captured_at": "2026:01:01 03:15:00"})
        ws.get_or_add_node("media", "img-b", {"captured_at": "2026:06:10 03:50:00"})

        result = run_timestamp_clustering(ws, create_edges=False)
        assert result["edges_created"] == 0
        assert len(result["clusters"]) == 1
        assert ws.get_edge_count() == 0
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_run_timestamp_clustering_skips_oversized_clusters():
    ws = _make_workspace("clustering_oversized")
    try:
        for i in range(MAX_CLUSTER_SIZE_FOR_EDGES + 1):
            ws.get_or_add_node(
                "media", f"img-{i}", {"captured_at": f"2026:01:{(i % 27) + 1:02d} 05:00:00"}
            )

        result = run_timestamp_clustering(ws)
        assert result["edges_created"] == 0
        assert result["skipped_oversized_clusters"] == 1
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)
