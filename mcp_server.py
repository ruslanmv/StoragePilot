#!/usr/bin/env python3
"""
StoragePilot MCP Server

A Model Context Protocol (MCP) server that exposes all StoragePilot tools
for use by LLM agents. This centralizes file system operations, classification,
and storage management capabilities.

Usage:
    python mcp_server.py                    # Start server (stdio transport)
    python mcp_server.py --dry-run          # Start in dry-run mode (default)
    python mcp_server.py --execute          # Start in execute mode (allows mutations)

The server exposes tools in these categories:
    - Discovery: scan_directory, find_large_files, find_old_files, find_developer_artifacts
    - System: get_system_overview, get_docker_usage
    - Classification: classify_files, classify_single_file, detect_duplicates
    - Execution: move_file, delete_file, create_directory, clean_docker
    - Utility: calculate_file_hash
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# MCP SDK imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        Tool,
        TextContent,
        CallToolResult,
    )
except ImportError as e:
    print(f"Error: MCP SDK import failed: {e}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Attempting to install/upgrade dependencies...", file=sys.stderr)
    import subprocess
    try:
        # Install/upgrade anyio first (required for mcp.lowlevel), then mcp
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade",
                              "anyio>=4.0.0", "mcp[cli]>=1.0.0"],
                              stdout=sys.stderr, stderr=sys.stderr)
        print("", file=sys.stderr)
        print("Dependencies installed. Please restart the server.", file=sys.stderr)
        sys.exit(0)
    except subprocess.CalledProcessError:
        print("", file=sys.stderr)
        print("Failed to install dependencies. Please run manually:", file=sys.stderr)
        print("  pip install --upgrade 'anyio>=4.0.0' 'mcp[cli]>=1.0.0'", file=sys.stderr)
        sys.exit(1)

# Import StoragePilot tools
sys.path.insert(0, str(Path(__file__).parent))

from tools.terminal import TerminalTools
from tools.classifier import FileClassifier


# =============================================================================
# MCP Server Setup
# =============================================================================

def create_server(dry_run: bool = True) -> Server:
    """Create and configure the MCP server with all StoragePilot tools."""

    server = Server("storagepilot")

    # Initialize tool instances
    terminal_tools = TerminalTools(dry_run=dry_run)
    classifier = FileClassifier()

    # =========================================================================
    # Tool Definitions
    # =========================================================================

    TOOLS = [
        # --- Discovery Tools ---
        Tool(
            name="scan_directory",
            description="Scan a directory and return disk usage breakdown. Shows total size and per-item sizes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to scan (e.g., '~/Downloads', '/home/user/Documents')"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="find_large_files",
            description="Find files larger than a specified size in a directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to search"
                    },
                    "min_size": {
                        "type": "string",
                        "description": "Minimum file size (e.g., '100M', '1G', '500K'). Default: '100M'",
                        "default": "100M"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="find_old_files",
            description="Find files not modified within a specified number of days.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to search"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days since last modification. Default: 90",
                        "default": 90
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="find_developer_artifacts",
            description="Find developer artifacts like node_modules, .venv, __pycache__, build directories that can be safely cleaned.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_path": {
                        "type": "string",
                        "description": "Workspace directory to search for artifacts"
                    }
                },
                "required": ["workspace_path"]
            }
        ),

        # --- System Tools ---
        Tool(
            name="get_system_overview",
            description="Get overall system storage information including disk usage and largest directories.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_docker_usage",
            description="Get Docker storage usage breakdown including images, containers, volumes, and build cache.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),

        # --- Classification Tools ---
        Tool(
            name="classify_files",
            description="Classify all files in a directory and generate an organization plan with move/delete/review recommendations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "Directory containing files to classify"
                    }
                },
                "required": ["directory_path"]
            }
        ),
        Tool(
            name="classify_single_file",
            description="Classify a single file and get organization recommendation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to classify"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="detect_duplicates",
            description="Find duplicate files in a directory using content hashing (MD5).",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "Directory to scan for duplicates"
                    }
                },
                "required": ["directory_path"]
            }
        ),

        # --- Execution Tools (respect dry_run mode) ---
        Tool(
            name="move_file",
            description=f"Move a file to a new location. {'[DRY-RUN MODE: Will simulate only]' if dry_run else '[EXECUTE MODE: Will perform actual move]'}",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source file path"
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination path (file or directory)"
                    }
                },
                "required": ["source", "destination"]
            }
        ),
        Tool(
            name="delete_file",
            description=f"Delete a file (with backup by default). {'[DRY-RUN MODE: Will simulate only]' if dry_run else '[EXECUTE MODE: Will perform actual deletion]'}",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to delete"
                    },
                    "backup": {
                        "type": "boolean",
                        "description": "Create backup before deletion. Default: true",
                        "default": True
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="create_directory",
            description=f"Create a new directory (including parent directories). {'[DRY-RUN MODE: Will simulate only]' if dry_run else '[EXECUTE MODE: Will create directory]'}",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to create"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="clean_docker",
            description=f"Clean Docker resources (dangling images, stopped containers, unused volumes). {'[DRY-RUN MODE: Will simulate only]' if dry_run else '[EXECUTE MODE: Will clean Docker]'}",
            inputSchema={
                "type": "object",
                "properties": {
                    "prune_all": {
                        "type": "boolean",
                        "description": "If true, prune ALL unused resources (more aggressive). Default: false",
                        "default": False
                    }
                },
                "required": []
            }
        ),

        # --- Utility Tools ---
        Tool(
            name="calculate_file_hash",
            description="Calculate the hash of a file (uses xxhash if available, falls back to MD5).",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to hash"
                    }
                },
                "required": ["file_path"]
            }
        ),

        # --- Server Info Tool ---
        Tool(
            name="get_server_info",
            description="Get information about the MCP server status and configuration.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]

    # =========================================================================
    # Tool Handlers
    # =========================================================================

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return list of available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        try:
            result = await handle_tool_call(name, arguments, terminal_tools, classifier, dry_run)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        except Exception as e:
            error_result = {
                "error": str(e),
                "tool": name,
                "arguments": arguments
            }
            return [TextContent(type="text", text=json.dumps(error_result, indent=2))]

    return server


async def handle_tool_call(
    name: str,
    arguments: dict,
    terminal_tools: TerminalTools,
    classifier: FileClassifier,
    dry_run: bool
) -> dict[str, Any]:
    """
    Route tool calls to appropriate handlers.

    All tools return dictionaries that get JSON-serialized.
    """

    # --- Discovery Tools ---

    if name == "scan_directory":
        path = os.path.expanduser(arguments["path"])
        return terminal_tools.get_disk_usage(path)

    elif name == "find_large_files":
        path = os.path.expanduser(arguments["path"])
        min_size = arguments.get("min_size", "100M")
        files = terminal_tools.find_files(
            path=path,
            min_size=min_size,
            file_type="f"
        )
        return {
            "path": path,
            "min_size": min_size,
            "count": len(files),
            "files": files
        }

    elif name == "find_old_files":
        path = os.path.expanduser(arguments["path"])
        days = arguments.get("days", 90)
        files = terminal_tools.find_files(
            path=path,
            modified_days=days,
            file_type="f"
        )
        return {
            "path": path,
            "days_threshold": days,
            "count": len(files),
            "files": files
        }

    elif name == "find_developer_artifacts":
        workspace_path = os.path.expanduser(arguments["workspace_path"])
        artifacts = _find_developer_artifacts_impl(terminal_tools, workspace_path)
        return artifacts

    # --- System Tools ---

    elif name == "get_system_overview":
        return terminal_tools.get_system_overview()

    elif name == "get_docker_usage":
        return terminal_tools.get_docker_usage()

    # --- Classification Tools ---

    elif name == "classify_files":
        directory_path = os.path.expanduser(arguments["directory_path"])
        classifications = classifier.classify_directory(directory_path)
        plan = classifier.generate_organization_plan(classifications)
        return {
            "directory": directory_path,
            "total_files": len(classifications),
            "classifications": [_classification_to_dict(c) for c in classifications],
            "organization_plan": plan
        }

    elif name == "classify_single_file":
        file_path = os.path.expanduser(arguments["file_path"])
        file_hash = terminal_tools.calculate_file_hash(file_path)
        classification = classifier.classify_file(file_path, file_hash)
        return _classification_to_dict(classification)

    elif name == "detect_duplicates":
        directory_path = os.path.expanduser(arguments["directory_path"])
        duplicates = _detect_duplicates_impl(terminal_tools, directory_path)
        return duplicates

    # --- Execution Tools ---

    elif name == "move_file":
        source = os.path.expanduser(arguments["source"])
        destination = os.path.expanduser(arguments["destination"])
        action_log = terminal_tools.move_file(source, destination)
        return _action_log_to_dict(action_log)

    elif name == "delete_file":
        path = os.path.expanduser(arguments["path"])
        backup = arguments.get("backup", True)
        action_log = terminal_tools.delete_file(path, backup=backup)
        return _action_log_to_dict(action_log)

    elif name == "create_directory":
        path = os.path.expanduser(arguments["path"])
        action_log = terminal_tools.create_directory(path)
        return _action_log_to_dict(action_log)

    elif name == "clean_docker":
        prune_all = arguments.get("prune_all", False)
        result = terminal_tools.clean_docker(prune_all=prune_all)
        return result

    # --- Utility Tools ---

    elif name == "calculate_file_hash":
        file_path = os.path.expanduser(arguments["file_path"])
        file_hash = terminal_tools.calculate_file_hash(file_path)
        return {
            "file_path": file_path,
            "hash": file_hash,
            "algorithm": "xxhash64" if file_hash else "failed"
        }

    elif name == "get_server_info":
        return {
            "server": "StoragePilot MCP Server",
            "version": "1.0.0",
            "dry_run": dry_run,
            "mode": "preview" if dry_run else "execute",
            "tools_count": 15,
            "categories": {
                "discovery": ["scan_directory", "find_large_files", "find_old_files", "find_developer_artifacts"],
                "system": ["get_system_overview", "get_docker_usage"],
                "classification": ["classify_files", "classify_single_file", "detect_duplicates"],
                "execution": ["move_file", "delete_file", "create_directory", "clean_docker"],
                "utility": ["calculate_file_hash", "get_server_info"]
            }
        }

    else:
        raise ValueError(f"Unknown tool: {name}")


# =============================================================================
# Helper Functions
# =============================================================================

def _classification_to_dict(classification) -> dict:
    """Convert FileClassification dataclass to dictionary."""
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
        "duplicate_of": classification.duplicate_of
    }


def _action_log_to_dict(action_log) -> dict:
    """Convert ActionLog dataclass to dictionary."""
    return {
        "timestamp": action_log.timestamp,
        "action_type": action_log.action_type,
        "source": action_log.source,
        "destination": action_log.destination,
        "size_bytes": action_log.size_bytes,
        "success": action_log.success,
        "dry_run": action_log.dry_run,
        "reversible": action_log.reversible,
        "undo_command": action_log.undo_command
    }


def _find_developer_artifacts_impl(terminal_tools: TerminalTools, workspace_path: str) -> dict:
    """Find developer artifacts in a workspace directory."""
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

    results = {
        "workspace": workspace_path,
        "artifacts": {},
        "total_size": 0,
        "total_count": 0
    }

    for artifact_name, config in artifact_patterns.items():
        try:
            found = terminal_tools.find_files(
                path=workspace_path,
                pattern=config["pattern"],
                file_type=config["type"],
                max_depth=5
            )
            if found:
                total_artifact_size = sum(f.get("size_bytes", 0) for f in found)
                results["artifacts"][artifact_name] = {
                    "count": len(found),
                    "total_size_bytes": total_artifact_size,
                    "total_size_human": terminal_tools._human_readable_size(total_artifact_size),
                    "regenerate_command": config["regenerate"],
                    "locations": [f["path"] for f in found[:10]]  # Limit to 10 per type
                }
                results["total_size"] += total_artifact_size
                results["total_count"] += len(found)
        except Exception:
            pass  # Skip artifacts that can't be found

    results["total_size_human"] = terminal_tools._human_readable_size(results["total_size"])
    return results


def _detect_duplicates_impl(terminal_tools: TerminalTools, directory_path: str) -> dict:
    """Detect duplicate files using content hashing."""
    import hashlib
    from collections import defaultdict

    hash_map = defaultdict(list)
    files_processed = 0
    errors = []

    path = Path(directory_path)
    if not path.exists():
        return {"error": f"Directory not found: {directory_path}"}

    for file_path in path.rglob("*"):
        if file_path.is_file():
            try:
                # Calculate MD5 hash
                hasher = hashlib.md5()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        hasher.update(chunk)
                file_hash = hasher.hexdigest()

                file_info = {
                    "path": str(file_path),
                    "size_bytes": file_path.stat().st_size,
                    "modified": file_path.stat().st_mtime
                }
                hash_map[file_hash].append(file_info)
                files_processed += 1
            except (PermissionError, OSError) as e:
                errors.append({"path": str(file_path), "error": str(e)})

    # Filter to only duplicates (hash with multiple files)
    duplicates = {
        hash_val: files
        for hash_val, files in hash_map.items()
        if len(files) > 1
    }

    # Calculate space that could be recovered
    recoverable_bytes = 0
    for files in duplicates.values():
        # Keep newest, calculate size of others
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
        "errors": errors[:10] if errors else []  # Limit error reporting
    }


# =============================================================================
# Main Entry Point
# =============================================================================

async def main():
    """Main entry point for the MCP server."""
    parser = argparse.ArgumentParser(
        description="StoragePilot MCP Server - Centralized storage management tools"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in dry-run mode (preview only, no actual changes). This is the default."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run in execute mode (allows actual file system changes)"
    )

    args = parser.parse_args()

    # Determine mode
    dry_run = not args.execute

    # Create server
    server = create_server(dry_run=dry_run)

    # Log startup info to stderr (stdout is for MCP protocol)
    mode_str = "DRY-RUN (preview)" if dry_run else "EXECUTE (live)"
    print(f"StoragePilot MCP Server starting in {mode_str} mode...", file=sys.stderr)

    # Run server with stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
