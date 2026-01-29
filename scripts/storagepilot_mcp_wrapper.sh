#!/usr/bin/env bash
# =============================================================================
# StoragePilot MCP Wrapper Script
# =============================================================================
# Launches StoragePilot MCP server in STDIO mode for Context Forge integration
#
# Usage:
#   ./scripts/storagepilot_mcp_wrapper.sh [--dry-run|--execute]
#
# Default: --dry-run (safe preview mode)
# =============================================================================

set -euo pipefail

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Change to project directory
cd "$PROJECT_DIR"

# Default to dry-run mode
MODE="${1:---dry-run}"

# Use virtual environment Python if available, otherwise system Python
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi

# Launch MCP server
exec "$PYTHON" mcp_server.py "$MODE"
