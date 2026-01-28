"""
StoragePilot Dashboard (FastAPI)
================================

Backend API for the React/Tailwind dashboard UI.
Provides:
- Config load/save
- Start scan + stream logs/progress over WebSocket
- Fetch scan results (review state)
- Execute cleaning actions (docker prune, delete dev debt, optional organizer)

Run:
  uvicorn ui.dashboard:app --host 127.0.0.1 --port 8000 --reload

Or use:
  make api
"""

from __future__ import annotations

import os
import json
import uuid
import yaml
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Add project root to path (so imports work when run from repo root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from tools.terminal import TerminalTools
from tools.classifier import FileClassifier


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

DEFAULT_CONFIG: Dict[str, Any] = {
    "scan_paths": {
        "primary": ["~/Downloads", "~/Desktop"],
        "secondary": ["~/Documents"],
        "workspace": ["~/workspace", "~/projects"],
    },
    "safety": {
        "dry_run": True,
        "require_approval": True,
        "backup_before_delete": True,
    },
    "llm": {
        "provider": "ollama",
        "model": "qwen2.5:0.5b",
        "base_url": "http://127.0.0.1:11434/v1",
    },
}


def _load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # Merge defaults (shallow-ish)
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in cfg.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def _save_config(cfg: Dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)


# -----------------------------------------------------------------------------
# Models (request/response)
# -----------------------------------------------------------------------------

class UiConfig(BaseModel):
    provider: Literal["ollama", "openai", "matrixllm"] = "ollama"
    model: str = "qwen2.5:0.5b"
    baseUrl: str = "http://127.0.0.1:11434/v1"
    scanPrimary: str = "., ~/Downloads, ~/Desktop"
    scanWorkspace: str = "~/workspace, ~/projects"
    dryRun: bool = True
    approval: bool = True
    backup: bool = True
    matrixCode: str = ""  # pairing handled elsewhere (optional)


class StartScanResponse(BaseModel):
    scan_id: str


class HudMetrics(BaseModel):
    storage_used_percent: float
    free_human: str
    total_human: str
    waste_human: str


class DevDebtItem(BaseModel):
    id: int
    name: str
    path: str
    size_human: str
    age: str  # e.g. "2y", "8mo"


class DownloadsStat(BaseModel):
    type: str
    percent: int


class ScanResult(BaseModel):
    scan_id: str
    status: Literal["IDLE", "SCANNING", "REVIEW", "SUCCESS"]
    metrics: HudMetrics
    dev_debt: List[DevDebtItem] = Field(default_factory=list)
    docker_reclaimable_human: str = "0 B"
    docker_reclaimable_bytes: int = 0
    downloads_breakdown: List[DownloadsStat] = Field(default_factory=list)
    finished_at: Optional[str] = None


class ExecuteCleanRequest(BaseModel):
    scan_id: str
    selected_dev_debt_ids: List[int] = Field(default_factory=list)
    docker_prune: bool = False
    organize_path: str = "~/Downloads"
    # future: organizer mode, custom rules, etc.


class ExecuteCleanResponse(BaseModel):
    ok: bool
    dry_run: bool
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    reclaimed_estimate_human: str = "0 B"


# -----------------------------------------------------------------------------
# In-memory scan state + websocket fanout
# -----------------------------------------------------------------------------

@dataclass
class ScanState:
    scan_id: str
    status: str = "SCANNING"
    progress: int = 0
    logs: List[str] = field(default_factory=list)
    result: Optional[ScanResult] = None
    ws_clients: List[WebSocket] = field(default_factory=list)


SCAN_STATES: Dict[str, ScanState] = {}


async def _broadcast(scan: ScanState, event: Dict[str, Any]) -> None:
    """Send event to all connected websocket clients."""
    dead: List[WebSocket] = []
    for ws in scan.ws_clients:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            scan.ws_clients.remove(ws)
        except ValueError:
            pass


def _human_size(num_bytes: int) -> str:
    """Convert bytes to human readable format."""
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _estimate_age(ts_iso: str) -> str:
    """Estimate age from ISO timestamp string."""
    try:
        dt = datetime.fromisoformat(ts_iso)
    except Exception:
        return "?"
    delta = datetime.now() - dt
    days = delta.days
    if days >= 365:
        return f"{days // 365}y"
    if days >= 30:
        return f"{days // 30}mo"
    if days >= 7:
        return f"{days // 7}w"
    return f"{max(days, 1)}d"


def _parse_size_to_bytes(size_str: str) -> int:
    """Parse human-readable size string to bytes."""
    if not size_str or size_str == "N/A":
        return 0
    size_str = size_str.strip().upper()
    multipliers = {
        "B": 1,
        "KB": 1024,
        "K": 1024,
        "MB": 1024 ** 2,
        "M": 1024 ** 2,
        "GB": 1024 ** 3,
        "G": 1024 ** 3,
        "TB": 1024 ** 4,
        "T": 1024 ** 4,
    }
    for suffix, mult in multipliers.items():
        if size_str.endswith(suffix):
            try:
                num = float(size_str[: -len(suffix)].strip())
                return int(num * mult)
            except ValueError:
                return 0
    try:
        return int(float(size_str))
    except ValueError:
        return 0


# -----------------------------------------------------------------------------
# Scan implementation (uses your existing tools)
# -----------------------------------------------------------------------------

async def _run_scan(scan_id: str) -> None:
    """Execute a storage scan in background."""
    cfg = _load_config()

    scan = SCAN_STATES[scan_id]
    tools = TerminalTools(dry_run=True)  # scan operations should never mutate

    async def log(msg: str, progress: Optional[int] = None) -> None:
        scan.logs.append(msg)
        if progress is not None:
            scan.progress = progress
        await _broadcast(scan, {"type": "log", "message": msg})
        if progress is not None:
            await _broadcast(scan, {"type": "progress", "value": scan.progress})

    await log("Initializing deep scan protocols...", 5)
    await asyncio.sleep(0.1)  # Allow WS messages to flush

    # 1) System overview (df top dirs)
    await log("Analyzing storage health...", 15)
    sys_overview = tools.get_system_overview()
    disk = sys_overview.get("disk", {}) or {}
    await asyncio.sleep(0.1)

    # 2) Docker usage
    await log("Inspecting Docker registry...", 30)
    docker = tools.get_docker_usage()
    await asyncio.sleep(0.1)

    # 3) Dev debt discovery (lightweight heuristic)
    await log("Detecting developer artifacts...", 45)
    scan_paths = cfg.get("scan_paths", {})
    workspace_paths = scan_paths.get("workspace", ["~/workspace", "~/projects"])
    primary_paths = scan_paths.get("primary", ["~/Downloads", "~/Desktop"])

    dev_debt: List[DevDebtItem] = []
    next_id = 1

    # Find common "heavy" folders
    heavy_names = ["node_modules", ".venv", "venv", "dist", "build", "target", "__pycache__"]
    all_scan_paths = workspace_paths + primary_paths

    for base in all_scan_paths:
        base_exp = os.path.expanduser(base)
        if not os.path.exists(base_exp):
            continue
        # search only a couple levels to avoid huge scans
        for name in heavy_names:
            matches = tools.find_files(base, pattern=name, file_type="d", max_depth=4)
            for m in matches[:30]:
                if m.get("error"):
                    continue
                age = _estimate_age(m.get("modified", ""))
                dev_debt.append(
                    DevDebtItem(
                        id=next_id,
                        name=m.get("name", name),
                        path=m.get("path", ""),
                        size_human=m.get("size_human", "N/A"),
                        age=age,
                    )
                )
                next_id += 1
        # cap to keep UI responsive
        if len(dev_debt) > 60:
            dev_debt = dev_debt[:60]
            break
    await asyncio.sleep(0.1)

    await log("Scanning Downloads for file categories...", 65)

    # 4) Downloads breakdown (via classifier)
    # Use first existing path from config, fallback to ~/Downloads or ~
    downloads_path = None
    for scan_path in primary_paths:
        expanded = os.path.expanduser(scan_path)
        if os.path.exists(expanded) and os.path.isdir(expanded):
            downloads_path = expanded
            break
    if not downloads_path:
        # Fallback to ~/Downloads or home
        for fb in [os.path.expanduser("~/Downloads"), os.path.expanduser("~")]:
            if os.path.exists(fb) and os.path.isdir(fb):
                downloads_path = fb
                break

    downloads_breakdown: List[DownloadsStat] = []

    if downloads_path and os.path.exists(downloads_path):
        classifier = FileClassifier()
        try:
            classifications = classifier.classify_directory(downloads_path)
            # map to UI buckets
            buckets = {"Images": 0, "Installers": 0, "Archives": 0, "Docs": 0, "Other": 0}
            for c in classifications:
                cat = (getattr(c, "category", "") or "").lower()
                if cat in ("image", "images"):
                    buckets["Images"] += 1
                elif cat in ("installer", "installers", "application"):
                    buckets["Installers"] += 1
                elif cat in ("archive", "archives"):
                    buckets["Archives"] += 1
                elif cat in ("document", "documents"):
                    buckets["Docs"] += 1
                else:
                    buckets["Other"] += 1
            total = sum(buckets.values()) or 1
            downloads_breakdown = [
                DownloadsStat(type=k, percent=int(round(v * 100 / total)))
                for k, v in buckets.items()
            ]
        except Exception as e:
            await log(f"Warning: Could not classify downloads: {e}", None)
            downloads_breakdown = [
                DownloadsStat(type="Images", percent=0),
                DownloadsStat(type="Installers", percent=0),
                DownloadsStat(type="Archives", percent=0),
                DownloadsStat(type="Docs", percent=0),
                DownloadsStat(type="Other", percent=100),
            ]
    else:
        downloads_breakdown = [
            DownloadsStat(type="Images", percent=0),
            DownloadsStat(type="Installers", percent=0),
            DownloadsStat(type="Archives", percent=0),
            DownloadsStat(type="Docs", percent=0),
            DownloadsStat(type="Other", percent=0),
        ]
    await asyncio.sleep(0.1)

    await log("Heuristic analysis complete. Waste identified.", 90)

    # 5) Compute HUD + Docker reclaimable
    used_percent = 0.0
    total_h = disk.get("total", "N/A")
    free_h = disk.get("available", "N/A")
    try:
        used_percent = float(str(disk.get("percent_used", "0")).replace("%", ""))
    except Exception:
        used_percent = 0.0

    # Docker reclaimable parsing
    reclaimable_bytes = 0
    reclaimable_h = "0 B"
    if isinstance(docker, dict) and not docker.get("error"):
        # Try to extract reclaimable info from docker system df output
        for key in ["images", "containers", "volumes"]:
            item = docker.get(key)
            if isinstance(item, dict) and "Reclaimable" in item:
                reclaim_str = item.get("Reclaimable", "0B")
                reclaimable_bytes += _parse_size_to_bytes(reclaim_str.split()[0] if reclaim_str else "0")
        if reclaimable_bytes > 0:
            reclaimable_h = _human_size(reclaimable_bytes)

    # Waste estimate = dev debt sizes + docker reclaimable
    total_waste_bytes = reclaimable_bytes
    for item in dev_debt:
        total_waste_bytes += _parse_size_to_bytes(item.size_human)

    waste_h = _human_size(total_waste_bytes) if total_waste_bytes > 0 else "0 B"

    result = ScanResult(
        scan_id=scan_id,
        status="REVIEW",
        metrics=HudMetrics(
            storage_used_percent=used_percent,
            free_human=str(free_h),
            total_human=str(total_h),
            waste_human=str(waste_h),
        ),
        dev_debt=dev_debt,
        docker_reclaimable_human=reclaimable_h,
        docker_reclaimable_bytes=reclaimable_bytes,
        downloads_breakdown=downloads_breakdown,
        finished_at=datetime.now().isoformat(),
    )

    scan.status = "REVIEW"
    scan.progress = 100
    scan.result = result

    await _broadcast(scan, {"type": "status", "value": "REVIEW"})
    await _broadcast(scan, {"type": "progress", "value": 100})
    await log("Scan complete. Ready for review.", 100)


# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------

app = FastAPI(
    title="StoragePilot Dashboard API",
    description="Backend API for the StoragePilot React/Tailwind dashboard UI",
    version="1.0.0",
)

# CORS: allow your static HTML to call localhost API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include AI Copilot router
try:
    from api.copilot import router as copilot_router
    app.include_router(copilot_router)
except ImportError as e:
    print(f"Warning: Could not load copilot API: {e}")


# -----------------------------------------------------------------------------
# Static file serving (for index.html)
# -----------------------------------------------------------------------------

STATIC_DIR = PROJECT_ROOT / "ui" / "static"


@app.on_event("startup")
async def startup_event():
    """Create static directory if it doesn't exist."""
    STATIC_DIR.mkdir(parents=True, exist_ok=True)


# Serve static files if the directory exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_index():
    """Serve the main dashboard HTML."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "StoragePilot API running. Place index.html in ui/static/"}


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/health")
def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"ok": True, "time": datetime.now().isoformat(), "version": "1.0.0"}


@app.get("/api/config", response_model=UiConfig)
def get_config() -> UiConfig:
    """Get current configuration."""
    cfg = _load_config()
    llm = cfg.get("llm", {})
    scan_paths = cfg.get("scan_paths", {})
    safety = cfg.get("safety", {})
    return UiConfig(
        provider=llm.get("provider", "ollama"),
        model=llm.get("model", "qwen2.5:0.5b"),
        baseUrl=llm.get("base_url", "http://127.0.0.1:11434/v1"),
        scanPrimary=", ".join(scan_paths.get("primary", [])),
        scanWorkspace=", ".join(scan_paths.get("workspace", [])),
        dryRun=bool(safety.get("dry_run", True)),
        approval=bool(safety.get("require_approval", True)),
        backup=bool(safety.get("backup_before_delete", True)),
        matrixCode="",
    )


@app.put("/api/config")
def put_config(new_cfg: UiConfig) -> Dict[str, Any]:
    """Save configuration."""
    cfg = _load_config()
    cfg["llm"] = cfg.get("llm", {})
    cfg["llm"]["provider"] = new_cfg.provider
    cfg["llm"]["model"] = new_cfg.model
    cfg["llm"]["base_url"] = new_cfg.baseUrl

    cfg["scan_paths"] = cfg.get("scan_paths", {})
    cfg["scan_paths"]["primary"] = [p.strip() for p in new_cfg.scanPrimary.split(",") if p.strip()]
    cfg["scan_paths"]["workspace"] = [p.strip() for p in new_cfg.scanWorkspace.split(",") if p.strip()]

    cfg["safety"] = cfg.get("safety", {})
    cfg["safety"]["dry_run"] = bool(new_cfg.dryRun)
    cfg["safety"]["require_approval"] = bool(new_cfg.approval)
    cfg["safety"]["backup_before_delete"] = bool(new_cfg.backup)
    _save_config(cfg)
    return {"ok": True}


@app.post("/api/scan/start", response_model=StartScanResponse)
async def start_scan() -> StartScanResponse:
    """Start a new storage scan."""
    scan_id = uuid.uuid4().hex
    SCAN_STATES[scan_id] = ScanState(scan_id=scan_id, status="SCANNING", progress=0, logs=[])
    # Fire and forget background task
    asyncio.create_task(_run_scan(scan_id))
    return StartScanResponse(scan_id=scan_id)


@app.get("/api/scan/{scan_id}", response_model=ScanResult)
def get_scan(scan_id: str) -> ScanResult:
    """Get scan results by ID."""
    scan = SCAN_STATES.get(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="scan_id not found")
    if not scan.result:
        # return a partial view while scanning
        return ScanResult(
            scan_id=scan_id,
            status="SCANNING",
            metrics=HudMetrics(
                storage_used_percent=0.0,
                free_human="N/A",
                total_human="N/A",
                waste_human="N/A",
            ),
            dev_debt=[],
            docker_reclaimable_human="0 B",
            docker_reclaimable_bytes=0,
            downloads_breakdown=[],
            finished_at=None,
        )
    return scan.result


@app.get("/api/scan/{scan_id}/logs")
def get_scan_logs(scan_id: str, offset: int = 0) -> Dict[str, Any]:
    """Get scan logs (for polling instead of WebSocket)."""
    scan = SCAN_STATES.get(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="scan_id not found")
    return {
        "scan_id": scan_id,
        "status": scan.status,
        "progress": scan.progress,
        "logs": scan.logs[offset:],
        "total_logs": len(scan.logs),
    }


@app.websocket("/api/scan/ws/{scan_id}")
async def scan_ws(websocket: WebSocket, scan_id: str):
    """WebSocket endpoint for real-time scan updates."""
    scan = SCAN_STATES.get(scan_id)
    if not scan:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    scan.ws_clients.append(websocket)

    # Send initial snapshot
    await websocket.send_text(json.dumps({"type": "status", "value": scan.status}))
    await websocket.send_text(json.dumps({"type": "progress", "value": scan.progress}))
    for line in scan.logs[-50:]:
        await websocket.send_text(json.dumps({"type": "log", "message": line}))

    try:
        while True:
            # keepalive / ignore client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        try:
            scan.ws_clients.remove(websocket)
        except ValueError:
            pass


@app.get("/api/fs/list")
def fs_list(path: str = Query("~")) -> Dict[str, Any]:
    """List directories in a path (for folder browser)."""
    p = os.path.expanduser(path)
    p = os.path.abspath(p)

    # If path doesn't exist, fall back to a valid directory
    if not os.path.exists(p) or not os.path.isdir(p):
        # Try fallbacks: config paths, ~/Downloads, home directory
        cfg = _load_config()
        fallbacks = []
        for scan_path in cfg.get("scan_paths", {}).get("primary", []):
            fallbacks.append(os.path.expanduser(scan_path))
        fallbacks.extend([
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~"),
            "/tmp",
        ])
        for fb in fallbacks:
            if os.path.exists(fb) and os.path.isdir(fb):
                p = fb
                break
        else:
            raise HTTPException(status_code=400, detail="No valid directory found")

    items = []
    try:
        for entry in os.scandir(p):
            if entry.is_dir(follow_symlinks=False):
                items.append({"name": entry.name, "path": entry.path})
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    items.sort(key=lambda x: x["name"].lower())
    return {"path": p, "directories": items}


@app.post("/api/clean/execute", response_model=ExecuteCleanResponse)
def execute_clean(req: ExecuteCleanRequest) -> ExecuteCleanResponse:
    """Execute cleaning actions based on scan results."""
    scan = SCAN_STATES.get(req.scan_id)
    if not scan or not scan.result:
        raise HTTPException(status_code=404, detail="scan_id not found or not finished")

    cfg = _load_config()
    safety = cfg.get("safety", {})
    dry_run = bool(safety.get("dry_run", True))
    backup = bool(safety.get("backup_before_delete", True))

    tools = TerminalTools(dry_run=dry_run)

    actions: List[Dict[str, Any]] = []
    total_reclaimed = 0

    # 1) Delete selected dev debt directories
    debt_by_id = {d.id: d for d in scan.result.dev_debt}
    for did in req.selected_dev_debt_ids:
        item = debt_by_id.get(did)
        if not item:
            continue
        size_bytes = _parse_size_to_bytes(item.size_human)
        res = tools.delete_file(item.path, backup=backup)
        actions.append({
            "action": "delete_dev_debt",
            "path": item.path,
            "size_human": item.size_human,
            "dry_run": dry_run,
            "success": bool(getattr(res, "success", True)),
        })
        if getattr(res, "success", True):
            total_reclaimed += size_bytes

    # 2) Docker prune
    if req.docker_prune:
        docker_res = tools.clean_docker(prune_all=False)
        actions.append({
            "action": "docker_prune",
            "dry_run": dry_run,
            "result": docker_res,
        })
        # Add docker reclaimable to total
        total_reclaimed += scan.result.docker_reclaimable_bytes

    # 3) Organizer (optional - safe stub for now)
    if req.organize_path:
        actions.append({
            "action": "organize_preview",
            "target": req.organize_path,
            "note": "File organization available in future version.",
        })

    # Mark scan success for UI
    scan.status = "SUCCESS"
    scan.result.status = "SUCCESS"
    scan.result.finished_at = datetime.now().isoformat()

    return ExecuteCleanResponse(
        ok=True,
        dry_run=dry_run,
        actions=actions,
        reclaimed_estimate_human=_human_size(total_reclaimed),
    )


@app.post("/api/clean/plan")
def get_clean_plan(req: ExecuteCleanRequest) -> Dict[str, Any]:
    """Get a cleaning plan without executing (for approval flow)."""
    scan = SCAN_STATES.get(req.scan_id)
    if not scan or not scan.result:
        raise HTTPException(status_code=404, detail="scan_id not found or not finished")

    cfg = _load_config()
    safety = cfg.get("safety", {})
    dry_run = bool(safety.get("dry_run", True))

    debt_by_id = {d.id: d for d in scan.result.dev_debt}
    planned_actions = []
    total_estimate = 0

    # Plan dev debt deletions
    for did in req.selected_dev_debt_ids:
        item = debt_by_id.get(did)
        if not item:
            continue
        size_bytes = _parse_size_to_bytes(item.size_human)
        planned_actions.append({
            "action": "delete_dev_debt",
            "path": item.path,
            "size_human": item.size_human,
            "size_bytes": size_bytes,
        })
        total_estimate += size_bytes

    # Plan docker prune
    if req.docker_prune:
        planned_actions.append({
            "action": "docker_prune",
            "size_human": scan.result.docker_reclaimable_human,
            "size_bytes": scan.result.docker_reclaimable_bytes,
        })
        total_estimate += scan.result.docker_reclaimable_bytes

    return {
        "scan_id": req.scan_id,
        "dry_run": dry_run,
        "planned_actions": planned_actions,
        "total_estimate_bytes": total_estimate,
        "total_estimate_human": _human_size(total_estimate),
        "requires_approval": bool(safety.get("require_approval", True)),
    }


# -----------------------------------------------------------------------------
# Run with: uvicorn ui.dashboard:app --host 127.0.0.1 --port 8000 --reload
# Or use: make api
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
