from src.utils.config_util import get_valid_name
import os
import json
import asyncio
import contextlib
import uvicorn
from typing import Optional, Dict, Any, Generator, List, Union
import io

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from loguru import logger

from src.core.managers import ConfigManager, WorkspaceManager
from src.core.loader import load_modules

app = FastAPI(title="Keen API Web Server")

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
        try:
            wm = WorkspaceManager(w["path"], name=w["name"])
            w["node_count"] = wm.get_node_count()
            w["edge_count"] = wm.get_edge_count()
            wm.close()
        except Exception:
            w["node_count"] = 0
            w["edge_count"] = 0

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
    config.add_workspace(name, db_file, req.description or "")
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
    """Get all API keys.

    Returns:
        List[Dict[str, Any]]: List of API keys.
    """
    if not config.is_unlocked():
        return JSONResponse(status_code=401, content={"error": "Config locked"})
    return config.get_all_api_keys()


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


@app.get("/api/proxies")
def get_proxies(config: ConfigManager = Depends(get_config)) -> List[Dict[str, Any]]:
    """Get all registered proxies."""
    return config.get_all_proxies()


@app.post("/api/proxies")
def add_proxy(req: ProxyCreate, config: ConfigManager = Depends(get_config)) -> Dict[str, Any]:
    """Register a new proxy."""
    if not req.url.strip():
        return {"success": False, "error": "URL is required"}
    success = config.add_proxy(req.url.strip())
    if success:
        return {"success": True}
    return {"success": False, "error": "Proxy already exists"}


@app.delete("/api/proxies/{proxy_id}")
def delete_proxy(proxy_id: int, config: ConfigManager = Depends(get_config)) -> Dict[str, bool]:
    """Delete a registered proxy."""
    success = config.delete_proxy(proxy_id)
    return {"success": success}


@app.post("/api/proxies/{proxy_id}/toggle")
def toggle_proxy(proxy_id: int, req: Dict[str, bool], config: ConfigManager = Depends(get_config)) -> Dict[str, bool]:
    """Toggle is_enabled for a proxy."""
    enabled = req.get("is_enabled", True)
    config.set_proxy_enabled(proxy_id, enabled)
    return {"success": True}


@app.post("/api/proxies/load")
def load_proxies(req: Dict[str, Any], config: ConfigManager = Depends(get_config)) -> Dict[str, Any]:
    """Bulk import proxies from text list or absolute filepath."""
    content = req.get("content", "")
    filepath = req.get("path", "")
    urls = []

    if filepath:
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
            except Exception as e:
                return {"success": False, "error": f"Failed to read file: {e}"}
        else:
            return {"success": False, "error": "File path does not exist"}
    elif content:
        urls = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
    else:
        return {"success": False, "error": "No proxies provided"}

    added = 0
    for url in urls:
        if config.add_proxy(url):
            added += 1
    return {"success": True, "loaded": added, "total": len(urls)}


@app.post("/api/proxies/test")
async def test_proxies(
    background_tasks: BackgroundTasks, config: ConfigManager = Depends(get_config)
) -> Dict[str, str]:
    """Trigger concurrent connectivity health checks in the background."""
    from fastapi import BackgroundTasks
    # Need to run connectivity checks asynchronously in a background task
    async def perform_async_checks():
        # Setup temporary config instance for background runner
        from src.core.managers import ConfigManager
        bg_config = ConfigManager("~/.keen/config.db")
        proxies = bg_config.get_all_proxies()
        if not proxies:
            bg_config.close()
            return

        import httpx
        import time
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

    # Schedule the coroutine in background tasks
    # Since background_tasks accepts async def functions, let's run it directly
    background_tasks.add_task(perform_async_checks)
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

    new_filename = get_valid_name(new_name)

    try:
        config.rename_workspace(name, new_filename)
        return {"success": True, "new_name": new_filename}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


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

        # Add a custom sink to loguru for this connection
        handler_id = logger.add(
            queue_sink.write,
            format="{time:HH:mm:ss} | {level} | {message}",
            level="DEBUG",
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

        handler_id = logger.add(
            queue_sink.write,
            format="{time:HH:mm:ss} | {level} | {message}",
            level="DEBUG",
        )

        stdout_redirector = QueueStdoutRedirector(log_queue)

        async def run_magic_task():
            with contextlib.redirect_stdout(stdout_redirector):
                with contextlib.redirect_stderr(stdout_redirector):
                    try:
                        await engine.run_chain(target, force=True)
                    except Exception as e:
                        logger.error(f"Magic execution failed: {e}")

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
