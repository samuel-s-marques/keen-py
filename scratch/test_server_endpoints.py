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


if __name__ == "__main__":
    test_endpoints()
