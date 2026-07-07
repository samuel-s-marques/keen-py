import os
import sys
import asyncio
import shutil

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager
from src.modules.helpers.url_to_domain import UrlToDomain


class MockShell:
    def __init__(self, workspace):
        self._workspace = workspace

    @property
    def workspace(self):
        return self._workspace


async def run_test():
    print("=== Testing UrlToDomain Module Ingestion ===")
    test_db_dir = os.path.expanduser("~/.keen_test_url_helper")
    if os.path.exists(test_db_dir):
        try:
            shutil.rmtree(test_db_dir)
        except OSError:
            pass
    os.makedirs(test_db_dir, exist_ok=True)

    ws_db_path = os.path.join(test_db_dir, "test_workspace.keen")
    ws = WorkspaceManager(ws_db_path, name="TestWorkspace")

    # Instantiate module
    module = UrlToDomain()
    module.shell = MockShell(ws)

    # Set options
    target_url = "https://example.com/some/path?param=1"
    module.set_option("TARGET", target_url)

    # Run the module
    await module.run()

    # Verify nodes and edges in workspace
    node_count = ws.get_node_count()
    edge_count = ws.get_edge_count()

    print(f"Nodes in workspace: {node_count}")
    print(f"Edges in workspace: {edge_count}")

    # Fetch nodes to check types and values
    cursor = ws.conn.cursor()
    cursor.execute("SELECT type, value, metadata FROM nodes")
    nodes = [dict(row) for row in cursor.fetchall()]

    for node in nodes:
        print(
            f"Node - Type: {node['type']}, Value: {node['value']}, Metadata: {node['metadata']}"
        )

    cursor.execute("SELECT source_id, target_id, relationship FROM edge")
    edges = [dict(row) for row in cursor.fetchall()]
    for edge in edges:
        print(
            f"Edge - Source ID: {edge['source_id']}, Target ID: {edge['target_id']}, Relationship: {edge['relationship']}"
        )

    assert node_count == 2, f"Expected 2 nodes, got {node_count}"
    assert edge_count == 1, f"Expected 1 edge, got {edge_count}"

    # Clean up
    ws.conn.close()
    try:
        shutil.rmtree(test_db_dir)
    except OSError:
        pass
    print("\n[OK] UrlToDomain module results successfully verified in the database!")


if __name__ == "__main__":
    asyncio.run(run_test())
