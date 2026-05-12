import os
import sys
import json
import asyncio
import contextlib
import uvicorn
from typing import Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
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

class WorkspaceCreate(BaseModel):
    name: str
    description: str = ""

class ModuleRunRequest(BaseModel):
    workspace_name: Optional[str] = None
    options: Dict[str, Any] = {}

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

import io

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

@app.get("/")
def root():
    return {"message": "Keen API is running. Access /dashboard for the UI."}

@app.get("/api/workspaces")
def get_workspaces():
    config = ConfigManager("~/.keen/config.db")
    workspaces = config.get_all_workspaces()
    
    # Enrich with counts
    for w in workspaces:
        try:
            wm = WorkspaceManager(w["path"], name=w["name"])
            w["node_count"] = wm.get_node_count()
            w["edge_count"] = wm.get_edge_count()
            wm.conn.close()
        except Exception:
            w["node_count"] = 0
            w["edge_count"] = 0
            
    return workspaces

@app.post("/api/workspaces")
def create_workspace(req: WorkspaceCreate):
    config = ConfigManager("~/.keen/config.db")
    if not req.name.isalnum() and "_" not in req.name and "-" not in req.name:
        return JSONResponse(status_code=400, content={"error": "Invalid workspace name"})
        
    db_file = f"cases/{req.name}.keen"
    config.add_workspace(req.name, db_file, req.description or "")
    return {"success": True, "name": req.name, "path": db_file}

@app.get("/api/workspaces/{name}/nodes")
def get_workspace_nodes(name: str):
    config = ConfigManager("~/.keen/config.db")
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
        wm.conn.close()
        return nodes
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/workspaces/{name}/edges")
def get_workspace_edges(name: str):
    config = ConfigManager("~/.keen/config.db")
    w = config.get_workspace(name)
    if not w:
        return JSONResponse(status_code=404, content={"error": "Workspace not found"})
        
    try:
        wm = WorkspaceManager(w["path"], name=name)
        cursor = wm.conn.cursor()
        cursor.execute("SELECT * FROM edge")
        edges = [dict(row) for row in cursor.fetchall()]
        wm.conn.close()
        return edges
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/modules")
def get_modules():
    modules = load_modules()
    result = {}
    for name, cls in modules.items():
        if name not in result: # Avoid duplicates if same module mapped multiple times
            metadata = getattr(cls, "metadata", {})
            result[name] = metadata
    return result

@app.websocket("/ws/modules/{module_name:path}/run")
async def websocket_run_module(websocket: WebSocket, module_name: str):
    await websocket.accept()
    
    config = ConfigManager("~/.keen/config.db")
    handler_id = None
    
    try:
        # 1. Receive configuration payload
        data = await websocket.receive_json()
        options = data.get("options", {})
        workspace_name = data.get("workspace_name", "")
        
        # 2. Setup workspace context
        workspace = None
        if workspace_name:
            w = config.get_workspace(workspace_name)
            if w:
                workspace = WorkspaceManager(w["path"], name=workspace_name)
                
        # 3. Instantiate module
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
            await websocket.send_json({"type": "error", "message": f"Module '{module_name}' not found"})
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
            await websocket.send_json({"type": "error", "message": "Pre-run validation failed. Missing or invalid options."})
            await websocket.close()
            return
            
        # 4. Setup Log Streaming
        log_queue = asyncio.Queue()
        queue_sink = QueueSink(log_queue)
        
        # Add a custom sink to loguru for this connection
        handler_id = logger.add(
            queue_sink.write, 
            format="{time:HH:mm:ss} | {level} | {message}", 
            level="DEBUG"
        )
        
        stdout_redirector = QueueStdoutRedirector(log_queue)
        
        # 5. Run Module
        async def run_module_task():
            # Redirect stdout to our queue so rich/print go to WS
            with contextlib.redirect_stdout(stdout_redirector):
                with contextlib.redirect_stderr(stdout_redirector):
                    try:
                        await module_instance.run()
                    except Exception as e:
                        logger.error(f"Execution failed: {e}")
                        
        module_task = asyncio.create_task(run_module_task())
        
        # 6. Stream logs down to WS concurrently
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
            await websocket.close()
        except Exception:
            pass

def start_server(host: str = "127.0.0.1", port: int = 8000, debug: bool = False):
    uvicorn.run("src.api.server:app", host=host, port=port, reload=debug)
