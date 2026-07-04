import os
import shutil
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager, WorkspaceManager


def test_managers():
    print("=== Testing Database Engine & Path Expansion ===")
    test_db_dir = os.path.expanduser("~/.keen_test_tmp")
    if os.path.exists(test_db_dir):
        shutil.rmtree(test_db_dir)
        
    config_db_path = "~/.keen_test_tmp/config.db"
    config = ConfigManager(config_db_path)
    
    # Check that it actually resolved and created the directory
    resolved_path = os.path.abspath(os.path.expanduser(config_db_path))
    assert os.path.exists(resolved_path), "Database file was not created at resolved path"
    print("[OK] Path expansion and directory creation verified successfully!")

    print("\n=== Testing ConfigManager API Keys & Preferences ===")
    # Unlock key manager first
    config.unlock("test_password")
    # Test api keys
    config.set_api_key("test_service", "super_secret_key_123")
    assert config.get_api_key("test_service") == "super_secret_key_123"
    
    all_keys = config.get_all_api_keys()
    assert len(all_keys) == 1
    assert all_keys[0]["service"] == "test_service"
    
    config.delete_api_key("test_service")
    assert config.get_api_key("test_service") is None
    print("[OK] API Keys CRUD works perfectly!")

    # Test preferences
    config.set_preference("last_workspace", "demo_workspace")
    assert config.get_preference("last_workspace") == "demo_workspace"
    
    config.set_preference("last_workspace", "another_one")
    assert config.get_preference("last_workspace") == "another_one"
    print("[OK] Preferences get/set works perfectly!")

    print("\n=== Testing ConfigManager Workspaces Registry ===")
    config.add_workspace("demo", "cases/demo.keen", "A temporary demo workspace")
    w = config.get_workspace("demo")
    assert w is not None
    assert w["name"] == "demo"
    assert w["description"] == "A temporary demo workspace"
    
    # Update description
    config.update_workspace_description("demo", "An updated workspace description")
    w_updated = config.get_workspace("demo")
    assert w_updated["description"] == "An updated workspace description"
    
    all_ws = config.get_all_workspaces()
    assert len(all_ws) == 1
    assert all_ws[0]["name"] == "demo"
    
    config.delete_workspace("demo")
    assert config.get_workspace("demo") is None
    print("[OK] Workspace Registry CRUD works perfectly!")

    print("\n=== Testing WorkspaceManager (Bug Fixes & Metrics) ===")
    ws_db_path = os.path.join(test_db_dir, "test_workspace.keen")
    ws = WorkspaceManager(ws_db_path, name="TestWorkspace")
    
    assert ws.name == "TestWorkspace", f"Expected TestWorkspace, got {ws.name}"
    assert ws.get_node_count() == 0
    assert ws.get_edge_count() == 0
    
    # Test critical bug fix: string value query
    node_id = ws.get_or_add_node("Domain", "example.com", {"owner": "Alice"})
    assert node_id is not None
    print(f"[OK] Created node ID: {node_id}")
    
    # Test getting same node again (should return same ID and not fail with SQL binding error!)
    node_id_dup = ws.get_or_add_node("Domain", "example.com", {"owner": "Alice"})
    assert node_id == node_id_dup, f"Expected same ID {node_id}, got {node_id_dup}"
    print("[OK] Critical SQL tuple-binding bug verified as FIXED!")

    # Add another node and an edge
    node2_id = ws.get_or_add_node("IP", "93.184.216.34")
    ws.add_edge(node_id, node2_id, "resolves_to")
    
    assert ws.get_node_count() == 2
    assert ws.get_edge_count() == 1
    print("[OK] Node & edge counters work perfectly!")
    
    # Clean up
    ws.conn.close()
    config.conn.close()
    shutil.rmtree(test_db_dir)
    print("\nALL TESTS PASSED SUCCESSFULLY! The improved ConfigManager and WorkspaceManager are rock solid.")


if __name__ == "__main__":
    try:
        test_managers()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
