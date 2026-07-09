import os
import sys
import asyncio
import shutil

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager
from src.modules.helpers.phone_to_country import PhoneToCountry


class MockShell:
    def __init__(self, workspace):
        self._workspace = workspace

    @property
    def workspace(self):
        return self._workspace


async def run_test():
    print("=== Testing PhoneToCountry Module Ingestion ===")
    test_db_dir = os.path.expanduser("~/.keen_test_phone_to_country")
    if os.path.exists(test_db_dir):
        try:
            shutil.rmtree(test_db_dir)
        except OSError:
            pass
    os.makedirs(test_db_dir, exist_ok=True)

    ws_db_path = os.path.join(test_db_dir, "test_workspace.keen")
    ws = WorkspaceManager(ws_db_path, name="TestWorkspace")

    module = PhoneToCountry()
    module.shell = MockShell(ws)
    module.set_option("TARGET", "+14157120049")

    await module.run()

    node_count = ws.get_node_count()
    edge_count = ws.get_edge_count()
    print(f"Nodes in workspace: {node_count}")
    print(f"Edges in workspace: {edge_count}")

    cursor = ws.conn.cursor()
    cursor.execute("SELECT type, value FROM nodes")
    nodes = [dict(row) for row in cursor.fetchall()]
    for node in nodes:
        print(f"Node - Type: {node['type']}, Value: {node['value']}")

    node_values = {n["value"] for n in nodes}
    assert "+14157120049" in node_values, "Phone node missing"
    assert node_count == 2, f"Expected 2 nodes, got {node_count}"
    assert edge_count == 1, f"Expected 1 edge, got {edge_count}"

    ws.conn.close()
    try:
        shutil.rmtree(test_db_dir)
    except OSError:
        pass

    print("\n[OK] PhoneToCountry module results successfully verified in the database!")


if __name__ == "__main__":
    asyncio.run(run_test())
