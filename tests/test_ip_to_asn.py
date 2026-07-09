import os
import sys
import asyncio
import shutil

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager
import src.modules.helpers.ip_to_asn as ip_to_asn_module
from src.modules.helpers.ip_to_asn import IpToAsn


class MockShell:
    def __init__(self, workspace):
        self._workspace = workspace

    @property
    def workspace(self):
        return self._workspace


async def mock_lookup_asn(ip: str):
    return {
        "ip": ip,
        "asn": "15169",
        "prefix": "8.8.8.0/24",
        "country": "US",
        "provider": "GOOGLE, US",
    }


async def run_test():
    print("=== Testing IpToAsn Module Ingestion ===")
    test_db_dir = os.path.expanduser("~/.keen_test_ip_to_asn")
    if os.path.exists(test_db_dir):
        try:
            shutil.rmtree(test_db_dir)
        except OSError:
            pass
    os.makedirs(test_db_dir, exist_ok=True)

    ws_db_path = os.path.join(test_db_dir, "test_workspace.keen")
    ws = WorkspaceManager(ws_db_path, name="TestWorkspace")

    # Avoid a real DNS query against Team Cymru.
    original_lookup = ip_to_asn_module.lookup_asn
    ip_to_asn_module.lookup_asn = mock_lookup_asn

    try:
        module = IpToAsn()
        module.shell = MockShell(ws)
        module.set_option("TARGET", "8.8.8.8")

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
        assert "8.8.8.8" in node_values, "IP node missing"
        assert "AS15169" in node_values, "ASN node missing"
        assert "US" in node_values, "Country node missing"
        assert node_count == 3, f"Expected 3 nodes, got {node_count}"
        assert edge_count == 2, f"Expected 2 edges, got {edge_count}"
    finally:
        ip_to_asn_module.lookup_asn = original_lookup
        ws.conn.close()
        try:
            shutil.rmtree(test_db_dir)
        except OSError:
            pass

    print("\n[OK] IpToAsn module results successfully verified in the database!")


if __name__ == "__main__":
    asyncio.run(run_test())
