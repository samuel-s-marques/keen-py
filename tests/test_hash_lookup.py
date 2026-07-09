import os
import sys
import asyncio
import shutil

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager
from src.modules.helpers.hash_lookup import HashLookup


class MockShell:
    def __init__(self, workspace):
        self._workspace = workspace

    @property
    def workspace(self):
        return self._workspace


async def run_test():
    print("=== Testing HashLookup Module Ingestion ===")
    test_db_dir = os.path.expanduser("~/.keen_test_hash_lookup")
    if os.path.exists(test_db_dir):
        try:
            shutil.rmtree(test_db_dir)
        except OSError:
            pass
    os.makedirs(test_db_dir, exist_ok=True)

    ws_db_path = os.path.join(test_db_dir, "test_workspace.keen")
    ws = WorkspaceManager(ws_db_path, name="TestWorkspace")

    md5_hash = "d41d8cd98f00b204e9800998ecf8427e"

    module = HashLookup()
    module.shell = MockShell(ws)
    module.set_option("TARGET", md5_hash)

    await module.run()

    node_count = ws.get_node_count()
    print(f"Nodes in workspace: {node_count}")

    cursor = ws.conn.cursor()
    cursor.execute("SELECT type, value, metadata FROM nodes")
    nodes = [dict(row) for row in cursor.fetchall()]
    for node in nodes:
        print(f"Node - Type: {node['type']}, Value: {node['value']}")

    assert node_count == 1, f"Expected 1 node, got {node_count}"
    assert nodes[0]["value"] == md5_hash
    assert nodes[0]["type"] == "x-hash"
    assert "MD5" in nodes[0]["metadata"]

    ws.conn.close()
    try:
        shutil.rmtree(test_db_dir)
    except OSError:
        pass

    print("\n[OK] HashLookup module results successfully verified in the database!")


if __name__ == "__main__":
    asyncio.run(run_test())
