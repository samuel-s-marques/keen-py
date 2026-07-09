import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager

TEST_DIR = os.path.expanduser("~/.keen_test_merge_tmp")


def _make_workspace(name: str) -> WorkspaceManager:
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    return WorkspaceManager(os.path.join(TEST_DIR, f"{name}.keen"), name=name)


def test_merge_repoints_edges_and_removes_absorbed_node():
    ws = _make_workspace("merge_basic")
    try:
        canonical = ws.get_or_add_node("person", "John Doe", {"title": "Engineer"})
        absorbed = ws.get_or_add_node("user-account", "jdoe_x", {"platform": "X"})
        other = ws.get_or_add_node("organization", "Acme Corp")

        ws.add_edge(absorbed, other, "works-at")

        assert ws.merge_nodes(canonical, [absorbed]) is True

        # Absorbed node is gone.
        assert ws.get_node_id("jdoe_x") is None

        # Its edge now points from the canonical node instead.
        cursor = ws.conn.cursor()
        cursor.execute("SELECT source_id, target_id FROM edge")
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["source_id"] == canonical
        assert rows[0]["target_id"] == other
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_merge_unions_metadata_with_lineage():
    ws = _make_workspace("merge_metadata")
    try:
        canonical = ws.get_or_add_node("person", "Jane Doe", {"title": "CPO"})
        absorbed = ws.get_or_add_node(
            "person", "jane_linkedin", {"company": "New York Times"}
        )

        ws.merge_nodes(canonical, [absorbed])

        cursor = ws.conn.cursor()
        cursor.execute("SELECT metadata FROM nodes WHERE id = ?", (canonical,))
        import json

        meta = json.loads(cursor.fetchone()["metadata"])
        assert meta["title"] == "CPO"
        assert meta["company"] == "New York Times"
        assert meta["merged_from"] == ["jane_linkedin"]
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_merge_never_creates_self_loop_or_duplicate_edge():
    ws = _make_workspace("merge_dedup")
    try:
        canonical = ws.get_or_add_node("person", "A")
        absorbed = ws.get_or_add_node("person", "B")
        shared_neighbor = ws.get_or_add_node("organization", "Shared Org")

        # Both A and B already point at the same neighbor with the same
        # relationship -- after the merge this would otherwise duplicate.
        ws.add_edge(canonical, shared_neighbor, "works-at")
        ws.add_edge(absorbed, shared_neighbor, "works-at")
        # A also already connects directly to B -- this becomes a self-loop.
        ws.add_edge(canonical, absorbed, "knows")

        ws.merge_nodes(canonical, [absorbed])

        cursor = ws.conn.cursor()
        cursor.execute("SELECT source_id, target_id, relationship FROM edge")
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["source_id"] == canonical
        assert rows[0]["target_id"] == shared_neighbor
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_merge_logs_a_provenance_ledger_entry():
    ws = _make_workspace("merge_ledger")
    try:
        canonical = ws.get_or_add_node("person", "A")
        absorbed = ws.get_or_add_node("person", "B")

        ws.merge_nodes(canonical, [absorbed], actor="analyst@example.com")

        entries = ws.get_ledger_entries()
        assert len(entries) == 1
        assert entries[0]["action"] == "merge_nodes"
        assert entries[0]["actor"] == "analyst@example.com"
        assert ws.verify_ledger_integrity() is True
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_merge_with_no_valid_absorbed_ids_returns_false():
    ws = _make_workspace("merge_noop")
    try:
        canonical = ws.get_or_add_node("person", "A")
        assert ws.merge_nodes(canonical, [9999]) is False
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


if __name__ == "__main__":
    test_merge_repoints_edges_and_removes_absorbed_node()
    test_merge_unions_metadata_with_lineage()
    test_merge_never_creates_self_loop_or_duplicate_edge()
    test_merge_logs_a_provenance_ledger_entry()
    test_merge_with_no_valid_absorbed_ids_returns_false()
    print("ALL MERGE TESTS PASSED!")
