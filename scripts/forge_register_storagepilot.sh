#!/usr/bin/env bash
# =============================================================================
# StoragePilot MCP Server Registration Script
# =============================================================================
# Registers StoragePilot as an HTTP gateway in MCP Context Forge
#
# Usage:
#   ./forge_register_storagepilot.sh /path/to/.env.local [MCP_SERVER_URL]
#
# Example:
#   ./forge_register_storagepilot.sh .env.local
#   ./forge_register_storagepilot.sh .env.local http://localhost:9000/mcp/sse
#
# Prerequisites:
#   - StoragePilot MCP server running in HTTP mode: make mcp-server-http
#   - Context Forge running and accessible
#
# Requirements:
#   - curl
#   - python3 (for JSON parsing)
# =============================================================================

set -euo pipefail

ENV_FILE="${1:-.env.local}"
MCP_SERVER_URL="${2:-http://localhost:9000/mcp/sse}"

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: Env file not found: $ENV_FILE"
  exit 1
fi

# -----------------------------------------------------------------------------
# Load environment variables
# -----------------------------------------------------------------------------

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# -----------------------------------------------------------------------------
# Determine Context Forge URL
# -----------------------------------------------------------------------------

FORGE_URL="${FORGE_URL:-}"
if [[ -z "$FORGE_URL" ]]; then
  BASE="${APP_DOMAIN:-http://localhost}"
  if [[ "$BASE" =~ :[0-9]+$ ]]; then
    FORGE_URL="$BASE"
  else
    FORGE_URL="${BASE}:4444"
  fi
fi

# -----------------------------------------------------------------------------
# Validate credentials
# -----------------------------------------------------------------------------

ADMIN_EMAIL="${PLATFORM_ADMIN_EMAIL:-}"
ADMIN_PASS="${PLATFORM_ADMIN_PASSWORD:-}"

if [[ -z "$ADMIN_EMAIL" || -z "$ADMIN_PASS" ]]; then
  echo "Error: PLATFORM_ADMIN_EMAIL or PLATFORM_ADMIN_PASSWORD missing in $ENV_FILE"
  exit 1
fi

echo "Context Forge URL: $FORGE_URL"

# -----------------------------------------------------------------------------
# Login to Context Forge
# -----------------------------------------------------------------------------

echo "Logging in as $ADMIN_EMAIL..."

LOGIN_JSON="$(curl -sS -X POST "$FORGE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASS\"}")"

# Check for empty response
if [[ -z "$LOGIN_JSON" ]]; then
  echo "Error: Empty login response (Context Forge not reachable?)"
  exit 1
fi

# Parse token using python -c (stdin is free for JSON input)
TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' <<<"$LOGIN_JSON")"

if [[ -z "$TOKEN" ]]; then
  echo "Error: Login failed. Response:"
  echo "$LOGIN_JSON"
  exit 1
fi

echo "Logged in successfully"
export CONTEXT_FORGE_TOKEN="$TOKEN"

# -----------------------------------------------------------------------------
# Register StoragePilot as a Gateway (HTTP/SSE)
# -----------------------------------------------------------------------------

GATEWAY_NAME="${GATEWAY_NAME:-storagepilot}"
GATEWAY_DESC="${GATEWAY_DESC:-StoragePilot MCP Server - AI-powered storage management}"

echo "Registering gateway: $GATEWAY_NAME"
echo "MCP Server URL: $MCP_SERVER_URL"

# Create JSON payload using python for proper escaping
CREATE_PAYLOAD="$(python3 -c "
import json
payload = {
    'name': '${GATEWAY_NAME}',
    'url': '${MCP_SERVER_URL}',
    'description': '${GATEWAY_DESC}',
    'transport': 'SSE',
    'auth_type': 'bearer',
    'auth_value': 'storagepilot-token',
    'visibility': 'private',
    'tags': ['storagepilot', 'mcp', 'sse', 'storage']
}
print(json.dumps(payload))
")"

CREATE_RESP="$(curl -sS -X POST "$FORGE_URL/gateways" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$CREATE_PAYLOAD" || true)"

if echo "$CREATE_RESP" | grep -q "\"id\"" ; then
  echo "Gateway registered: $GATEWAY_NAME"
else
  if echo "$CREATE_RESP" | grep -qi "conflict" || echo "$CREATE_RESP" | grep -q "409"; then
    echo "Gateway already exists: $GATEWAY_NAME (continuing)"
  else
    echo "Warning: Gateway creation response:"
    echo "$CREATE_RESP"
    echo "Check Admin UI -> Gateways for status"
  fi
fi

# -----------------------------------------------------------------------------
# Sync MatrixShell (if installed)
# -----------------------------------------------------------------------------

if command -v matrixsh >/dev/null 2>&1; then
  echo "Syncing MatrixShell plugins from Context Forge..."
  matrixsh login --url "$FORGE_URL" --token "$CONTEXT_FORGE_TOKEN"
  matrixsh sync
  echo "MatrixShell synced. Try: matrixsh tools"
else
  echo "matrixsh not found; skipping MatrixShell sync."
  echo "To sync later:"
  echo "  matrixsh login --url \"$FORGE_URL\" --token \"\$CONTEXT_FORGE_TOKEN\""
  echo "  matrixsh sync"
fi

echo ""
echo "Registration complete."
