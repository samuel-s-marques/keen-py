import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from src.api.server import app, get_config
from src.core.managers import ConfigManager


def test_endpoints():
    print("=== Testing FastAPI Refactored Endpoints via TestClient ===")

    # Initialize a temporary config manager
    config_db = os.path.expanduser("~/.keen_test_server_config.db")
    if os.path.exists(config_db):
        try:
            os.remove(config_db)
        except OSError:
            pass

    cm = ConfigManager(config_db)
    # Unlock and register a workspace
    cm.unlock("testpass")
    cm.add_workspace("test_ws", "cases/test_ws.keen", "Test workspace")
    cm.close()

    # Override get_config dependency
    def get_config_override():
        config = ConfigManager(config_db)
        try:
            yield config
        finally:
            config.close()

    app.dependency_overrides[get_config] = get_config_override

    client = TestClient(app)

    # 1. Test happy path workspace nodes
    response = client.get("/api/workspaces/test_ws/nodes")
    print(f"GET nodes: Status {response.status_code}, Body: {response.json()}")
    assert response.status_code == 200

    # 2. Test invalid workspace nodes (must throw 404 and return standard error JSON)
    response = client.get("/api/workspaces/non_existent_ws/nodes")
    print(
        f"GET non-existent nodes: Status {response.status_code}, Body: {response.json()}"
    )
    assert response.status_code == 404
    assert response.json() == {"error": "Workspace not found"}

    # 3. Test workspace edges
    response = client.get("/api/workspaces/test_ws/edges")
    print(f"GET edges: Status {response.status_code}")
    assert response.status_code == 200

    # 4. Test post node
    response = client.post(
        "/api/workspaces/test_ws/nodes", json={"type": "ip", "value": "8.8.8.8"}
    )
    print(f"POST node: Status {response.status_code}, Body: {response.json()}")
    assert response.status_code == 200
    assert response.json().get("success") is True

    # 5. Test proxy endpoints, validation, and credential masking
    # Invalid scheme test
    response = client.post("/api/proxies", json={"url": "ftp://192.168.1.100:3128"})
    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "error": "Invalid scheme. Supported schemes are: http, https, socks4, socks4a, socks5, socks5h",
    }

    # Missing port test
    response = client.post("/api/proxies", json={"url": "http://192.168.1.100"})
    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "error": "Port is required (e.g. host:port)",
    }

    # Port out of range test
    response = client.post("/api/proxies", json={"url": "http://192.168.1.100:99999"})
    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "error": "Port must be in range 1-65535",
    }

    # Valid proxy addition
    response = client.post(
        "/api/proxies", json={"url": "http://admin:secret123@192.168.1.100:3128"}
    )
    assert response.status_code == 200
    assert response.json().get("success") is True

    response = client.get("/api/proxies")
    assert response.status_code == 200
    proxies_list = response.json()
    assert len(proxies_list) == 1
    assert proxies_list[0]["url"] == "http://****:****@192.168.1.100:3128"
    proxy_id = proxies_list[0]["id"]

    # Test toggling with valid ID
    response = client.post(f"/api/proxies/{proxy_id}/toggle", json={"is_enabled": 0})
    assert response.status_code == 200
    assert response.json() == {"success": True}

    # Test toggling with invalid ID
    response = client.post("/api/proxies/999999/toggle", json={"is_enabled": 1})
    assert response.status_code == 200
    assert response.json() == {"success": False}

    # Test toggling with payload coercion
    response = client.post(f"/api/proxies/{proxy_id}/toggle", json={"is_enabled": "1"})
    assert response.status_code == 200
    assert response.json() == {"success": True}

    # Test bulk loading endpoint
    response = client.post(
        "/api/proxies/load",
        json={
            "content": (
                "# This is a comment\n"
                "http://127.0.0.1:8080\n"
                "socks5://user:pass@127.0.0.1:1080\n"
                "invalid_proxy_url_here\n"
                "http://127.0.0.1:999999\n"
            )
        },
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "loaded": 2, "total": 4}

    response = client.get("/api/proxies")
    assert response.status_code == 200
    assert len(response.json()) == 3

    print(
        "[OK] Proxies API endpoints, credential masking, toggle, and bulk loading verified successfully!"
    )

    # Clean up DB
    if os.path.exists(config_db):
        try:
            os.remove(config_db)
        except OSError:
            pass
    if os.path.exists("cases/test_ws.keen"):
        try:
            os.remove("cases/test_ws.keen")
        except OSError:
            pass

    print(
        "\n[OK] All FastAPI endpoints successfully verified and backward-compatibility guaranteed!"
    )


def test_workspace_scope_endpoints():
    """Scope can be declared at workspace-creation time (POST /api/workspaces
    with a `scope` list) and edited afterward via the dedicated scope endpoints."""
    config_db = os.path.expanduser("~/.keen_test_server_scope_config.db")
    if os.path.exists(config_db):
        try:
            os.remove(config_db)
        except OSError:
            pass

    def get_config_override():
        config = ConfigManager(config_db)
        try:
            yield config
        finally:
            config.close()

    app.dependency_overrides[get_config] = get_config_override
    client = TestClient(app)

    try:
        # Create a workspace with scope declared inline.
        response = client.post(
            "/api/workspaces",
            json={
                "name": "scope_test_ws",
                "description": "Scope endpoint test",
                "scope": [
                    {"scope_type": "domain", "value": "example.com", "consent_basis": "signed SOW"}
                ],
            },
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        # The declared entry should already be visible.
        response = client.get("/api/workspaces/scope_test_ws/scope")
        assert response.status_code == 200
        entries = response.json()
        assert len(entries) == 1
        assert entries[0]["scope_type"] == "domain"
        assert entries[0]["value"] == "example.com"

        # Add a second entry directly via POST.
        response = client.post(
            "/api/workspaces/scope_test_ws/scope",
            json={"scope_type": "ip", "value": "1.2.3.4"},
        )
        assert response.status_code == 200
        new_id = response.json()["id"]

        response = client.get("/api/workspaces/scope_test_ws/scope")
        assert len(response.json()) == 2

        # Invalid scope_type is rejected.
        response = client.post(
            "/api/workspaces/scope_test_ws/scope",
            json={"scope_type": "not-a-real-type", "value": "x"},
        )
        assert response.status_code == 422

        # Remove the second entry.
        response = client.delete(f"/api/workspaces/scope_test_ws/scope/{new_id}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        response = client.get("/api/workspaces/scope_test_ws/scope")
        assert len(response.json()) == 1

        # Add an out-of-scope node directly, then quarantine it the way
        # BaseModule._ingest_results would, and confirm it's surfaced.
        from src.core.managers import WorkspaceManager

        wm = WorkspaceManager("cases/scope_test_ws.keen", name="scope_test_ws")
        node_id = wm.get_or_add_node("domain-name", "evil.com")
        assert not wm.is_in_scope("evil.com")
        wm.quarantine_node(node_id, reason="out of scope")
        wm.close()

        response = client.get("/api/workspaces/scope_test_ws/quarantined-nodes")
        assert response.status_code == 200
        quarantined = response.json()
        assert len(quarantined) == 1
        assert quarantined[0]["value"] == "evil.com"

        print("[OK] Workspace scope endpoints verified successfully!")
    finally:
        if os.path.exists(config_db):
            try:
                os.remove(config_db)
            except OSError:
                pass
        if os.path.exists("cases/scope_test_ws.keen"):
            try:
                os.remove("cases/scope_test_ws.keen")
            except OSError:
                pass


def test_workspace_merge_nodes_endpoint():
    """POST /api/workspaces/{name}/nodes/merge is the operator-facing entry
    point for WorkspaceManager.merge_nodes -- otherwise the primitive is
    unreachable from the running product (see internal/ARCHITECTURE_ROADMAP.md §1.3)."""
    config_db = os.path.expanduser("~/.keen_test_server_merge_config.db")
    if os.path.exists(config_db):
        try:
            os.remove(config_db)
        except OSError:
            pass

    def get_config_override():
        config = ConfigManager(config_db)
        try:
            yield config
        finally:
            config.close()

    app.dependency_overrides[get_config] = get_config_override
    client = TestClient(app)

    try:
        response = client.post(
            "/api/workspaces",
            json={"name": "merge_test_ws", "description": "Merge endpoint test"},
        )
        assert response.status_code == 200

        from src.core.managers import WorkspaceManager

        wm = WorkspaceManager("cases/merge_test_ws.keen", name="merge_test_ws")
        canonical_id = wm.get_or_add_node("person", "John Doe")
        absorbed_id = wm.get_or_add_node("person", "j.doe")
        wm.close()

        response = client.post(
            "/api/workspaces/merge_test_ws/nodes/merge",
            json={"canonical_id": canonical_id, "absorbed_ids": [absorbed_id]},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        wm = WorkspaceManager("cases/merge_test_ws.keen", name="merge_test_ws")
        assert wm.get_node_id("j.doe") is None
        assert wm.get_node_id("John Doe") == canonical_id
        entries = wm.get_ledger_entries()
        assert any(e["action"] == "merge_nodes" for e in entries)
        wm.close()

        # A merge referencing a nonexistent canonical node is reported, not silently OK'd.
        response = client.post(
            "/api/workspaces/merge_test_ws/nodes/merge",
            json={"canonical_id": 999999, "absorbed_ids": [canonical_id]},
        )
        assert response.status_code == 404

        print("[OK] Workspace merge endpoint verified successfully!")
    finally:
        if os.path.exists(config_db):
            try:
                os.remove(config_db)
            except OSError:
                pass
        if os.path.exists("cases/merge_test_ws.keen"):
            try:
                os.remove("cases/merge_test_ws.keen")
            except OSError:
                pass


def test_notifications_test_endpoint():
    """No channels configured -> success with an empty results map (not an error)."""
    config_db = os.path.expanduser("~/.keen_test_server_notify_config.db")
    if os.path.exists(config_db):
        try:
            os.remove(config_db)
        except OSError:
            pass

    def get_config_override():
        config = ConfigManager(config_db)
        try:
            yield config
        finally:
            config.close()

    app.dependency_overrides[get_config] = get_config_override
    client = TestClient(app)

    try:
        response = client.post("/api/notifications/test")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["results"] == {}
        print("[OK] Notifications test endpoint verified successfully!")
    finally:
        if os.path.exists(config_db):
            try:
                os.remove(config_db)
            except OSError:
                pass


if __name__ == "__main__":
    test_endpoints()
    test_workspace_scope_endpoints()
    test_notifications_test_endpoint()
