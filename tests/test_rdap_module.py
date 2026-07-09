import os
import shutil
import sys
import asyncio

import pytest

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager
from src.modules.discovery.whois_module import WhoisModule
from src.utils.rdap import query_rdap


class MockShell:
    def __init__(self, workspace):
        self.workspace = workspace


@pytest.mark.skip(reason="live network call against google.com's real RDAP endpoint — unsuitable for CI")
async def test_rdap_direct():
    print("=== Testing Direct RDAP Query ===")
    domain = "google.com"
    data = await query_rdap(domain)
    assert data is not None, "Failed to retrieve RDAP data"
    print(f"Registrar: {data.get('registrar')}")
    print(f"Organization: {data.get('org')}")
    print(f"Creation Date: {data.get('creation_date')}")
    print(f"Expiration Date: {data.get('expiration_date')}")
    print(f"Name Servers: {data.get('name_servers')}")
    print(f"Emails: {data.get('emails')}")
    print(f"Status: {data.get('status')}")
    assert data.get('registrar') is not None, "Registrar should not be None"


@pytest.mark.skip(reason="live network call against google.com's real RDAP/WHOIS data — unsuitable for CI")
async def test_module_integration():
    print("\n=== Testing WhoisModule with RDAP Integration ===")
    
    # Setup temporary workspace
    test_db_dir = os.path.expanduser("~/.keen_rdap_test_tmp")
    if os.path.exists(test_db_dir):
        shutil.rmtree(test_db_dir)
    os.makedirs(test_db_dir, exist_ok=True)
    
    ws_db_path = os.path.join(test_db_dir, "test_ws.keen")
    ws = WorkspaceManager(ws_db_path, name="TestWorkspace")
    shell = MockShell(ws)
    
    # Instantiate the module
    module = WhoisModule()
    module.shell = shell
    
    # Configure option
    module.set_option("TARGET", "google.com")
    
    # Run the module
    await module.run()
    
    # Print the saved nodes and edges from the workspace DB
    print("\n=== Saved Workspace Nodes ===")
    cursor = ws.conn.cursor()
    cursor.execute("SELECT id, type, value, metadata FROM nodes")
    nodes = cursor.fetchall()
    for n in nodes:
        print(f"Node ID: {n[0]}, Type: {n[1]}, Value: {n[2]}")
        
    print("\n=== Saved Workspace Edges ===")
    cursor.execute("SELECT id, source_id, target_id, relationship FROM edge")
    edges = cursor.fetchall()
    for e in edges:
        # Resolve names for display
        cursor.execute("SELECT value FROM nodes WHERE id = ?", (e[1],))
        src = cursor.fetchone()[0]
        cursor.execute("SELECT value FROM nodes WHERE id = ?", (e[2],))
        tgt = cursor.fetchone()[0]
        print(f"Edge ID: {e[0]}, Source: {src}, Target: {tgt}, Relation: {e[3]}")
        
    # Assertions to verify correctness
    assert len(nodes) > 0, "No nodes were saved to the workspace"
    assert len(edges) > 0, "No edges were saved to the workspace"
    
    # Clean up
    ws.conn.close()
    shutil.rmtree(test_db_dir)
    print("\nRDAP integration test completed successfully! Everything functions perfectly.")


async def main():
    await test_rdap_direct()
    await test_module_integration()


if __name__ == "__main__":
    asyncio.run(main())
