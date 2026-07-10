import asyncio
import contextlib
import io
import json
import os
import re
import secrets
from typing import Any, Dict, Generator, List, Optional, Union

import uvicorn
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.loader import load_modules
from src.core.managers import ConfigManager, WorkspaceManager
from src.core.playbooks import PlaybookEngine, load_playbook, validate_playbook
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

# --------------------------------------------------------------------------- #
# Optional session-token authentication.
#
# Off by default (preserving the current single-user local workflow). When
# enabled via KEEN_REQUIRE_AUTH=1, every /api route except the exemptions below
# requires an `Authorization: Bearer <token>` header; a token is minted on a
# successful /api/config/unlock and returned to the client. This closes the
# "any host that can reach the port drives the tool" gap for networked
# deployments without changing local behavior.
# --------------------------------------------------------------------------- #
_SESSION_TOKENS: set = set()
_AUTH_EXEMPT_PATHS = {"/api/health", "/api/config/unlock", "/api"}


def _auth_enabled() -> bool:
    return os.environ.get("KEEN_REQUIRE_AUTH", "").lower() in ("1", "true", "yes")


def _issue_session_token() -> str:
    token = secrets.token_urlsafe(32)
    _SESSION_TOKENS.add(token)
    return token


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Enforce bearer-token auth on /api routes when KEEN_REQUIRE_AUTH is set."""
    if _auth_enabled():
        path = request.url.path
        if path.startswith("/api") and path not in _AUTH_EXEMPT_PATHS:
            header = request.headers.get("Authorization", "")
            token = header[7:] if header.startswith("Bearer ") else ""
            if token not in _SESSION_TOKENS:
                return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return await call_next(request)


os.makedirs("web", exist_ok=True)

_VALID_SCOPE_TYPES = ("domain", "ip", "cidr", "organization", "person")


class ScopeEntryCreate(BaseModel):
    scope_type: str
    value: str
    consent_basis: str = ""


class WorkspaceCreate(BaseModel):
    name: str
    description: str = ""
    scope: List[ScopeEntryCreate] = []


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


class ProxyToggle(BaseModel):
    is_enabled: bool = True


class ProxyLoad(BaseModel):
    content: str = ""


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


class NodeMergeRequest(BaseModel):
    canonical_id: int
    absorbed_ids: List[int]


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


class PlaybookSaveRequest(BaseModel):
    """Either ``yaml_content`` (raw text, from the YAML editor) or ``playbook``
    (a structured dict, from the visual DAG builder) must be given -- never
    both. Exactly one wire format in, one canonical YAML file out."""

    yaml_content: Optional[str] = None
    playbook: Optional[Dict[str, Any]] = None


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


def validate_workspace_name(raw_name: str) -> str:
    """Validate a workspace display name, returning the trimmed name.

    Shared by workspace create and rename so the rule lives in one place.
    Raises HTTPException(400) with the API's ``{"error": ...}`` shape on failure.
    """
    name = (raw_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not all(c.isalnum() or c in " _-" for c in name):
        raise HTTPException(
            status_code=400,
            detail="Workspace name must be alphanumeric (underscores/hyphens/spaces allowed).",
        )
    return name


PLAYBOOKS_DIR = "playbooks"
_PLAYBOOK_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _playbook_path(playbook_id: str) -> str:
    """Resolve ``playbook_id`` to a file under ``PLAYBOOKS_DIR``."""
    if not _PLAYBOOK_ID_RE.match(playbook_id):
        raise HTTPException(
            status_code=400,
            detail="Playbook id must be alphanumeric (underscores/hyphens allowed).",
        )
    os.makedirs(PLAYBOOKS_DIR, exist_ok=True)
    return os.path.join(PLAYBOOKS_DIR, f"{playbook_id}.yaml")


def _parse_playbook_body(body: "PlaybookSaveRequest"):
    """Normalize a save/validate request body to a playbook dict.

    Returns ``(playbook, error_message)`` -- exactly one is ``None``.
    """
    import yaml

    if body.yaml_content is not None:
        try:
            return yaml.safe_load(body.yaml_content), None
        except yaml.YAMLError as e:
            return None, f"Invalid YAML: {e}"
    if body.playbook is not None:
        return body.playbook, None
    return None, "Either 'yaml_content' or 'playbook' must be provided"


def _save_playbook(path: str, body: "PlaybookSaveRequest") -> JSONResponse:
    import yaml

    playbook, error = _parse_playbook_body(body)
    if error:
        return JSONResponse(status_code=400, content={"error": error})

    result = validate_playbook(playbook)
    if result["errors"]:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid playbook",
                "errors": result["errors"],
                "warnings": result["warnings"],
            },
        )

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(playbook, f, sort_keys=False)
    return JSONResponse(content={"success": True, "warnings": result["warnings"]})


class WorkspaceNotFoundException(Exception):
    pass


@app.exception_handler(WorkspaceNotFoundException)
def workspace_not_found_handler(
    request: Request, exc: WorkspaceNotFoundException
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "Workspace not found"})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Return HTTP errors in the API's consistent ``{"error": ...}`` envelope
    (the SPA reads ``.error``) rather than Starlette's default ``{"detail": ...}``."""
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Shape 422 request-validation failures like every other error."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "Invalid request parameters.",
            "details": jsonable_encoder(exc.errors()),
        },
    )


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
    include_counts: bool = True,
    config: ConfigManager = Depends(get_config),
) -> List[Dict[str, Any]]:
    """Get all workspaces.

    Args:
        include_counts: When True (default), enrich each workspace with node/edge
            counts — which requires opening every workspace DB file. Pass
            ``?include_counts=false`` to skip that work for a fast listing.

    Returns:
        List[Dict[str, Any]]: List of workspaces.
    """
    workspaces = config.get_all_workspaces()

    if not include_counts:
        return workspaces

    # Enrich with counts (opens each workspace DB — one connection per file).
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
    name = validate_workspace_name(req.name)

    filename = get_valid_name(name)

    db_file = f"cases/{filename}.keen"
    try:
        config.add_workspace(name, db_file, req.description or "")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if req.scope:
        for entry in req.scope:
            if entry.scope_type not in _VALID_SCOPE_TYPES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid scope_type '{entry.scope_type}'. Must be one of: {', '.join(_VALID_SCOPE_TYPES)}.",
                )
        wm = WorkspaceManager(db_file, name=name)
        try:
            for entry in req.scope:
                wm.add_scope_entry(entry.scope_type, entry.value, entry.consent_basis)
        finally:
            wm.close()

    return {"success": True, "name": name, "path": db_file}


@app.get("/api/workspaces/{name}/nodes", response_model=None)
def get_workspace_nodes(
    wm: WorkspaceManager = Depends(get_workspace_manager),
    limit: Optional[int] = None,
    offset: int = 0,
) -> Union[List[Dict[str, Any]], JSONResponse]:
    """Get nodes in a workspace.

    Args:
        wm (WorkspaceManager): The active workspace manager dependency.
        limit: Optional maximum number of nodes to return (omit for all).
        offset: Number of rows to skip (for pagination); default 0.

    Returns:
        Union[List[Dict[str, Any]], JSONResponse]: List of nodes in the workspace or a 500 JSONResponse on exception.
    """
    try:
        cursor = wm.conn.cursor()
        if limit is not None:
            cursor.execute(
                "SELECT * FROM nodes ORDER BY id LIMIT ? OFFSET ?",
                (max(0, limit), max(0, offset)),
            )
        else:
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
    limit: Optional[int] = None,
    offset: int = 0,
) -> Union[List[Dict[str, Any]], JSONResponse]:
    """Get edges in a workspace.

    Args:
        name (str): Workspace name.
        limit: Optional maximum number of edges to return (omit for all).
        offset: Number of rows to skip (for pagination); default 0.

    Returns:
        List[Dict[str, Any]]: List of edges.
    """
    try:
        cursor = wm.conn.cursor()
        if limit is not None:
            cursor.execute(
                "SELECT * FROM edge ORDER BY id LIMIT ? OFFSET ?",
                (max(0, limit), max(0, offset)),
            )
        else:
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
        # Mint a session token so clients can authenticate subsequent requests
        # when KEEN_REQUIRE_AUTH is enabled (harmless/no-op otherwise).
        return {"success": True, "token": _issue_session_token()}
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
    proxy_id: int, req: ProxyToggle, config: ConfigManager = Depends(get_config)
) -> Dict[str, bool]:
    """Toggle is_enabled for a proxy."""
    success = config.set_proxy_enabled(proxy_id, req.is_enabled)
    return {"success": success}


@app.post("/api/proxies/load")
def load_proxies(
    req: ProxyLoad, config: ConfigManager = Depends(get_config)
) -> Dict[str, Any]:
    """Bulk import proxies from raw text content."""
    content = req.content
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
    new_name = validate_workspace_name(req.new_name)

    # Pass the display name through; rename_workspace derives the .keen filename
    # via get_valid_name internally.
    try:
        config.rename_workspace(name, new_name)
        return {"success": True, "new_name": new_name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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


@app.post("/api/workspaces/{name}/nodes/merge", response_model=None)
def merge_workspace_nodes(
    req: NodeMergeRequest, wm: WorkspaceManager = Depends(get_workspace_manager)
) -> Union[Dict[str, Any], JSONResponse]:
    """Merge nodes into one identity.

    Re-points every edge from ``absorbed_ids`` onto ``canonical_id``, unions
    their metadata, and logs one provenance ledger entry. This is always an
    explicit operator action -- nothing in Keen merges nodes automatically.
    """
    try:
        merged = wm.merge_nodes(req.canonical_id, req.absorbed_ids, actor="web")
        if not merged:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "Canonical node not found or no absorbed nodes matched"
                },
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


@app.post("/api/notifications/test")
async def test_notifications(
    config: ConfigManager = Depends(get_config),
) -> Dict[str, Any]:
    """Send a synthetic test message to every channel in ``notify_channels``.

    Distinguishes "not configured" from "configured but failed" per channel
    (see ``send_test_notification``) so the Integrations settings tab can
    show exactly what's wrong instead of a single opaque pass/fail.
    """
    from src.utils.notifications import send_test_notification

    results = await send_test_notification(config)
    return {"success": True, "results": results}


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


@app.get("/api/workspaces/{name}/scope", response_model=None)
def get_workspace_scope(
    wm: WorkspaceManager = Depends(get_workspace_manager),
) -> Union[List[Dict[str, Any]], JSONResponse]:
    """List the workspace's declared scope entries (empty = enforcement opted out)."""
    try:
        return wm.list_scope()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/workspaces/{name}/scope", response_model=None)
def create_workspace_scope_entry(
    entry: ScopeEntryCreate, wm: WorkspaceManager = Depends(get_workspace_manager)
) -> Union[Dict[str, Any], JSONResponse]:
    if entry.scope_type not in _VALID_SCOPE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid scope_type '{entry.scope_type}'. Must be one of: {', '.join(_VALID_SCOPE_TYPES)}.",
        )
    entry_id = wm.add_scope_entry(entry.scope_type, entry.value, entry.consent_basis)
    return {"success": True, "id": entry_id}


@app.delete("/api/workspaces/{name}/scope/{entry_id}", response_model=None)
def delete_workspace_scope_entry(
    entry_id: int, wm: WorkspaceManager = Depends(get_workspace_manager)
) -> Union[Dict[str, Any], JSONResponse]:
    if not wm.remove_scope_entry(entry_id):
        return JSONResponse(status_code=404, content={"error": "Scope entry not found"})
    return {"success": True}


@app.get("/api/workspaces/{name}/quarantined-nodes", response_model=None)
def get_workspace_quarantined_nodes(
    wm: WorkspaceManager = Depends(get_workspace_manager),
) -> Union[List[Dict[str, Any]], JSONResponse]:
    """List nodes flagged as outside the workspace's declared scope."""
    try:
        return wm.get_quarantined_nodes()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/workspaces/{name}/jobs", response_model=None)
def get_workspace_jobs(
    wm: WorkspaceManager = Depends(get_workspace_manager),
    status: Optional[str] = None,
    limit: Optional[int] = None,
) -> Union[List[Dict[str, Any]], JSONResponse]:
    """List job_history rows for a workspace (the Web UI task panel's data source)."""
    try:
        return wm.list_jobs(status=status, limit=limit)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/workspaces/{name}/jobs/{job_id}", response_model=None)
def get_workspace_job(
    job_id: str, wm: WorkspaceManager = Depends(get_workspace_manager)
) -> Union[Dict[str, Any], JSONResponse]:
    job = wm.get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return job


@app.post("/api/workspaces/{name}/jobs/{job_id}/cancel", response_model=None)
def cancel_workspace_job(
    job_id: str, wm: WorkspaceManager = Depends(get_workspace_manager)
) -> Union[Dict[str, Any], JSONResponse]:
    """Cancel a job: interrupts its task if this process is still running it
    (see ``_ACTIVE_JOB_TASKS``), and always records the cancellation intent in
    ``job_history`` even if the task isn't found (already finished, or the
    server restarted since it started)."""
    task = _ACTIVE_JOB_TASKS.get(job_id)
    if task and not task.done():
        task.cancel()

    if not wm.cancel_job(job_id):
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return {"success": True}


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


@app.get("/api/playbooks")
def list_playbooks() -> List[Dict[str, Any]]:
    """List playbooks stored under ``playbooks/*.yaml``.

    A playbook that fails to parse is still listed (so it shows up for the
    user to fix or delete) with an ``error`` field instead of being silently
    dropped.
    """
    os.makedirs(PLAYBOOKS_DIR, exist_ok=True)
    result = []
    for fname in sorted(os.listdir(PLAYBOOKS_DIR)):
        if not fname.endswith((".yaml", ".yml")):
            continue
        playbook_id = os.path.splitext(fname)[0]
        try:
            pb = load_playbook(os.path.join(PLAYBOOKS_DIR, fname))
            result.append(
                {
                    "id": playbook_id,
                    "name": pb.get("name", playbook_id),
                    "description": pb.get("description", ""),
                    "trigger_type": pb.get("trigger_type", ""),
                    "step_count": len(pb.get("steps", [])),
                }
            )
        except Exception as e:
            result.append(
                {
                    "id": playbook_id,
                    "name": playbook_id,
                    "description": "",
                    "trigger_type": "",
                    "step_count": 0,
                    "error": str(e),
                }
            )
    return result


@app.get("/api/playbooks/{playbook_id}", response_model=None)
def get_playbook(playbook_id: str) -> Union[Dict[str, Any], JSONResponse]:
    """Return both the raw YAML text (for the YAML editor) and the parsed
    dict (for the visual DAG builder) so either view can be populated
    without re-parsing client-side."""
    path = _playbook_path(playbook_id)
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "Playbook not found"})

    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    try:
        parsed: Optional[Dict[str, Any]] = load_playbook(path)
    except Exception:
        parsed = None
    return {"id": playbook_id, "yaml": raw, "playbook": parsed}


@app.post("/api/playbooks/validate")
def validate_playbook_endpoint(body: PlaybookSaveRequest) -> Dict[str, Any]:
    """Validate a playbook (from either wire format) without writing anything."""
    playbook, error = _parse_playbook_body(body)
    if error:
        return {"valid": False, "errors": [error], "warnings": []}
    result = validate_playbook(playbook)
    return {
        "valid": not result["errors"],
        "errors": result["errors"],
        "warnings": result["warnings"],
    }


@app.post("/api/playbooks/{playbook_id}", response_model=None)
def create_playbook(playbook_id: str, body: PlaybookSaveRequest) -> JSONResponse:
    path = _playbook_path(playbook_id)
    if os.path.exists(path):
        return JSONResponse(
            status_code=409, content={"error": "A playbook with this id already exists"}
        )
    return _save_playbook(path, body)


@app.put("/api/playbooks/{playbook_id}", response_model=None)
def update_playbook(playbook_id: str, body: PlaybookSaveRequest) -> JSONResponse:
    path = _playbook_path(playbook_id)
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "Playbook not found"})
    return _save_playbook(path, body)


@app.delete("/api/playbooks/{playbook_id}", response_model=None)
def delete_playbook(playbook_id: str) -> Union[Dict[str, Any], JSONResponse]:
    path = _playbook_path(playbook_id)
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "Playbook not found"})
    os.remove(path)
    return {"success": True}


# In-memory registry of running jobs' asyncio Tasks, keyed by job_id. A live
# Task can't be persisted to SQLite, so this is what actually lets `jobs
# cancel <job_id>` / POST .../jobs/{job_id}/cancel interrupt a run; the
# job_history row (see WorkspaceManager) is the persisted record of intent
# and outcome, and survives a process restart even though this registry doesn't.
_ACTIVE_JOB_TASKS: Dict[str, asyncio.Task] = {}


async def _stream_run(
    websocket: WebSocket,
    run_coro_factory,
    *,
    workspace: Optional[WorkspaceManager] = None,
    config: Optional[ConfigManager] = None,
    module_instance: Any = None,
    module_name: str = "",
    target_value: str = "",
) -> None:
    """Run ``run_coro_factory()`` while streaming its logs/stdout to ``websocket``.

    Shared by the module- and magic-run WebSocket endpoints (previously ~120
    duplicated lines each). Emits the same wire messages the SPA consumes:
    ``{"type": "log", "message": ...}`` per line and, on success,
    ``{"type": "status", "status": "completed"}``. Manages the per-run loguru
    sink (scoped to this run via ``ws_run_id`` so concurrent runs don't bleed
    logs into each other) and cancels the task if the client disconnects.

    When ``workspace`` is given, this also persists the run as a row in
    ``job_history`` (created ``pending``->``running``, updated as structured
    ``progress``/``node_added``/``edge_added`` events arrive from
    ``module_instance``, and finalized ``completed``/``failed``/``cancelled``),
    registers its task in ``_ACTIVE_JOB_TASKS`` for external cancellation, and
    fires the notification dispatcher on completion. Any structured event a
    module pushes via its ``_event_sink`` rides the same queue as plain log
    strings -- dicts are forwarded as-is; strings are wrapped as ``log``
    messages -- so the wire format gains new message types without breaking
    clients that only understand ``log``/``status``/``error``.
    """
    import uuid as _uuid

    log_queue: asyncio.Queue = asyncio.Queue()
    queue_sink = QueueSink(log_queue)
    run_id = _uuid.uuid4().hex
    handler_id = logger.add(
        queue_sink.write,
        format="{time:HH:mm:ss} | {level} | {message}",
        level="DEBUG",
        filter=lambda r: r["extra"].get("ws_run_id") == run_id,
    )
    stdout_redirector = QueueStdoutRedirector(log_queue)

    job_id: Optional[str] = None
    if workspace is not None:
        job_id = workspace.create_job(module_name or "unknown", target_value or "")
        workspace.update_job(job_id, status="running")

    if module_instance is not None and job_id is not None:
        module_instance._event_sink = log_queue.put_nowait

    run_error: list = []

    async def _runner():
        with contextlib.redirect_stdout(stdout_redirector):
            with contextlib.redirect_stderr(stdout_redirector):
                try:
                    await run_coro_factory()
                except Exception as e:
                    logger.error(f"Execution failed: {e}")
                    run_error.append(str(e))

    nodes_added = 0
    edges_added = 0

    try:
        # Create the task inside contextualize so it inherits ws_run_id, which the
        # sink filter above keys on.
        with logger.contextualize(ws_run_id=run_id):
            task = asyncio.create_task(_runner())

        if job_id is not None:
            _ACTIVE_JOB_TASKS[job_id] = task
            await websocket.send_json({"type": "job_started", "job_id": job_id})

        while not task.done() or not log_queue.empty():
            try:
                item = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                log_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception:
                # Client disconnected — cancel execution and stop streaming.
                task.cancel()
                break

            if isinstance(item, dict):
                if job_id is not None and workspace is not None:
                    if item.get("type") == "progress":
                        workspace.update_job(job_id, progress=item.get("progress"))
                    elif item.get("type") == "node_added":
                        nodes_added += 1
                        workspace.update_job(job_id, nodes_added=nodes_added)
                    elif item.get("type") == "edge_added":
                        edges_added += 1
                        workspace.update_job(job_id, edges_added=edges_added)
                await websocket.send_json(item)
            else:
                if job_id is not None and workspace is not None:
                    workspace.append_job_log(job_id, str(item))
                await websocket.send_json({"type": "log", "message": item})

        try:
            await task
            if job_id is not None and workspace is not None:
                if run_error:
                    workspace.update_job(
                        job_id, status="failed", error_message=run_error[0]
                    )
                else:
                    workspace.update_job(job_id, status="completed", progress=1.0)
            await websocket.send_json({"type": "status", "status": "completed"})
        except asyncio.CancelledError:
            if job_id is not None and workspace is not None:
                workspace.update_job(job_id, status="cancelled")
    finally:
        if job_id is not None:
            _ACTIVE_JOB_TASKS.pop(job_id, None)
            if config is not None and workspace is not None:
                from src.utils.notifications import notify_job_completion

                await notify_job_completion(config, workspace, job_id)
        try:
            logger.remove(handler_id)
        except Exception:
            pass


@app.websocket("/ws/modules/{module_name:path}/run")
async def websocket_run_module(websocket: WebSocket, module_name: str) -> None:
    """Run a module asynchronously via WebSocket.

    Args:
        websocket (WebSocket): WebSocket connection.
        module_name (str): Module name.
    """
    await websocket.accept()

    config = ConfigManager("~/.keen/config.db")
    workspace = None

    try:
        # Receive configuration payload
        data = await websocket.receive_json()
        options = data.get("options", {})
        workspace_name = data.get("workspace_name", "")
        confirm_active = bool(data.get("confirm", False))

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

        if confirm_active:
            module_instance.confirm_execution()

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

        # Stream the module run's logs/stdout to the WebSocket.
        await _stream_run(
            websocket,
            module_instance.run,
            workspace=workspace,
            config=config,
            module_instance=module_instance,
            module_name=getattr(target_module_class, "metadata", {}).get(
                "name", module_name
            ),
            target_value=str(options.get(module_instance.target_option, "")),
        )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
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

        # Stream the magic chain's logs/stdout to the WebSocket. A magic chain
        # invokes many modules internally (see MagicEngine._run_module), so
        # this is tracked as one coarse-grained "magic_chain" job rather than
        # one row per sub-module -- no module_instance to wire a fine-grained
        # event sink to.
        await _stream_run(
            websocket,
            lambda: engine.run_chain(target, force=True),
            workspace=workspace,
            config=config,
            module_name="magic_chain",
            target_value=target,
        )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
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


@app.websocket("/ws/playbooks/{playbook_id}/run")
async def websocket_run_playbook(websocket: WebSocket, playbook_id: str) -> None:
    """Run a playbook asynchronously via WebSocket."""
    await websocket.accept()

    config = ConfigManager("~/.keen/config.db")
    workspace = None

    try:
        try:
            path = _playbook_path(playbook_id)
        except HTTPException as e:
            await websocket.send_json({"type": "error", "message": e.detail})
            await websocket.close()
            return

        if not os.path.exists(path):
            await websocket.send_json(
                {"type": "error", "message": "Playbook not found"}
            )
            await websocket.close()
            return

        try:
            playbook = load_playbook(path)
        except Exception as e:
            await websocket.send_json(
                {"type": "error", "message": f"Invalid playbook: {e}"}
            )
            await websocket.close()
            return

        data = await websocket.receive_json()
        trigger_value = str(data.get("trigger_value", "")).strip()
        workspace_name = data.get("workspace_name", "")

        if not trigger_value:
            await websocket.send_json(
                {"type": "error", "message": "trigger_value is required"}
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
                db_file = "cases/playbooks.keen"
                os.makedirs("cases", exist_ok=True)
                config.add_workspace(
                    "playbooks", db_file, "Default playbook-run workspace"
                )
                workspace = WorkspaceManager(db_file, name="playbooks")

        shell_adapter = WebShellAdapter(workspace, config)
        engine = PlaybookEngine(shell_adapter, config)

        await _stream_run(
            websocket,
            lambda: engine.run(playbook, trigger_value),
            workspace=workspace,
            config=config,
            module_instance=engine,
            module_name=f"playbook:{playbook_id}",
            target_value=trigger_value,
        )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
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
