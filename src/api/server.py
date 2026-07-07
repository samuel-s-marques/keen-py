import asyncio
import contextlib
import io
import json
import os
import re
from typing import Any, Dict, Generator, List, Optional, Union

import uvicorn
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

from src.core.loader import load_modules
from src.core.managers import ConfigManager, WorkspaceManager
from src.utils.config_util import get_valid_name

app = FastAPI(title="Keen API Web Server")

# Strong references to fire-and-forget background tasks
_BACKGROUND_TASKS: set = set()

PROXY_CREDENTIALS_RE = re.compile(r"^(https?|socks4|socks5)://([^/]+)@")
PROXY_VALIDATION_RE = re.compile(
    r"^(?P<scheme>https?|socks4|socks4a|socks5|socks5h)://"
    r"(?:[^/@:]+(?::[^/@:]+)?@)?"
    r"(?P<host>[^/:]+)"
    r":(?P<port>[0-9]+)$",
    re.IGNORECASE,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("web", exist_ok=True)


class WorkspaceCreate(BaseModel):
    name: str
    description: str = ""


class ModuleRunRequest(BaseModel):
    workspace_name: Optional[str] = None
    options: Dict[str, Any] = {}


class EdgeCreate(BaseModel):
    source_id: str
    target_id: str
    relationship: str
    metadata: Optional[Dict[str, Any]] = {}


class ConfigUnlock(BaseModel):
    password: str


class APIKeyCreate(BaseModel):
    service: str
    api_key: str


class WorkspaceRename(BaseModel):
    new_name: str


class ProxyCreate(BaseModel):
    url: str


class ProxyUpdate(BaseModel):
    url: Optional[str] = None
    is_enabled: Optional[bool] = None


class NodePositionsUpdate(BaseModel):
    positions: Dict[str, Dict[str, float]]


class NodeCreate(BaseModel):
    type: str
    value: str
    metadata: Optional[Dict[str, Any]] = {}


class NodeUpdate(BaseModel):
    type: Optional[str] = None
    value: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class EdgeUpdate(BaseModel):
    relationship: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class FeedbackSubmit(BaseModel):
    status: str
    feedback: Optional[str] = None


class AITestRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class SuggestionGenerateRequest(BaseModel):
    user_query: Optional[str] = None
    selected_nodes: Optional[List[Dict[str, Any]]] = None


class WebShellAdapter:
    def __init__(
        self, workspace: Optional[WorkspaceManager], config: ConfigManager
    ) -> None:
        self.workspace = workspace
        self.config = config
        self.is_web_context = True
        self._magic_running = False


class APIShellContext:
    def __init__(self, workspace: Optional[WorkspaceManager] = None) -> None:
        self.workspace = workspace


class QueueSink:
    def __init__(self, queue: asyncio.Queue) -> None:
        self.queue = queue

    def write(self, message: Any) -> None:
        try:
            self.queue.put_nowait(str(message))
        except Exception:
            pass


class QueueStdoutRedirector(io.TextIOBase):
    def __init__(self, queue: asyncio.Queue) -> None:
        self.queue = queue

    def write(self, text: str) -> int:
        if text.strip():
            try:
                self.queue.put_nowait(text)
            except Exception:
                pass
        return len(text)

    def flush(self) -> None:
        pass


def get_config() -> Generator[ConfigManager, None, None]:
    config = ConfigManager("~/.keen/config.db")
    try:
        yield config
    finally:
        config.close()


class WorkspaceNotFoundException(Exception):
    pass


@app.exception_handler(WorkspaceNotFoundException)
def workspace_not_found_handler(
    request: Request, exc: WorkspaceNotFoundException
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "Workspace not found"})


def get_workspace_manager(
    name: str, config: ConfigManager = Depends(get_config)
) -> Generator[WorkspaceManager, None, None]:
    w = config.get_workspace(name)
    if not w:
        raise WorkspaceNotFoundException()
    wm = WorkspaceManager(w["path"], name=name)
    try:
        yield wm
    finally:
        wm.close()


@app.get("/api")
def api() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/api/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/workspaces")
def get_workspaces(
    config: ConfigManager = Depends(get_config),
) -> List[Dict[str, Any]]:
    """Get all workspaces.

    Returns:
        List[Dict[str, Any]]: List of workspaces.
    """
    workspaces = config.get_all_workspaces()

    # Enrich with counts
    for w in workspaces:
        wm = None
        try:
            wm = WorkspaceManager(w["path"], name=w["name"])
            w["node_count"] = wm.get_node_count()
            w["edge_count"] = wm.get_edge_count()
        except Exception:
            w["node_count"] = 0
            w["edge_count"] = 0
        finally:
            if wm is not None:
                wm.close()

    return workspaces


@app.post("/api/workspaces", response_model=None)
def create_workspace(
    req: WorkspaceCreate, config: ConfigManager = Depends(get_config)
) -> Union[Dict[str, Any], JSONResponse]:
    """Create a new workspace.

    Args:
        req (WorkspaceCreate): Workspace to create.

    Returns:
        Dict[str, Any]: Workspace.
    """
    if not req.name.strip():
        return JSONResponse(status_code=400, content={"error": "Name is required"})

    name = req.name.strip()
    if not all(c.isalnum() or c in " _-" for c in name):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Workspace name must be alphanumeric (underscores/hyphens/spaces allowed)."
            },
        )

    filename = get_valid_name(name)

    db_file = f"cases/{filename}.keen"
    try:
        config.add_workspace(name, db_file, req.description or "")
    except ValueError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})
    return {"success": True, "name": name, "path": db_file}


@app.get("/api/workspaces/{name}/nodes", response_model=None)
def get_workspace_nodes(
    wm: WorkspaceManager = Depends(get_workspace_manager),
) -> Union[List[Dict[str, Any]], JSONResponse]:
    """Get all nodes in a workspace.

    Args:
        wm (WorkspaceManager): The active workspace manager dependency.

    Returns:
        Union[List[Dict[str, Any]], JSONResponse]: List of nodes in the workspace or a 500 JSONResponse on exception.
    """
    try:
        cursor = wm.conn.cursor()
        cursor.execute("SELECT * FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        for node in nodes:
            if node.get("metadata"):
                try:
                    node["metadata"] = json.loads(node["metadata"])
                except Exception:
                    pass

            # Provide both the original value (for display/uniqueness)
            # and a clean value (for module execution)
            from src.utils.utils import parse_node_prefix

            raw_value = node.get("value", "")
            prefix, clean = parse_node_prefix(raw_value)
            node["label"] = raw_value  # visual identifier (e.g. "github:username")
            node["clean_value"] = clean  # execution target  (e.g. "username")
            node["platform"] = prefix  # platform prefix   (e.g. "github") or None

        return nodes
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/workspaces/{name}/nodes", response_model=None)
def create_workspace_node(
    req: NodeCreate, wm: WorkspaceManager = Depends(get_workspace_manager)
) -> Union[Dict[str, Any], JSONResponse]:
    """Create a new node in a workspace.

    Args:
        name (str): Workspace name.
        req (NodeCreate): Node to create.

    Returns:
        Dict[str, Any]: Node.
    """
    try:
        node_id = wm.get_or_add_node(req.type, req.value, req.metadata)
        return {"success": True, "node_id": node_id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/workspaces/{name}/edges", response_model=None)
def get_workspace_edges(
    wm: WorkspaceManager = Depends(get_workspace_manager),
) -> Union[List[Dict[str, Any]], JSONResponse]:
    """Get all edges in a workspace.

    Args:
        name (str): Workspace name.

    Returns:
        List[Dict[str, Any]]: List of edges.
    """
    try:
        cursor = wm.conn.cursor()
        cursor.execute("SELECT * FROM edge")
        edges = [dict(row) for row in cursor.fetchall()]
        for edge in edges:
            if edge.get("metadata"):
                try:
                    edge["metadata"] = json.loads(edge["metadata"])
                except Exception:
                    pass
        return edges
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/config/unlock", response_model=None)
def unlock_config(
    req: ConfigUnlock, config: ConfigManager = Depends(get_config)
) -> Union[Dict[str, Any], JSONResponse]:
    """Unlock the config.

    Args:
        req (ConfigUnlock): Config to unlock.

    Returns:
        Dict[str, Any]: Success status.
    """
    if config.unlock(req.password):
        return {"success": True}
    return JSONResponse(status_code=401, content={"error": "Invalid password"})


@app.get("/api/config/keys", response_model=None)
def get_config_keys(
    config: ConfigManager = Depends(get_config),
) -> Union[List[Dict[str, Any]], JSONResponse]:
    """Get all API keys with their values masked.

    The plaintext key value is never returned over HTTP: the unlock state is a
    process-global flag, so once any client unlocks, this endpoint would
    otherwise disclose decrypted keys to any origin/host that can reach the port.
    Only masked values are exposed; modules read the real keys server-side.

    Returns:
        List[Dict[str, Any]]: List of API key services with masked values.
    """
    if not config.is_unlocked():
        return JSONResponse(status_code=401, content={"error": "Config locked"})

    masked = []
    for k in config.get_all_api_keys():
        val = k.get("api_key", "") or ""
        masked.append(
            {
                **k,
                "api_key": (val[:4] + "*" * (len(val) - 4))
                if len(val) > 4
                else "*" * len(val),
            }
        )
    return masked


@app.post("/api/config/keys", response_model=None)
def set_config_key(
    req: APIKeyCreate, config: ConfigManager = Depends(get_config)
) -> Union[Dict[str, Any], JSONResponse]:
    """Set an API key.

    Args:
        req (APIKeyCreate): API key to set.

    Returns:
        Dict[str, Any]: Success status.
    """
    if not config.is_unlocked():
        return JSONResponse(status_code=401, content={"error": "Config locked"})
    config.set_api_key(req.service.lower(), req.api_key)
    return {"success": True}


@app.get("/api/config/preferences")
def get_preferences(
    config: ConfigManager = Depends(get_config),
) -> Dict[str, str]:
    """Get all configuration preferences."""
    cursor = config.conn.cursor()
    cursor.execute("SELECT key, value FROM preferences")
    rows = cursor.fetchall()
    blocked_keys = ["last_workspace", "api_keys_salt", "master_password_check"]

    prefs = {}
    for row in rows:
        key = row[0]
        val = row[1]
        if key in blocked_keys:
            continue
        prefs[key] = val
    return prefs


@app.post("/api/config/preferences")
def update_preferences(
    req: Dict[str, Any], config: ConfigManager = Depends(get_config)
) -> Dict[str, bool]:
    """Update multiple preferences."""
    blocked_keys = ["last_workspace", "api_keys_salt", "master_password_check"]
    if "key" in req and "value" in req and len(req) == 2:
        key = req["key"]
        val = req["value"]
        if key not in blocked_keys:
            config.set_preference(key, str(val))
    else:
        for key, val in req.items():
            if key in blocked_keys:
                continue
            config.set_preference(key, str(val))
    return {"success": True}


def mask_proxy_url(url: str) -> str:
    match = PROXY_CREDENTIALS_RE.match(url)
    if match:
        scheme = match.group(1)
        return f"{scheme}://****:****@{url[match.end() :]}"
    return url


@app.get("/api/proxies")
def get_proxies(config: ConfigManager = Depends(get_config)) -> List[Dict[str, Any]]:
    """Get all registered proxies."""
    proxies = config.get_all_proxies()
    for p in proxies:
        if "url" in p:
            p["url"] = mask_proxy_url(p["url"])
    return proxies


def is_valid_proxy_url(url: str) -> tuple[bool, str]:
    match = PROXY_VALIDATION_RE.match(url)
    if not match:
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            if parsed.scheme.lower() not in [
                "http",
                "https",
                "socks4",
                "socks4a",
                "socks5",
                "socks5h",
            ]:
                return (
                    False,
                    "Invalid scheme. Supported schemes are: http, https, socks4, socks4a, socks5, socks5h",
                )
            if not parsed.hostname:
                return False, "Host is required (e.g. host:port or user:pass@host:port)"
            try:
                port = parsed.port
            except ValueError:
                return False, "Port must be in range 1-65535"
            if port is None:
                return False, "Port is required (e.g. host:port)"
            if not (1 <= port <= 65535):
                return False, "Port must be in range 1-65535"
        except Exception:
            logger.exception("Failed to parse proxy URL during validation")
            return False, "Malformed proxy URL. Format: scheme://[user:pass@]host:port"
        return False, "Malformed proxy URL. Format: scheme://[user:pass@]host:port"

    try:
        port = int(match.group("port"))
        if not (1 <= port <= 65535):
            return False, "Port must be in range 1-65535"
    except ValueError:
        return False, "Port must be in range 1-65535"

    return True, ""


@app.post("/api/proxies")
def add_proxy(
    req: ProxyCreate, config: ConfigManager = Depends(get_config)
) -> Dict[str, Any]:
    """Register a new proxy."""
    url = req.url.strip()
    if not url:
        return {"success": False, "error": "URL is required"}

    is_valid, err_msg = is_valid_proxy_url(url)
    if not is_valid:
        return {"success": False, "error": err_msg}

    success = config.add_proxy(url)
    if success:
        return {"success": True}
    return {"success": False, "error": "Proxy already exists"}


@app.delete("/api/proxies/{proxy_id}")
def delete_proxy(
    proxy_id: int, config: ConfigManager = Depends(get_config)
) -> Dict[str, bool]:
    """Delete a registered proxy."""
    success = config.delete_proxy(proxy_id)
    return {"success": success}


@app.post("/api/proxies/{proxy_id}/toggle")
def toggle_proxy(
    proxy_id: int, req: Dict[str, Any], config: ConfigManager = Depends(get_config)
) -> Dict[str, bool]:
    """Toggle is_enabled for a proxy."""
    enabled = bool(req.get("is_enabled", True))
    success = config.set_proxy_enabled(proxy_id, enabled)
    return {"success": success}


@app.post("/api/proxies/load")
def load_proxies(
    req: Dict[str, Any], config: ConfigManager = Depends(get_config)
) -> Dict[str, Any]:
    """Bulk import proxies from raw text content."""
    content = req.get("content", "")
    if not content:
        return {"success": False, "error": "No proxies provided"}

    urls = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    valid_urls = []
    for url in urls:
        is_valid, _ = is_valid_proxy_url(url)
        if is_valid:
            valid_urls.append(url)

    added = config.add_proxies(valid_urls)
    return {"success": True, "loaded": added, "total": len(urls)}


@app.post("/api/proxies/test")
async def test_proxies(config: ConfigManager = Depends(get_config)) -> Dict[str, str]:
    """Trigger concurrent connectivity health checks in the background."""

    # Need to run connectivity checks asynchronously in a background task
    async def perform_async_checks():
        # Setup temporary config instance for background runner
        from src.core.managers import ConfigManager

        bg_config = ConfigManager("~/.keen/config.db")
        proxies = bg_config.get_all_proxies()
        if not proxies:
            bg_config.close()
            return

        import time

        import httpx

        sem = asyncio.Semaphore(10)

        async def check_one(p):
            async with sem:
                url = p["url"]
                proxy_id = p["id"]
                start_time = time.time()
                try:
                    async with httpx.AsyncClient(proxy=url, timeout=5.0) as client:
                        resp = await client.get("https://httpbin.org/ip")
                        if resp.status_code == 200:
                            latency = time.time() - start_time
                            bg_config.update_proxy_status(proxy_id, "online", latency)
                        else:
                            bg_config.update_proxy_status(proxy_id, "offline", -1)
                except Exception:
                    bg_config.update_proxy_status(proxy_id, "offline", -1)

        tasks = [check_one(p) for p in proxies]
        await asyncio.gather(*tasks)
        bg_config.close()

    # Schedule the coroutine without blocking the request lifecycle/event loop
    task = asyncio.create_task(perform_async_checks())
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return {"status": "testing"}


@app.delete("/api/workspaces/{name}")
def delete_workspace(
    name: str, config: ConfigManager = Depends(get_config)
) -> Dict[str, bool]:
    """Delete a workspace.

    Args:
        name (str): Workspace name.

    Returns:
        Dict[str, Any]: Success status.
    """
    config.delete_workspace(name)
    return {"success": True}


@app.put("/api/workspaces/{name}", response_model=None)
def rename_workspace(
    name: str, req: WorkspaceRename, config: ConfigManager = Depends(get_config)
) -> Union[Dict[str, Any], JSONResponse]:
    """Rename a workspace.

    Args:
        name (str): Workspace name.
        req (WorkspaceRename): New name.

    Returns:
        Dict[str, Any]: Success status.
    """
    if not req.new_name.strip():
        return JSONResponse(status_code=400, content={"error": "Name is required"})

    new_name = req.new_name.strip()
    if not all(c.isalnum() or c in " _-" for c in new_name):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Workspace name must be alphanumeric (underscores/hyphens/spaces allowed)."
            },
        )

    # Pass the display name through; rename_workspace derives the .keen filename
    # via get_valid_name internally.
    try:
        config.rename_workspace(name, new_name)
        return {"success": True, "new_name": new_name}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/api/workspaces/{name}/export")
def export_workspace(
    name: str,
    format: str,
    background_tasks: BackgroundTasks,
    config: ConfigManager = Depends(get_config),
) -> Any:
    """Export workspace to multiple formats.

    Args:
        name (str): Workspace name.
        format (str): Export format.

    Returns:
        Any: File response.
    """
    w = config.get_workspace(name)
    if not w:
        raise WorkspaceNotFoundException()

    format = format.lower()
    if format not in ["pdf", "html", "stix2", "json", "markdown"]:
        return JSONResponse(
            status_code=400, content={"error": f"Unsupported export format: {format}"}
        )

    import os
    import tempfile

    from fastapi.responses import FileResponse

    ext_map = {
        "pdf": ".pdf",
        "html": ".html",
        "stix2": ".json",
        "json": ".json",
        "markdown": ".md",
    }
    ext = ext_map.get(format, ".txt")

    temp_fd, temp_path = tempfile.mkstemp(suffix=ext)
    os.close(temp_fd)

    try:
        wm = WorkspaceManager(w["path"], name=name)
        wm.export(format, temp_path)
        wm.close()
    except Exception:
        logger.exception("Workspace export failed")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return JSONResponse(
            status_code=500,
            content={"error": "Export failed due to an internal server error."},
        )

    def cleanup():
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    background_tasks.add_task(cleanup)

    media_types = {
        "pdf": "application/pdf",
        "html": "text/html",
        "stix2": "application/json",
        "json": "application/json",
        "markdown": "text/markdown",
    }

    filename = f"{name}_export{ext}"

    return FileResponse(
        path=temp_path,
        media_type=media_types.get(format, "application/octet-stream"),
        filename=filename,
    )


@app.post("/api/workspaces/{name}/edges", response_model=None)
def create_workspace_edge(
    req: EdgeCreate, wm: WorkspaceManager = Depends(get_workspace_manager)
) -> Union[Dict[str, Any], JSONResponse]:
    """Create a new edge in a workspace.

    Args:
        name (str): Workspace name.
        req (EdgeCreate): Edge to create.

    Returns:
        Dict[str, Any]: Success status.
    """
    try:

        def resolve_node_id(ref: str) -> int | None:
            if ref.isdigit():
                nid = int(ref)
                if wm.node_exists_by_id(nid):
                    return nid
            return wm.get_node_id(ref)

        source_id = resolve_node_id(req.source_id)
        target_id = resolve_node_id(req.target_id)

        if not source_id or not target_id:
            return JSONResponse(
                status_code=400, content={"error": "Invalid node references"}
            )

        wm.add_edge(source_id, target_id, req.relationship, req.metadata)
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.delete("/api/workspaces/{name}/nodes/{node_id}", response_model=None)
def delete_workspace_node(
    node_id: int, wm: WorkspaceManager = Depends(get_workspace_manager)
) -> Union[Dict[str, Any], JSONResponse]:
    """Delete a node from a workspace.

    Args:
        name (str): Workspace name.
        node_id (int): Node ID.

    Returns:
        Dict[str, Any]: Success status.
    """
    try:
        wm.delete_node(node_id)
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.delete("/api/workspaces/{name}/edges/{edge_id}", response_model=None)
def delete_workspace_edge(
    edge_id: int, wm: WorkspaceManager = Depends(get_workspace_manager)
) -> Union[Dict[str, Any], JSONResponse]:
    """Delete an edge from a workspace.

    Args:
        name (str): Workspace name.
        edge_id (int): Edge ID.

    Returns:
        Dict[str, Any]: Success status.
    """
    try:
        wm.delete_edge(edge_id)
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.put("/api/workspaces/{name}/nodes/{node_id}", response_model=None)
def update_workspace_node(
    node_id: int,
    req: NodeUpdate,
    wm: WorkspaceManager = Depends(get_workspace_manager),
) -> Union[Dict[str, Any], JSONResponse]:
    """Update a node in a workspace.

    Args:
        name (str): Workspace name.
        node_id (int): Node ID.
        req (NodeUpdate): Updated node data.

    Returns:
        Dict[str, Any]: Success status.
    """
    if req.type is None and req.value is None and req.metadata is None:
        return JSONResponse(
            status_code=400, content={"error": "No fields provided to update"}
        )

    try:
        updated = wm.update_node(node_id, req.type, req.value, req.metadata)
        if not updated:
            return JSONResponse(
                status_code=404, content={"error": "Node not found or no changes made"}
            )
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.put("/api/workspaces/{name}/edges/{edge_id}", response_model=None)
def update_workspace_edge(
    edge_id: int,
    req: EdgeUpdate,
    wm: WorkspaceManager = Depends(get_workspace_manager),
) -> Union[Dict[str, Any], JSONResponse]:
    """Update an edge in a workspace.

    Args:
        name (str): Workspace name.
        edge_id (int): Edge ID.
        req (EdgeUpdate): Updated edge data.

    Returns:
        Dict[str, Any]: Success status.
    """
    if req.relationship is None and req.metadata is None:
        return JSONResponse(
            status_code=400, content={"error": "No fields provided to update"}
        )

    try:
        updated = wm.update_edge(edge_id, req.relationship, req.metadata)
        if not updated:
            return JSONResponse(
                status_code=404, content={"error": "Edge not found or no changes made"}
            )
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/workspaces/{name}/nodes/positions", response_model=None)
def update_node_positions(
    req: NodePositionsUpdate, wm: WorkspaceManager = Depends(get_workspace_manager)
) -> Union[Dict[str, Any], JSONResponse]:
    """Update node positions in a workspace.

    Args:
        name (str): Workspace name.
        req (NodePositionsUpdate): Node positions to update.

    Returns:
        Dict[str, Any]: Success status.
    """
    try:
        cursor = wm.conn.cursor()
        for node_id_str, pos in req.positions.items():
            node_id = None
            if node_id_str.isdigit():
                node_id = int(node_id_str)
            else:
                node_id = wm.get_node_id(node_id_str)

            if node_id:
                cursor.execute(
                    "UPDATE nodes SET x = ?, y = ? WHERE id = ?",
                    (pos.get("x"), pos.get("y"), node_id),
                )
        wm.conn.commit()
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/workspaces/{name}/suggestions", response_model=None)
def get_workspace_suggestions(
    wm: WorkspaceManager = Depends(get_workspace_manager),
) -> Union[Dict[str, Any], JSONResponse]:
    """Get all AI suggestions and thoughts in a workspace.

    Args:
        wm (WorkspaceManager): The active workspace manager dependency.

    Returns:
        Union[Dict[str, Any], JSONResponse]: Suggestions and thoughts.
    """
    try:
        suggestions = wm.get_suggestions()
        latest_analysis = wm.get_latest_analysis()
        return {"suggestions": suggestions, "latest_analysis": latest_analysis}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/workspaces/{name}/suggestions/status", response_model=None)
def get_workspace_suggestions_status(
    name: str,
) -> Dict[str, Any]:
    """Get the current AI generation status and logs for a workspace.

    Args:
        name (str): Workspace name.

    Returns:
        Dict[str, Any]: Status and activity logs.
    """
    from src.core.thinking_partner import ThinkingPartnerEngine

    task_info = ThinkingPartnerEngine.active_tasks.get(name)
    if task_info:
        return {
            "is_generating": task_info.get("is_generating", False),
            "logs": task_info.get("logs", []),
        }
    return {"is_generating": False, "logs": []}


@app.post("/api/workspaces/{name}/suggestions/generate", response_model=None)
async def generate_workspace_suggestions(
    name: str,
    req: Optional[SuggestionGenerateRequest] = None,
) -> Union[List[Dict[str, Any]], JSONResponse]:
    """Manually trigger AI suggestion engine for a workspace with optional user query and selected nodes.

    Args:
        name (str): Workspace name.
        req (SuggestionGenerateRequest): Request body payload.

    Returns:
        Union[List[Dict[str, Any]], JSONResponse]: List of generated suggestions.
    """
    try:
        from src.core.thinking_partner import ThinkingPartnerEngine

        user_query = req.user_query if req else None
        selected_nodes = req.selected_nodes if req else None

        # Check if the workspace exists first to avoid silent failures
        engine = ThinkingPartnerEngine()
        suggestions = await engine.generate_suggestions(
            name, user_query=user_query, selected_nodes=selected_nodes
        )
        return suggestions
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post(
    "/api/workspaces/{name}/suggestions/{suggestion_id}/feedback", response_model=None
)
def submit_suggestion_feedback(
    suggestion_id: int,
    req: FeedbackSubmit,
    wm: WorkspaceManager = Depends(get_workspace_manager),
) -> Union[Dict[str, Any], JSONResponse]:
    """Submit user feedback for an AI suggestion.

    Args:
        suggestion_id (int): Suggestion ID.
        req (FeedbackSubmit): Feedback data.
        wm (WorkspaceManager): The active workspace manager dependency.

    Returns:
        Union[Dict[str, Any], JSONResponse]: Success status.
    """
    try:
        updated = wm.update_suggestion_status(suggestion_id, req.status, req.feedback)
        if not updated:
            return JSONResponse(
                status_code=404, content={"error": "Suggestion not found"}
            )
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/config/ai/test")
async def test_ai_connection(req: AITestRequest) -> Dict[str, Any]:
    """Test connection to the LLM provider using temporary or saved config."""
    provider = req.provider.lower()
    model = req.model or "gpt-4o"
    base_url = req.base_url or ""
    api_key = req.api_key or ""

    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                if base_url:
                    url = base_url.rstrip("/") + "/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                }
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    return {"success": True, "message": "Connection successful!"}
                else:
                    return {
                        "success": False,
                        "error": f"API returned status code {resp.status_code}: {resp.text}",
                    }

            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                if base_url:
                    url = base_url.rstrip("/") + "/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                payload = {
                    "model": model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "ping"}],
                }
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    return {"success": True, "message": "Connection successful!"}
                else:
                    return {
                        "success": False,
                        "error": f"API returned status code {resp.status_code}: {resp.text}",
                    }

            else:
                # Local / Ollama / LM Studio / KoboldCpp / Custom OpenAI Compatible
                url = "http://localhost:1234/v1/chat/completions"
                if base_url:
                    url = base_url.rstrip("/")
                    if "/v1" not in url:
                        url = url + "/v1"
                    if not url.endswith("/chat/completions"):
                        url = url + "/chat/completions"
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                }

                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    return {"success": True, "message": "Connection successful!"}
                else:
                    return {
                        "success": False,
                        "error": f"API returned status code {resp.status_code}: {resp.text}",
                    }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/config/ai/detect-models")
async def detect_ai_models(req: AITestRequest) -> Dict[str, Any]:
    """Fetch available models from the provider endpoint."""
    provider = req.provider.lower()
    base_url = req.base_url or ""
    api_key = req.api_key or ""

    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == "openai":
                url = "https://api.openai.com/v1/models"
                if base_url:
                    url = base_url.rstrip("/") + "/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    models_data = resp.json()
                    model_ids = [m["id"] for m in models_data.get("data", [])]
                    return {"success": True, "models": model_ids}
                else:
                    return {
                        "success": False,
                        "error": f"Failed to fetch models: {resp.text}",
                    }

            elif provider == "anthropic":
                # Anthropic doesn't have a public models list endpoint, return standard list
                standard_models = [
                    "claude-3-5-sonnet-20240620",
                    "claude-3-opus-20240229",
                    "claude-3-sonnet-20240229",
                    "claude-3-haiku-20240307",
                ]
                return {
                    "success": True,
                    "models": standard_models,
                    "note": "Anthropic does not expose a list endpoint. Showing standard models.",
                }

            elif provider == "ollama":
                # Ollama standard models tags endpoint is /api/tags
                url = "http://localhost:11434/api/tags"
                if base_url:
                    parsed_url = base_url.rstrip("/")
                    if parsed_url.endswith("/v1"):
                        url = parsed_url[:-3] + "/api/tags"
                    else:
                        url = parsed_url + "/api/tags"

                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        model_ids = [m["name"] for m in data.get("models", [])]
                        return {"success": True, "models": model_ids}
                except Exception:
                    pass

                # Fallback to /v1/models
                url = "http://localhost:11434/v1/models"
                if base_url:
                    url = base_url.rstrip("/")
                    if not url.endswith("/models"):
                        if url.endswith("/v1"):
                            url = url + "/models"
                        else:
                            url = url + "/v1/models"
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    model_ids = [m["id"] for m in data.get("data", [])]
                    return {"success": True, "models": model_ids}
                else:
                    return {
                        "success": False,
                        "error": f"Failed to fetch models from Ollama: {resp.text}",
                    }

            else:
                # LM Studio / KoboldCpp / Custom OpenAI Compatible
                url = "http://localhost:1234/v1/models"
                if base_url:
                    url = base_url.rstrip("/")
                    if not url.endswith("/models"):
                        if url.endswith("/v1"):
                            url = url + "/models"
                        else:
                            url = url + "/v1/models"
                headers = {}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    model_ids = [m["id"] for m in data.get("data", [])]
                    return {"success": True, "models": model_ids}
                else:
                    return {
                        "success": False,
                        "error": f"Failed to fetch models: {resp.text}",
                    }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/modules")
def get_modules() -> Dict[str, Any]:
    """Get all available modules.

    Returns:
        Dict[str, Any]: Dictionary of modules.
    """
    modules = load_modules()
    result = {}
    for key, cls in modules.items():
        if "/" in key and not key.startswith("src."):
            metadata = getattr(cls, "metadata", {}).copy()
            metadata["category"] = key.split("/")[0]
            result[key] = metadata
    return result


@app.websocket("/ws/modules/{module_name:path}/run")
async def websocket_run_module(websocket: WebSocket, module_name: str) -> None:
    """Run a module asynchronously via WebSocket.

    Args:
        websocket (WebSocket): WebSocket connection.
        module_name (str): Module name.
    """
    await websocket.accept()

    config = ConfigManager("~/.keen/config.db")
    handler_id = None
    workspace = None

    try:
        # Receive configuration payload
        data = await websocket.receive_json()
        options = data.get("options", {})
        workspace_name = data.get("workspace_name", "")

        # Setup workspace context
        if workspace_name:
            w = config.get_workspace(workspace_name)
            if w:
                workspace = WorkspaceManager(w["path"], name=workspace_name)

        # Instantiate module
        modules = load_modules()

        # We need to find the module. load_modules maps short name, category/name, and full path.
        # Let's find by short name or exact match.
        target_module_class = None
        for key, cls in modules.items():
            metadata = getattr(cls, "metadata", {})
            m_name = metadata.get("name", "").lower()
            if module_name.lower() in [key.lower(), m_name]:
                target_module_class = cls
                break

        if not target_module_class:
            await websocket.send_json(
                {"type": "error", "message": f"Module '{module_name}' not found"}
            )
            await websocket.close()
            return

        module_instance = target_module_class()
        module_instance.shell = APIShellContext(workspace=workspace)
        module_instance.is_web_context = True

        # Attempt to load API keys
        if config.is_unlocked():
            module_instance.load_api_keys(config)

        # Set options from request
        for key, val in options.items():
            module_instance.set_option(key, val)

        # Check requirements
        if not module_instance.pre_run():
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Pre-run validation failed. Missing or invalid options.",
                }
            )
            await websocket.close()
            return

        # Setup Log Streaming
        log_queue = asyncio.Queue()
        queue_sink = QueueSink(log_queue)

        # Tag this run with a unique id and filter the sink to only records emitted
        # within this run's context.
        import uuid as _uuid

        run_id = _uuid.uuid4().hex
        handler_id = logger.add(
            queue_sink.write,
            format="{time:HH:mm:ss} | {level} | {message}",
            level="DEBUG",
            filter=lambda r: r["extra"].get("ws_run_id") == run_id,
        )

        stdout_redirector = QueueStdoutRedirector(log_queue)

        # Run Module
        async def run_module_task():
            # Redirect stdout to our queue so rich/print go to WS
            with contextlib.redirect_stdout(stdout_redirector):
                with contextlib.redirect_stderr(stdout_redirector):
                    try:
                        await module_instance.run()
                    except Exception as e:
                        logger.error(f"Execution failed: {e}")

        # Create the task inside contextualize so it inherits ws_run_id in its
        # context, which the sink filter above keys on.
        with logger.contextualize(ws_run_id=run_id):
            module_task = asyncio.create_task(run_module_task())

        # Stream logs down to WS concurrently
        while not module_task.done() or not log_queue.empty():
            try:
                # Wait for next log with timeout to occasionally check task completion
                log_msg = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                await websocket.send_json({"type": "log", "message": log_msg})
                log_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception:
                # Client disconnected, cancel execution
                module_task.cancel()
                break

        try:
            await module_task
            await websocket.send_json({"type": "status", "status": "completed"})
        except asyncio.CancelledError:
            pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if handler_id is not None:
            try:
                logger.remove(handler_id)
            except Exception:
                pass
        try:
            config.close()
        except Exception:
            pass
        if workspace:
            try:
                workspace.close()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass


@app.websocket("/ws/magic/run")
async def websocket_run_magic(websocket: WebSocket) -> None:
    """Run magic chaining asynchronously via WebSocket."""
    await websocket.accept()

    config = ConfigManager("~/.keen/config.db")
    handler_id = None
    workspace = None

    try:
        data = await websocket.receive_json()
        target = data.get("target", "").strip()
        workspace_name = data.get("workspace_name", "")

        if not target:
            await websocket.send_json(
                {"type": "error", "message": "Target is required"}
            )
            await websocket.close()
            return

        # Setup workspace context
        if workspace_name:
            w = config.get_workspace(workspace_name)
            if w:
                workspace = WorkspaceManager(w["path"], name=workspace_name)

        if not workspace:
            last_ws = config.get_preference("last_workspace")
            if last_ws:
                w = config.get_workspace(last_ws)
                if w:
                    workspace = WorkspaceManager(w["path"], name=last_ws)
            if not workspace:
                db_file = "cases/magic.keen"
                os.makedirs("cases", exist_ok=True)
                config.add_workspace(
                    "magic", db_file, "Default magic chaining workspace"
                )
                workspace = WorkspaceManager(db_file, name="magic")

        # Create shell adapter
        shell_adapter = WebShellAdapter(workspace, config)

        from src.core.magic import MagicEngine

        engine = MagicEngine(shell_adapter, config=config)

        # Setup Log Streaming
        log_queue = asyncio.Queue()
        queue_sink = QueueSink(log_queue)

        # Scope this connection's sink to its own run (see the module-run endpoint
        # for details) so concurrent runs don't leak logs into each other.
        import uuid as _uuid

        run_id = _uuid.uuid4().hex
        handler_id = logger.add(
            queue_sink.write,
            format="{time:HH:mm:ss} | {level} | {message}",
            level="DEBUG",
            filter=lambda r: r["extra"].get("ws_run_id") == run_id,
        )

        stdout_redirector = QueueStdoutRedirector(log_queue)

        async def run_magic_task():
            with contextlib.redirect_stdout(stdout_redirector):
                with contextlib.redirect_stderr(stdout_redirector):
                    try:
                        await engine.run_chain(target, force=True)
                    except Exception as e:
                        logger.error(f"Magic execution failed: {e}")

        with logger.contextualize(ws_run_id=run_id):
            magic_task = asyncio.create_task(run_magic_task())
        # Stream logs down to WS concurrently
        while not magic_task.done() or not log_queue.empty():
            try:
                log_msg = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                await websocket.send_json({"type": "log", "message": log_msg})
                log_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception:
                magic_task.cancel()
                break

        try:
            await magic_task
            await websocket.send_json({"type": "status", "status": "completed"})
        except asyncio.CancelledError:
            pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if handler_id is not None:
            try:
                logger.remove(handler_id)
            except Exception:
                pass
        try:
            config.close()
        except Exception:
            pass
        if workspace:
            try:
                workspace.close()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass


app.mount("/", StaticFiles(directory="web", html=True), name="web")


def start_server(
    host: str = "127.0.0.1", port: int = 8000, debug: bool = False
) -> None:
    uvicorn.run("src.api.server:app", host=host, port=port, reload=debug)
