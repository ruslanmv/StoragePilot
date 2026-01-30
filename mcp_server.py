#!/usr/bin/env python3
"""
StoragePilot MCP Server v1.2.0
==============================

A Model Context Protocol (MCP) server that exposes StoragePilot tools for LLM agents.

Transports:
- stdio (default): for Claude Desktop / local MCP clients
- HTTP: for MCP Inspector, Context Forge, MCP Gateway
  - Streamable HTTP (recommended, /mcp endpoint)
  - SSE (legacy, /sse endpoint)

Compatibility:
- MCP SDK >= 1.0.0
- MCP Inspector (latest)
- Context Forge
- MCP Gateway
- Claude Desktop

Usage:
    # stdio transport (for Claude Desktop)
    python mcp_server.py
    python mcp_server.py --execute

    # HTTP transport (for MCP Inspector / Context Forge)
    python mcp_server.py --http
    python mcp_server.py --http --host 0.0.0.0 --port 9000
    python mcp_server.py --http --execute

Endpoints (HTTP mode):
    Streamable HTTP (recommended):
      POST /mcp              - Main MCP endpoint
      GET  /mcp              - SSE stream (optional)
      DELETE /mcp            - Session termination

    Legacy SSE:
      GET  /sse              - SSE connection
      POST /messages         - Message posting

    Utility:
      GET  /health           - Health check
      GET  /info             - Server information
      GET  /                 - Root info
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import signal
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("storagepilot-mcp")

# -----------------------------------------------------------------------------
# MCP SDK imports
# -----------------------------------------------------------------------------
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    MCP_AVAILABLE = True
except ImportError as e:
    logger.error(f"MCP SDK import failed: {e}")
    logger.error("Install with: pip install --upgrade 'anyio>=4.0.0' 'mcp[cli]>=1.0.0'")
    MCP_AVAILABLE = False
    raise SystemExit(1)

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
SERVER_NAME = "storagepilot"
SERVER_VERSION = "1.2.0"
SERVER_DESCRIPTION = "StoragePilot MCP Server - AI-powered storage management"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000


# =============================================================================
# Data Classes
# =============================================================================

class ActionType(str, Enum):
    """Types of file actions."""
    MOVE = "move"
    DELETE = "delete"
    CREATE = "create"
    CLEAN = "clean"


@dataclass
class ActionLog:
    """Log entry for a file operation."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    action_type: str = ""
    source: str = ""
    destination: str | None = None
    size_bytes: int = 0
    success: bool = False
    dry_run: bool = True
    reversible: bool = False
    undo_command: str | None = None
    error: str | None = None


@dataclass
class FileClassification:
    """Classification result for a file."""
    path: str = ""
    filename: str = ""
    extension: str = ""
    category: str = "unknown"
    subcategory: str = ""
    confidence: float = 0.0
    suggested_destination: str = ""
    action: str = "review"
    reason: str = ""
    is_duplicate: bool = False
    duplicate_of: str | None = None


# =============================================================================
# Terminal Tools Implementation
# =============================================================================

class TerminalTools:
    """File system operations with dry-run support."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self._action_history: list[ActionLog] = []

    def _human_readable_size(self, size_bytes: int) -> str:
        """Convert bytes to human-readable format."""
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if abs(size_bytes) < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} EB"

    def get_disk_usage(self, path: str) -> dict[str, Any]:
        """Get disk usage for a directory."""
        path_obj = Path(path).expanduser().resolve()

        if not path_obj.exists():
            return {"error": f"Path does not exist: {path}", "path": str(path_obj)}

        if not path_obj.is_dir():
            stat = path_obj.stat()
            return {
                "path": str(path_obj),
                "type": "file",
                "size_bytes": stat.st_size,
                "size_human": self._human_readable_size(stat.st_size),
            }

        total_size = 0
        items: list[dict[str, Any]] = []
        errors: list[str] = []

        try:
            for item in path_obj.iterdir():
                try:
                    if item.is_file():
                        size = item.stat().st_size
                    elif item.is_dir():
                        size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                    else:
                        continue

                    total_size += size
                    items.append({
                        "name": item.name,
                        "path": str(item),
                        "type": "directory" if item.is_dir() else "file",
                        "size_bytes": size,
                        "size_human": self._human_readable_size(size),
                    })
                except (PermissionError, OSError) as e:
                    errors.append(f"{item.name}: {e}")
        except PermissionError as e:
            return {"error": f"Permission denied: {e}", "path": str(path_obj)}

        items.sort(key=lambda x: x["size_bytes"], reverse=True)

        return {
            "path": str(path_obj),
            "total_size_bytes": total_size,
            "total_size_human": self._human_readable_size(total_size),
            "item_count": len(items),
            "items": items[:50],
            "errors": errors[:10] if errors else None,
        }

    def find_files(
        self,
        path: str,
        pattern: str | None = None,
        min_size: str | None = None,
        modified_days: int | None = None,
        file_type: str = "f",
        max_depth: int | None = None,
    ) -> list[dict[str, Any]]:
        """Find files matching criteria."""
        path_obj = Path(path).expanduser().resolve()
        results: list[dict[str, Any]] = []

        if not path_obj.exists():
            return results

        min_bytes = 0
        if min_size:
            size_map = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
            try:
                if min_size[-1].upper() in size_map:
                    min_bytes = int(float(min_size[:-1]) * size_map[min_size[-1].upper()])
                else:
                    min_bytes = int(min_size)
            except (ValueError, IndexError):
                min_bytes = 0

        cutoff_time = None
        if modified_days:
            cutoff_time = datetime.now().timestamp() - (modified_days * 86400)

        def should_include(p: Path, depth: int) -> bool:
            if max_depth and depth > max_depth:
                return False
            if file_type == "f" and not p.is_file():
                return False
            if file_type == "d" and not p.is_dir():
                return False
            if pattern and pattern not in p.name:
                return False
            return True

        def walk_path(p: Path, depth: int = 0):
            if max_depth and depth > max_depth:
                return
            try:
                for item in p.iterdir():
                    try:
                        if should_include(item, depth):
                            stat = item.stat()
                            if min_bytes and stat.st_size < min_bytes:
                                continue
                            if cutoff_time and stat.st_mtime > cutoff_time:
                                continue
                            results.append({
                                "path": str(item),
                                "name": item.name,
                                "size_bytes": stat.st_size,
                                "size_human": self._human_readable_size(stat.st_size),
                                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            })
                        if item.is_dir():
                            walk_path(item, depth + 1)
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                pass

        walk_path(path_obj)
        results.sort(key=lambda x: x["size_bytes"], reverse=True)
        return results[:100]

    def get_system_overview(self) -> dict[str, Any]:
        """Get system storage overview."""
        import shutil

        result: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "disk_usage": {},
            "home_directory": {},
        }

        try:
            total, used, free = shutil.disk_usage("/")
            result["disk_usage"] = {
                "total_bytes": total,
                "total_human": self._human_readable_size(total),
                "used_bytes": used,
                "used_human": self._human_readable_size(used),
                "free_bytes": free,
                "free_human": self._human_readable_size(free),
                "percent_used": round((used / total) * 100, 1),
            }
        except OSError as e:
            result["disk_usage"] = {"error": str(e)}

        home = Path.home()
        try:
            home_size = sum(f.stat().st_size for f in home.rglob("*") if f.is_file())
            result["home_directory"] = {
                "path": str(home),
                "size_bytes": home_size,
                "size_human": self._human_readable_size(home_size),
            }
        except (PermissionError, OSError) as e:
            result["home_directory"] = {"path": str(home), "error": str(e)}

        return result

    def get_docker_usage(self) -> dict[str, Any]:
        """Get Docker storage usage."""
        import subprocess

        result: dict[str, Any] = {"available": False}

        try:
            subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=10)
            result["available"] = True

            proc = subprocess.run(
                ["docker", "system", "df", "--format", "json"],
                capture_output=True, text=True, timeout=30,
            )

            if proc.returncode == 0:
                lines = proc.stdout.strip().split("\n")
                usage = []
                for line in lines:
                    if line.strip():
                        try:
                            usage.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                result["usage"] = usage

        except FileNotFoundError:
            result["error"] = "Docker not installed"
        except subprocess.TimeoutExpired:
            result["error"] = "Docker command timed out"
        except subprocess.CalledProcessError as e:
            result["error"] = f"Docker error: {e}"

        return result

    def calculate_file_hash(self, file_path: str, algorithm: str = "md5") -> str | None:
        """Calculate file hash."""
        path = Path(file_path).expanduser().resolve()

        if not path.is_file():
            return None

        try:
            try:
                import xxhash
                hasher = xxhash.xxh64()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        hasher.update(chunk)
                return hasher.hexdigest()
            except ImportError:
                pass

            hasher = hashlib.md5()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()

        except (PermissionError, OSError):
            return None

    def move_file(self, source: str, destination: str) -> ActionLog:
        """Move a file."""
        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()

        log = ActionLog(
            action_type=ActionType.MOVE.value,
            source=str(src),
            destination=str(dst),
            dry_run=self.dry_run,
        )

        if not src.exists():
            log.error = f"Source does not exist: {src}"
            return log

        try:
            log.size_bytes = src.stat().st_size if src.is_file() else 0

            if self.dry_run:
                log.success = True
                log.reversible = True
                log.undo_command = f"mv '{dst}' '{src}'"
            else:
                if dst.is_dir():
                    dst = dst / src.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dst)
                log.success = True
                log.reversible = True
                log.undo_command = f"mv '{dst}' '{src}'"

        except (PermissionError, OSError) as e:
            log.error = str(e)

        self._action_history.append(log)
        return log

    def delete_file(self, path: str, backup: bool = True) -> ActionLog:
        """Delete a file."""
        file_path = Path(path).expanduser().resolve()

        log = ActionLog(
            action_type=ActionType.DELETE.value,
            source=str(file_path),
            dry_run=self.dry_run,
        )

        if not file_path.exists():
            log.error = f"File does not exist: {file_path}"
            return log

        try:
            log.size_bytes = file_path.stat().st_size if file_path.is_file() else 0

            if self.dry_run:
                log.success = True
                if backup:
                    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                    log.reversible = True
                    log.undo_command = f"mv '{backup_path}' '{file_path}'"
            else:
                if backup:
                    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                    file_path.rename(backup_path)
                    log.reversible = True
                    log.undo_command = f"mv '{backup_path}' '{file_path}'"
                else:
                    if file_path.is_dir():
                        import shutil
                        shutil.rmtree(file_path)
                    else:
                        file_path.unlink()
                log.success = True

        except (PermissionError, OSError) as e:
            log.error = str(e)

        self._action_history.append(log)
        return log

    def create_directory(self, path: str) -> ActionLog:
        """Create a directory."""
        dir_path = Path(path).expanduser().resolve()

        log = ActionLog(
            action_type=ActionType.CREATE.value,
            source=str(dir_path),
            dry_run=self.dry_run,
        )

        if dir_path.exists():
            log.error = f"Path already exists: {dir_path}"
            return log

        try:
            if self.dry_run:
                log.success = True
                log.reversible = True
                log.undo_command = f"rmdir '{dir_path}'"
            else:
                dir_path.mkdir(parents=True, exist_ok=True)
                log.success = True
                log.reversible = True
                log.undo_command = f"rmdir '{dir_path}'"

        except (PermissionError, OSError) as e:
            log.error = str(e)

        self._action_history.append(log)
        return log

    def clean_docker(self, prune_all: bool = False) -> dict[str, Any]:
        """Clean Docker resources."""
        import subprocess

        result: dict[str, Any] = {
            "dry_run": self.dry_run,
            "prune_all": prune_all,
            "actions": [],
        }

        try:
            subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=10)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            result["error"] = f"Docker not available: {e}"
            return result

        if self.dry_run:
            result["actions"].append({
                "type": "prune",
                "target": "all" if prune_all else "dangling",
                "status": "would_execute",
            })
            return result

        try:
            if prune_all:
                proc = subprocess.run(
                    ["docker", "system", "prune", "-af"],
                    capture_output=True, text=True, timeout=300,
                )
            else:
                proc = subprocess.run(
                    ["docker", "system", "prune", "-f"],
                    capture_output=True, text=True, timeout=300,
                )

            result["actions"].append({
                "type": "prune",
                "target": "all" if prune_all else "dangling",
                "status": "completed" if proc.returncode == 0 else "failed",
                "output": proc.stdout,
                "errors": proc.stderr if proc.stderr else None,
            })

        except subprocess.TimeoutExpired:
            result["error"] = "Docker prune timed out"

        return result


# =============================================================================
# File Classifier Implementation
# =============================================================================

class FileClassifier:
    """Classify files by type and suggest organization."""

    CATEGORY_MAP: dict[str, dict[str, Any]] = {
        "documents": {
            "extensions": [".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx"],
            "destination": "Documents",
        },
        "images": {
            "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff", ".raw"],
            "destination": "Pictures",
        },
        "videos": {
            "extensions": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"],
            "destination": "Videos",
        },
        "audio": {
            "extensions": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
            "destination": "Music",
        },
        "archives": {
            "extensions": [".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".xz"],
            "destination": "Archives",
        },
        "code": {
            "extensions": [".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".go", ".rs", ".rb", ".php"],
            "destination": "Code",
        },
        "data": {
            "extensions": [".json", ".xml", ".yaml", ".yml", ".csv", ".sql", ".db", ".sqlite"],
            "destination": "Data",
        },
    }

    def classify_file(self, file_path: str, file_hash: str | None = None) -> FileClassification:
        """Classify a single file."""
        path = Path(file_path)

        classification = FileClassification(
            path=str(path),
            filename=path.name,
            extension=path.suffix.lower(),
        )

        for category, config in self.CATEGORY_MAP.items():
            if classification.extension in config["extensions"]:
                classification.category = category
                classification.suggested_destination = config["destination"]
                classification.confidence = 0.9
                classification.action = "move"
                classification.reason = f"File extension matches {category} category"
                break
        else:
            classification.category = "unknown"
            classification.action = "review"
            classification.reason = "Unknown file type"
            classification.confidence = 0.5

        return classification

    def classify_directory(self, directory_path: str) -> list[FileClassification]:
        """Classify all files in a directory."""
        path = Path(directory_path).expanduser().resolve()
        classifications: list[FileClassification] = []

        if not path.is_dir():
            return classifications

        try:
            for file_path in path.iterdir():
                if file_path.is_file():
                    classifications.append(self.classify_file(str(file_path)))
        except (PermissionError, OSError):
            pass

        return classifications

    def generate_organization_plan(self, classifications: list[FileClassification]) -> dict[str, Any]:
        """Generate an organization plan from classifications."""
        plan: dict[str, Any] = {
            "total_files": len(classifications),
            "by_action": {"move": [], "delete": [], "review": []},
            "by_category": {},
        }

        for c in classifications:
            if c.action in plan["by_action"]:
                plan["by_action"][c.action].append(c.path)
            if c.category not in plan["by_category"]:
                plan["by_category"][c.category] = []
            plan["by_category"][c.category].append(c.path)

        return plan


# =============================================================================
# MCP Server Implementation
# =============================================================================

def create_server(dry_run: bool = True) -> Server:
    """Create and configure the MCP server with all StoragePilot tools."""
    server = Server(SERVER_NAME)

    terminal_tools = TerminalTools(dry_run=dry_run)
    classifier = FileClassifier()

    tools: list[Tool] = [
        Tool(
            name="scan_directory",
            description="Scan a directory and return disk usage breakdown. Shows total size and per-item sizes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to scan (e.g., '~/Downloads', '/home/user/Documents')",
                    }
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="find_large_files",
            description="Find files larger than a specified size in a directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to search"},
                    "min_size": {
                        "type": "string",
                        "description": "Minimum file size (e.g., '100M', '1G', '500K'). Default: '100M'",
                        "default": "100M",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="find_old_files",
            description="Find files not modified within a specified number of days.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to search"},
                    "days": {
                        "type": "integer",
                        "description": "Number of days since last modification. Default: 90",
                        "default": 90,
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="find_developer_artifacts",
            description="Find developer artifacts like node_modules, .venv, __pycache__, build directories that can be safely cleaned.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_path": {
                        "type": "string",
                        "description": "Workspace directory to search for artifacts",
                    }
                },
                "required": ["workspace_path"],
            },
        ),
        Tool(
            name="get_system_overview",
            description="Get overall system storage information including disk usage and largest directories.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_docker_usage",
            description="Get Docker storage usage breakdown including images, containers, volumes, and build cache.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="classify_files",
            description="Classify all files in a directory and generate an organization plan with move/delete/review recommendations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "Directory containing files to classify",
                    }
                },
                "required": ["directory_path"],
            },
        ),
        Tool(
            name="classify_single_file",
            description="Classify a single file and get organization recommendation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to classify",
                    }
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="detect_duplicates",
            description="Find duplicate files in a directory using content hashing (MD5).",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "Directory to scan for duplicates",
                    }
                },
                "required": ["directory_path"],
            },
        ),
        Tool(
            name="move_file",
            description=(
                "Move a file to a new location. "
                + ("[DRY-RUN MODE: Will simulate only]" if dry_run else "[EXECUTE MODE: Will perform actual move]")
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source file path"},
                    "destination": {"type": "string", "description": "Destination path (file or directory)"},
                },
                "required": ["source", "destination"],
            },
        ),
        Tool(
            name="delete_file",
            description=(
                "Delete a file (with backup by default). "
                + ("[DRY-RUN MODE: Will simulate only]" if dry_run else "[EXECUTE MODE: Will perform actual deletion]")
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to delete"},
                    "backup": {
                        "type": "boolean",
                        "description": "Create backup before deletion. Default: true",
                        "default": True,
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="create_directory",
            description=(
                "Create a new directory (including parent directories). "
                + ("[DRY-RUN MODE: Will simulate only]" if dry_run else "[EXECUTE MODE: Will create directory]")
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create"}
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="clean_docker",
            description=(
                "Clean Docker resources (dangling images, stopped containers, unused volumes). "
                + ("[DRY-RUN MODE: Will simulate only]" if dry_run else "[EXECUTE MODE: Will clean Docker]")
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prune_all": {
                        "type": "boolean",
                        "description": "If true, prune ALL unused resources (more aggressive). Default: false",
                        "default": False,
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="calculate_file_hash",
            description="Calculate the hash of a file (uses xxhash if available, falls back to MD5).",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file to hash"}
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="get_server_info",
            description="Get information about the MCP server status and configuration.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        logger.debug(f"Tool call: {name} with arguments: {arguments}")
        try:
            result = await handle_tool_call(name, arguments, terminal_tools, classifier, dry_run)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        except Exception as e:
            logger.error(f"Tool error: {name} - {e}")
            error_result = {
                "error": str(e),
                "error_type": type(e).__name__,
                "tool": name,
                "arguments": arguments,
            }
            return [TextContent(type="text", text=json.dumps(error_result, indent=2, default=str))]

    return server


async def handle_tool_call(
    name: str,
    arguments: dict,
    terminal_tools: TerminalTools,
    classifier: FileClassifier,
    dry_run: bool,
) -> dict[str, Any]:
    """Route tool calls to appropriate handlers."""

    if name == "scan_directory":
        path = os.path.expanduser(arguments["path"])
        return terminal_tools.get_disk_usage(path)

    if name == "find_large_files":
        path = os.path.expanduser(arguments["path"])
        min_size = arguments.get("min_size", "100M")
        files = terminal_tools.find_files(path=path, min_size=min_size, file_type="f")
        return {"path": path, "min_size": min_size, "count": len(files), "files": files}

    if name == "find_old_files":
        path = os.path.expanduser(arguments["path"])
        days = int(arguments.get("days", 90))
        files = terminal_tools.find_files(path=path, modified_days=days, file_type="f")
        return {"path": path, "days_threshold": days, "count": len(files), "files": files}

    if name == "find_developer_artifacts":
        workspace_path = os.path.expanduser(arguments["workspace_path"])
        return _find_developer_artifacts_impl(terminal_tools, workspace_path)

    if name == "get_system_overview":
        return terminal_tools.get_system_overview()

    if name == "get_docker_usage":
        return terminal_tools.get_docker_usage()

    if name == "classify_files":
        directory_path = os.path.expanduser(arguments["directory_path"])
        classifications = classifier.classify_directory(directory_path)
        plan = classifier.generate_organization_plan(classifications)
        return {
            "directory": directory_path,
            "total_files": len(classifications),
            "classifications": [_classification_to_dict(c) for c in classifications],
            "organization_plan": plan,
        }

    if name == "classify_single_file":
        file_path = os.path.expanduser(arguments["file_path"])
        file_hash = terminal_tools.calculate_file_hash(file_path)
        classification = classifier.classify_file(file_path, file_hash)
        return _classification_to_dict(classification)

    if name == "detect_duplicates":
        directory_path = os.path.expanduser(arguments["directory_path"])
        return _detect_duplicates_impl(terminal_tools, directory_path)

    if name == "move_file":
        source = os.path.expanduser(arguments["source"])
        destination = os.path.expanduser(arguments["destination"])
        action_log = terminal_tools.move_file(source, destination)
        return _action_log_to_dict(action_log)

    if name == "delete_file":
        path = os.path.expanduser(arguments["path"])
        backup = bool(arguments.get("backup", True))
        action_log = terminal_tools.delete_file(path, backup=backup)
        return _action_log_to_dict(action_log)

    if name == "create_directory":
        path = os.path.expanduser(arguments["path"])
        action_log = terminal_tools.create_directory(path)
        return _action_log_to_dict(action_log)

    if name == "clean_docker":
        prune_all = bool(arguments.get("prune_all", False))
        return terminal_tools.clean_docker(prune_all=prune_all)

    if name == "calculate_file_hash":
        file_path = os.path.expanduser(arguments["file_path"])
        file_hash = terminal_tools.calculate_file_hash(file_path)
        algorithm = "xxhash64"
        try:
            import xxhash
        except ImportError:
            algorithm = "md5"
        return {
            "file_path": file_path,
            "hash": file_hash,
            "algorithm": algorithm if file_hash else "failed",
        }

    if name == "get_server_info":
        return {
            "server": SERVER_DESCRIPTION,
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
            "dry_run": dry_run,
            "mode": "preview" if dry_run else "execute",
            "tools_count": 15,
            "categories": {
                "discovery": ["scan_directory", "find_large_files", "find_old_files", "find_developer_artifacts"],
                "system": ["get_system_overview", "get_docker_usage"],
                "classification": ["classify_files", "classify_single_file", "detect_duplicates"],
                "execution": ["move_file", "delete_file", "create_directory", "clean_docker"],
                "utility": ["calculate_file_hash", "get_server_info"],
            },
        }

    raise ValueError(f"Unknown tool: {name}")


# =============================================================================
# Helper Functions
# =============================================================================

def _classification_to_dict(classification: FileClassification) -> dict[str, Any]:
    return {
        "path": classification.path,
        "filename": classification.filename,
        "extension": classification.extension,
        "category": classification.category,
        "subcategory": classification.subcategory,
        "confidence": classification.confidence,
        "suggested_destination": classification.suggested_destination,
        "action": classification.action,
        "reason": classification.reason,
        "is_duplicate": classification.is_duplicate,
        "duplicate_of": classification.duplicate_of,
    }


def _action_log_to_dict(action_log: ActionLog) -> dict[str, Any]:
    result = {
        "timestamp": action_log.timestamp,
        "action_type": action_log.action_type,
        "source": action_log.source,
        "destination": action_log.destination,
        "size_bytes": action_log.size_bytes,
        "success": action_log.success,
        "dry_run": action_log.dry_run,
        "reversible": action_log.reversible,
        "undo_command": action_log.undo_command,
    }
    if action_log.error:
        result["error"] = action_log.error
    return result


def _find_developer_artifacts_impl(terminal_tools: TerminalTools, workspace_path: str) -> dict[str, Any]:
    artifact_patterns = {
        "node_modules": {"pattern": "node_modules", "type": "d", "regenerate": "npm install"},
        "venv": {"pattern": ".venv", "type": "d", "regenerate": "python -m venv .venv && pip install -r requirements.txt"},
        "pycache": {"pattern": "__pycache__", "type": "d", "regenerate": "automatic"},
        "pytest_cache": {"pattern": ".pytest_cache", "type": "d", "regenerate": "automatic"},
        "mypy_cache": {"pattern": ".mypy_cache", "type": "d", "regenerate": "automatic"},
        "build": {"pattern": "build", "type": "d", "regenerate": "varies by project"},
        "dist": {"pattern": "dist", "type": "d", "regenerate": "varies by project"},
        "target": {"pattern": "target", "type": "d", "regenerate": "cargo build"},
        "vendor": {"pattern": "vendor", "type": "d", "regenerate": "go mod vendor"},
    }

    results: dict[str, Any] = {"workspace": workspace_path, "artifacts": {}, "total_size": 0, "total_count": 0}

    for artifact_name, config in artifact_patterns.items():
        try:
            found = terminal_tools.find_files(
                path=workspace_path, pattern=config["pattern"], file_type=config["type"], max_depth=5,
            )
            if not found:
                continue

            total_artifact_size = sum(f.get("size_bytes", 0) for f in found)
            results["artifacts"][artifact_name] = {
                "count": len(found),
                "total_size_bytes": total_artifact_size,
                "total_size_human": terminal_tools._human_readable_size(total_artifact_size),
                "regenerate_command": config["regenerate"],
                "locations": [f["path"] for f in found[:10]],
            }
            results["total_size"] += total_artifact_size
            results["total_count"] += len(found)
        except Exception as e:
            logger.debug(f"Error finding {artifact_name}: {e}")
            continue

    results["total_size_human"] = terminal_tools._human_readable_size(results["total_size"])
    return results


def _detect_duplicates_impl(terminal_tools: TerminalTools, directory_path: str) -> dict[str, Any]:
    hash_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    files_processed = 0
    errors: list[dict[str, Any]] = []

    path = Path(directory_path).expanduser().resolve()
    if not path.exists():
        return {"error": f"Directory not found: {directory_path}"}

    for file_path in path.rglob("*"):
        if not file_path.is_file():
            continue
        try:
            hasher = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()

            st = file_path.stat()
            hash_map[file_hash].append({
                "path": str(file_path),
                "size_bytes": st.st_size,
                "modified": st.st_mtime,
            })
            files_processed += 1
        except (PermissionError, OSError) as e:
            errors.append({"path": str(file_path), "error": str(e)})

    duplicates = {h: files for h, files in hash_map.items() if len(files) > 1}

    recoverable_bytes = 0
    for files in duplicates.values():
        sorted_files = sorted(files, key=lambda x: x["modified"], reverse=True)
        for f in sorted_files[1:]:
            recoverable_bytes += f["size_bytes"]

    return {
        "directory": directory_path,
        "files_processed": files_processed,
        "duplicate_groups": len(duplicates),
        "total_duplicate_files": sum(len(f) for f in duplicates.values()),
        "recoverable_bytes": recoverable_bytes,
        "recoverable_human": terminal_tools._human_readable_size(recoverable_bytes),
        "duplicates": duplicates,
        "errors": errors[:10],
    }


# =============================================================================
# HTTP Transport (Streamable HTTP + SSE)
# =============================================================================

def create_http_app(server: Server, dry_run: bool):
    """
    Create a Starlette ASGI app with both Streamable HTTP and SSE transports.

    Endpoints:
      Streamable HTTP (for MCP Inspector):
        POST /mcp    - Main MCP endpoint
        GET  /mcp    - Optional SSE stream
        DELETE /mcp  - Session termination

      Legacy SSE (for Context Forge):
        GET  /sse         - SSE connection
        POST /messages    - Message posting

      Utility:
        GET  /health      - Health check
        GET  /info        - Server info
        GET  /            - Root
    """
    try:
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        from starlette.responses import JSONResponse
        from starlette.requests import Request
        from starlette.middleware import Middleware
        from starlette.middleware.cors import CORSMiddleware
    except ImportError:
        logger.error("HTTP transport requires starlette. Install with: pip install starlette uvicorn")
        sys.exit(1)

    # Check available transports
    streamable_http_available = False
    sse_available = False

    # Try Streamable HTTP (newer MCP SDK >= 1.8)
    try:
        from mcp.server.streamable_http import StreamableHTTPServerTransport
        streamable_http_available = True
        logger.info("Streamable HTTP transport available")
    except ImportError:
        logger.info("Streamable HTTP transport not available (needs mcp>=1.8)")

    # Try SSE (legacy)
    try:
        from mcp.server.sse import SseServerTransport
        sse_available = True
        logger.info("SSE transport available")
    except ImportError:
        logger.info("SSE transport not available")

    if not streamable_http_available and not sse_available:
        logger.error("No HTTP transports available. Update MCP SDK: pip install 'mcp[cli]>=1.0.0'")
        sys.exit(1)

    # Session storage for Streamable HTTP
    sessions: dict[str, Any] = {}

    # --- Streamable HTTP handlers ---
    async def handle_mcp_streamable(request: Request):
        """Handle Streamable HTTP at /mcp endpoint."""
        if not streamable_http_available:
            return JSONResponse({"error": "Streamable HTTP not available"}, status_code=501)

        from mcp.server.streamable_http import StreamableHTTPServerTransport

        # Create transport for this request
        transport = StreamableHTTPServerTransport(
            mcp_session_timeout_seconds=300,
        )

        try:
            # Handle the request
            response = await transport.handle_request(
                request.scope,
                request.receive,
                request._send,
            )
            return response
        except Exception as e:
            logger.error(f"Streamable HTTP error: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    # Create a raw ASGI handler for Streamable HTTP
    async def mcp_asgi_handler(scope, receive, send):
        """Raw ASGI handler for /mcp endpoint supporting Streamable HTTP."""
        if not streamable_http_available:
            response = JSONResponse({"error": "Streamable HTTP not available"}, status_code=501)
            await response(scope, receive, send)
            return

        from mcp.server.streamable_http import StreamableHTTPServerTransport

        transport = StreamableHTTPServerTransport(
            mcp_session_timeout_seconds=300,
        )

        async def run_server(read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

        try:
            await transport.handle_request(scope, receive, send, run_server)
        except Exception as e:
            logger.error(f"Streamable HTTP error: {e}")
            response = JSONResponse({"error": str(e)}, status_code=500)
            await response(scope, receive, send)

    # --- SSE handlers (legacy) ---
    sse_transport = None
    if sse_available:
        from mcp.server.sse import SseServerTransport
        sse_transport = SseServerTransport("/messages")

    async def handle_sse(scope, receive, send):
        """Handle SSE connection at /sse endpoint."""
        if not sse_transport:
            response = JSONResponse({"error": "SSE not available"}, status_code=501)
            await response(scope, receive, send)
            return

        logger.info(f"SSE connection from {scope.get('client', 'unknown')}")
        try:
            async with sse_transport.connect_sse(scope, receive, send) as streams:
                await server.run(streams[0], streams[1], server.create_initialization_options())
        except Exception as e:
            logger.error(f"SSE error: {e}")

    async def handle_messages(scope, receive, send):
        """Handle POST messages at /messages endpoint."""
        if not sse_transport:
            response = JSONResponse({"error": "SSE not available"}, status_code=501)
            await response(scope, receive, send)
            return

        await sse_transport.handle_post_message(scope, receive, send)

    # --- Utility handlers ---
    async def health_check(request):
        return JSONResponse({
            "status": "healthy",
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "mode": "dry-run" if dry_run else "execute",
            "transports": {
                "streamable_http": streamable_http_available,
                "sse": sse_available,
            },
            "timestamp": datetime.now().isoformat(),
        })

    async def server_info(request):
        return JSONResponse({
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
            "description": SERVER_DESCRIPTION,
            "mode": "dry-run" if dry_run else "execute",
            "endpoints": {
                "streamable_http": "/mcp" if streamable_http_available else None,
                "sse": "/sse" if sse_available else None,
                "messages": "/messages" if sse_available else None,
                "health": "/health",
                "info": "/info",
            },
            "tools_count": 15,
            "mcp_version": "1.0.0",
        })

    async def root_handler(request):
        return JSONResponse({
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
            "description": SERVER_DESCRIPTION,
            "endpoints": {
                "mcp": "/mcp (Streamable HTTP)" if streamable_http_available else None,
                "sse": "/sse (Legacy SSE)" if sse_available else None,
                "health": "/health",
                "info": "/info",
            },
            "connection_instructions": {
                "mcp_inspector": {
                    "url": "http://HOST:PORT/mcp",
                    "transport": "streamable-http",
                } if streamable_http_available else {
                    "url": "http://HOST:PORT/sse",
                    "transport": "sse",
                },
            },
        })

    # Build routes
    routes = [
        Route("/", root_handler, methods=["GET"]),
        Route("/health", health_check, methods=["GET"]),
        Route("/info", server_info, methods=["GET"]),
    ]

    # Add Streamable HTTP endpoint
    if streamable_http_available:
        routes.append(Mount("/mcp", app=mcp_asgi_handler))

    # Add SSE endpoints
    if sse_available:
        routes.append(Mount("/sse", app=handle_sse))
        routes.append(Mount("/messages", app=handle_messages))

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["*"],
        )
    ]

    return Starlette(
        routes=routes,
        middleware=middleware,
        debug=False,
        on_startup=[lambda: logger.info("HTTP server started")],
        on_shutdown=[lambda: logger.info("HTTP server shutting down")],
    )


async def run_http_server(server: Server, dry_run: bool, host: str, port: int):
    """Run the MCP server with HTTP transport."""
    try:
        import uvicorn
    except ImportError:
        logger.error("HTTP transport requires uvicorn. Install with: pip install uvicorn")
        sys.exit(1)

    app = create_http_app(server, dry_run)
    mode_str = "DRY-RUN (preview)" if dry_run else "EXECUTE (live)"
    connect_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host

    # Check which transports are available
    streamable_available = False
    sse_available = False
    try:
        from mcp.server.streamable_http import StreamableHTTPServerTransport
        streamable_available = True
    except ImportError:
        pass
    try:
        from mcp.server.sse import SseServerTransport
        sse_available = True
    except ImportError:
        pass

    print("=" * 65, file=sys.stderr)
    print(f"  StoragePilot MCP Server v{SERVER_VERSION}", file=sys.stderr)
    print(f"  Mode: {mode_str}", file=sys.stderr)
    print("=" * 65, file=sys.stderr)
    print(f"\n  Listening on: http://{host}:{port}", file=sys.stderr)
    print("\n  Available Transports:", file=sys.stderr)
    if streamable_available:
        print(f"    ✓ Streamable HTTP: http://{connect_host}:{port}/mcp", file=sys.stderr)
    else:
        print(f"    ✗ Streamable HTTP: Not available (upgrade mcp SDK)", file=sys.stderr)
    if sse_available:
        print(f"    ✓ Legacy SSE:      http://{connect_host}:{port}/sse", file=sys.stderr)
    else:
        print(f"    ✗ Legacy SSE:      Not available", file=sys.stderr)
    print(f"\n  Utility Endpoints:", file=sys.stderr)
    print(f"    Health: http://{connect_host}:{port}/health", file=sys.stderr)
    print(f"    Info:   http://{connect_host}:{port}/info", file=sys.stderr)
    print("\n  MCP Inspector Connection:", file=sys.stderr)
    if streamable_available:
        print(f"    URL:       http://{connect_host}:{port}/mcp", file=sys.stderr)
        print(f"    Transport: Streamable HTTP", file=sys.stderr)
    elif sse_available:
        print(f"    URL:       http://{connect_host}:{port}/sse", file=sys.stderr)
        print(f"    Transport: SSE", file=sys.stderr)
    if host == "0.0.0.0":
        print(f"\n  Docker: Use http://host.docker.internal:{port}/mcp", file=sys.stderr)
    print("=" * 65, file=sys.stderr)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        proxy_headers=True,
        access_log=True,
        timeout_keep_alive=120,
    )

    server_instance = uvicorn.Server(config)

    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Shutdown signal received")
        server_instance.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    await server_instance.serve()


# =============================================================================
# stdio Transport
# =============================================================================

async def run_stdio_server(server: Server, dry_run: bool):
    """Run the MCP server with stdio transport."""
    mode_str = "DRY-RUN (preview)" if dry_run else "EXECUTE (live)"

    logger.info(f"StoragePilot MCP Server v{SERVER_VERSION}")
    logger.info(f"Mode: {mode_str}")
    logger.info("Transport: stdio")
    logger.info("Waiting for MCP client connection...")
    logger.info("Note: This transport is for MCP clients (Claude Desktop, etc.)")
    logger.info("      For testing, use: make mcp-inspector or make mcp-server-http")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# =============================================================================
# Main Entry Point
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=SERVER_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # stdio transport (for Claude Desktop)
  %(prog)s --execute                # stdio, execute mode
  %(prog)s --http                   # HTTP transport (for MCP Inspector)
  %(prog)s --http --execute         # HTTP, execute mode
  %(prog)s --http --host 0.0.0.0    # HTTP, bind all interfaces

For MCP Inspector:
  1. Start server:  %(prog)s --http --port 9000
  2. Open Inspector and connect to:
     URL: http://127.0.0.1:9000/mcp
     Transport: Streamable HTTP (or SSE if unavailable)
        """,
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--execute", action="store_true", help="Execute mode (actual file changes)")
    mode_group.add_argument("--dry-run", action="store_true", help="Dry-run mode (default, preview only)")

    parser.add_argument("--http", action="store_true", help="HTTP transport (for MCP Inspector)")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help=f"Bind host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port (default: {DEFAULT_PORT})")
    parser.add_argument("--debug", action="store_true", help="Debug logging")

    return parser.parse_args()


async def main():
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    dry_run = not args.execute
    server = create_server(dry_run=dry_run)

    if args.http:
        await run_http_server(server, dry_run, args.host, args.port)
    else:
        await run_stdio_server(server, dry_run)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server shutdown by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
