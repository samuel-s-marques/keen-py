from src.utils.config_util import get_valid_name
import os
import sys
import json
import asyncio
import contextlib
import uvicorn
from typing import Optional, Dict, Any
import io

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("web", exist_ok=True)
app.mount("/dashboard", StaticFiles(directory="web", html=True), name="web")

WORKSPACE_RE_PATTERN = r"/[^a-zA-Z0-9\s_-]/g"


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


class ConfigUnlock(BaseModel):
    password: str


class APIKeyCreate(BaseModel):
    service: str
    api_key: str


class WorkspaceRename(BaseModel):
    new_name: str


class NodePositionsUpdate(BaseModel):
    positions: Dict[str, Dict[str, float]]


class NodeCreate(BaseModel):
    type: str
    value: str
    metadata: Optional[Dict[str, Any]] = {}


class APIShellContext:
    def __init__(self, workspace: WorkspaceManager | None = None):
        self.workspace = workspace


class QueueSink:
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    def write(self, message):
        try:
            self.queue.put_nowait(str(message))
        except Exception:
            pass


class QueueStdoutRedirector(io.TextIOBase):
    def __init__(self, queue: asyncio.Queue):
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


def get_config():
    config = ConfigManager("~/.keen/config.db")
    try:
        yield config
    finally:
        config.close()


@app.get("/")
def root():
    return {"message": "Keen API is running. Access /dashboard for the UI."}


@app.get("/api")
def api():
    return RedirectResponse(url="/docs")


@app.get("/api/workspaces")
def get_workspaces(config: ConfigManager = Depends(get_config)):
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


@app.post("/api/workspaces")
def create_workspace(req: WorkspaceCreate, config: ConfigManager = Depends(get_config)):
    """Create a new workspace.

    Args:
        req (WorkspaceCreate): Workspace to create.

    Returns:
        Dict[str, Any]: Workspace.
    """
    if not req.name.strip():
        return JSONResponse(status_code=400, content={"error": "Name is required"})

    name = get_valid_name(req.name)

    db_file = f"cases/{name}.keen"
    config.add_workspace(req.name, db_file, req.description or "")
    return {"success": True, "name": name, "path": db_file}


@app.get("/api/workspaces/{name}/nodes")
def get_workspace_nodes(name: str, config: ConfigManager = Depends(get_config)):
    """Get all nodes in a workspace.

    Args:
        name (str): Workspace name.

    Returns:
        List[Dict[str, Any]]: List of nodes.
    """
    w = config.get_workspace(name)
    if not w:
        return JSONResponse(status_code=404, content={"error": "Workspace not found"})

    try:
        wm = WorkspaceManager(w["path"], name=name)
        cursor = wm.conn.cursor()
        cursor.execute("SELECT * FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        for node in nodes:
            if node.get("metadata"):
                try:
                    node["metadata"] = json.loads(node["metadata"])
                except Exception:
                    pass
        wm.close()
        return nodes
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/workspaces/{name}/nodes")
def create_workspace_node(
    name: str, req: NodeCreate, config: ConfigManager = Depends(get_config)
):
    """Create a new node in a workspace.

    Args:
        name (str): Workspace name.
        req (NodeCreate): Node to create.

    Returns:
        Dict[str, Any]: Node.
    """
    w = config.get_workspace(name)
    if not w:
        return JSONResponse(status_code=404, content={"error": "Workspace not found"})
    try:
        wm = WorkspaceManager(w["path"], name=name)
        node_id = wm.get_or_add_node(req.type, req.value, req.metadata)
        wm.close()
        return {"success": True, "node_id": node_id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/workspaces/{name}/edges")
def get_workspace_edges(name: str, config: ConfigManager = Depends(get_config)):
    """Get all edges in a workspace.

    Args:
        name (str): Workspace name.

    Returns:
        List[Dict[str, Any]]: List of edges.
    """
    w = config.get_workspace(name)
    if not w:
        return JSONResponse(status_code=404, content={"error": "Workspace not found"})

    try:
        wm = WorkspaceManager(w["path"], name=name)
        cursor = wm.conn.cursor()
        cursor.execute("SELECT * FROM edge")
        edges = [dict(row) for row in cursor.fetchall()]
        wm.close()
        return edges
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/config/unlock")
def unlock_config(req: ConfigUnlock, config: ConfigManager = Depends(get_config)):
    """Unlock the config.

    Args:
        req (ConfigUnlock): Config to unlock.

    Returns:
        Dict[str, Any]: Success status.
    """
    if config.unlock(req.password):
        return {"success": True}
    return JSONResponse(status_code=401, content={"error": "Invalid password"})


@app.get("/api/config/keys")
def get_config_keys(config: ConfigManager = Depends(get_config)):
    """Get all API keys.

    Returns:
        List[Dict[str, Any]]: List of API keys.
    """
    if not config.is_unlocked():
        return JSONResponse(status_code=401, content={"error": "Config locked"})
    return config.get_all_api_keys()


@app.post("/api/config/keys")
def set_config_key(req: APIKeyCreate, config: ConfigManager = Depends(get_config)):
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


@app.delete("/api/workspaces/{name}")
def delete_workspace(name: str, config: ConfigManager = Depends(get_config)):
    """Delete a workspace.

    Args:
        name (str): Workspace name.

    Returns:
        Dict[str, Any]: Success status.
    """
    config.delete_workspace(name)
    return {"success": True}


@app.put("/api/workspaces/{name}")
def rename_workspace(
    name: str, req: WorkspaceRename, config: ConfigManager = Depends(get_config)
):
    """Rename a workspace.

    Args:
        name (str): Workspace name.
        req (WorkspaceRename): New name.

    Returns:
        Dict[str, Any]: Success status.
    """
    if not req.new_name.strip():
        return JSONResponse(status_code=400, content={"error": "Name is required"})

    new_name = get_valid_name(req.new_name)

    try:
        config.rename_workspace(name, new_name)
        return {"success": True, "new_name": new_name}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/workspaces/{name}/edges")
def create_workspace_edge(
    name: str, req: EdgeCreate, config: ConfigManager = Depends(get_config)
):
    """Create a new edge in a workspace.

    Args:
        name (str): Workspace name.
        req (EdgeCreate): Edge to create.

    Returns:
        Dict[str, Any]: Success status.
    """
    w = config.get_workspace(name)
    if not w:
        return JSONResponse(status_code=404, content={"error": "Workspace not found"})
    try:
        wm = WorkspaceManager(w["path"], name=name)

        source_id = req.source_id
        if not source_id.isdigit():
            source_id = wm.get_node_id(source_id)
        target_id = req.target_id
        if not target_id.isdigit():
            target_id = wm.get_node_id(target_id)

        if not source_id or not target_id:
            return JSONResponse(
                status_code=400, content={"error": "Invalid node references"}
            )

        wm.add_edge(int(source_id), int(target_id), req.relationship)
        wm.close()
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.delete("/api/workspaces/{name}/nodes/{node_id}")
def delete_workspace_node(
    name: str, node_id: int, config: ConfigManager = Depends(get_config)
):
    """Delete a node from a workspace.

    Args:
        name (str): Workspace name.
        node_id (int): Node ID.

    Returns:
        Dict[str, Any]: Success status.
    """
    w = config.get_workspace(name)
    if not w:
        return JSONResponse(status_code=404, content={"error": "Workspace not found"})
    try:
        wm = WorkspaceManager(w["path"], name=name)
        wm.delete_node(node_id)
        wm.close()
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.delete("/api/workspaces/{name}/edges/{edge_id}")
def delete_workspace_edge(
    name: str, edge_id: int, config: ConfigManager = Depends(get_config)
):
    """Delete an edge from a workspace.

    Args:
        name (str): Workspace name.
        edge_id (int): Edge ID.

    Returns:
        Dict[str, Any]: Success status.
    """
    w = config.get_workspace(name)
    if not w:
        return JSONResponse(status_code=404, content={"error": "Workspace not found"})
    try:
        wm = WorkspaceManager(w["path"], name=name)
        wm.delete_edge(edge_id)
        wm.close()
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/workspaces/{name}/nodes/positions")
def update_node_positions(
    name: str, req: NodePositionsUpdate, config: ConfigManager = Depends(get_config)
):
    """Update node positions in a workspace.

    Args:
        name (str): Workspace name.
        req (NodePositionsUpdate): Node positions to update.

    Returns:
        Dict[str, Any]: Success status.
    """
    w = config.get_workspace(name)
    if not w:
        return JSONResponse(status_code=404, content={"error": "Workspace not found"})
    try:
        wm = WorkspaceManager(w["path"], name=name)
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
        wm.close()
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/modules")
def get_modules():
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
async def websocket_run_module(websocket: WebSocket, module_name: str):
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
            except WebSocketDisconnect:
                # Client disconnected, cancel execution
                module_task.cancel()
                raise

        await module_task
        await websocket.send_json({"type": "status", "status": "completed"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
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


def start_server(host: str = "127.0.0.1", port: int = 8000, debug: bool = False):
    uvicorn.run("src.api.server:app", host=host, port=port, reload=debug)
