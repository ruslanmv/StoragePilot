#!/usr/bin/env bash
# =============================================================================
# StoragePilot MCP Server Registration Script
# =============================================================================
# Registers StoragePilot as a STDIO gateway in MCP Context Forge
#
# Usage:
#   ./forge_register_storagepilot.sh /path/to/.env.local /path/to/wrapper.sh
#
# Example:
#   ./forge_register_storagepilot.sh .env.local ~/storagepilot_mcp_dryrun.sh
#
# Requirements:
#   - curl
#   - python3 (for JSON parsing)
#   - Context Forge running and accessible
# =============================================================================

set -euo pipefail

ENV_FILE="${1:-.env.local}"
WRAPPER_PATH="${2:-}"

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: Env file not found: $ENV_FILE"
  exit 1
fi

if [[ -z "$WRAPPER_PATH" ]]; then
  echo "Error: Missing wrapper script path argument."
  echo "Usage: $0 .env.local /path/to/storagepilot_wrapper.sh"
  exit 1
fi

if [[ ! -x "$WRAPPER_PATH" ]]; then
  echo "Error: Wrapper script is not executable: $WRAPPER_PATH"
  echo "Fix with: chmod +x \"$WRAPPER_PATH\""
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

TOKEN="$(python3 - <<'PY'
import json,sys
data=json.loads(sys.stdin.read())
print(data.get("access_token",""))
PY
<<<"$LOGIN_JSON")"

if [[ -z "$TOKEN" ]]; then
  echo "Error: Login failed. Response:"
  echo "$LOGIN_JSON"
  exit 1
fi

echo "Logged in successfully"
export CONTEXT_FORGE_TOKEN="$TOKEN"

# -----------------------------------------------------------------------------
# Register StoragePilot as a Gateway (STDIO)
# -----------------------------------------------------------------------------

GATEWAY_NAME="${GATEWAY_NAME:-storagepilot-stdio}"
GATEWAY_DESC="${GATEWAY_DESC:-StoragePilot MCP (STDIO) - dry-run wrapper}"

echo "Registering gateway: $GATEWAY_NAME"

CREATE_PAYLOAD="$(python3 - <<PY
import json
payload = {
  "name": "${GATEWAY_NAME}",
  "url": "${WRAPPER_PATH}",
  "description": "${GATEWAY_DESC}",
  "transport": "STDIO",
  "auth_type": "none",
  "visibility": "private",
  "tags": ["storagepilot", "mcp", "stdio"]
}
print(json.dumps(payload))
PY
)"

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
