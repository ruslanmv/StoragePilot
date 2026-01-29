#!/usr/bin/env python3
"""
scripts/forge_register_storagepilot.py

Register (or update) the StoragePilot MCP server as a Gateway in MCP Context Forge.

Production-ready goals:
- Safe .env.local parsing (no shell `source`)
- Uses existing CONTEXT_FORGE_TOKEN if provided, otherwise logs in with admin creds
- Validates Forge + MCP health endpoints before registering
- Creates gateway, or updates it if it already exists
- Uses Context Forge schema expectations (auth_token for bearer)
- Clear exit codes and actionable errors

Usage:
  python3 scripts/forge_register_storagepilot.py --env .env.local
  python3 scripts/forge_register_storagepilot.py --env .env.local --mcp-url http://127.0.0.1:9000/mcp/sse
  python3 scripts/forge_register_storagepilot.py --env .env.local --name storagepilot --transport SSE

Required in .env.local (minimum):
  PLATFORM_ADMIN_EMAIL=admin@example.com
  PLATFORM_ADMIN_PASSWORD=changeme1
  FORGE_URL=http://localhost:4444

Optional in .env.local:
  CONTEXT_FORGE_TOKEN=...                     # if set, skips login
  STORAGEPILOT_BEARER_TOKEN=storagepilot-token # forwarded by Forge to StoragePilot as Authorization: Bearer ...
  GATEWAY_NAME=storagepilot
  GATEWAY_DESC=...
  MCP_SERVER_URL=http://127.0.0.1:9000/mcp/sse
  MCP_HEALTH_URL=http://127.0.0.1:9000/health
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ----------------------------
# Utilities
# ----------------------------

def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def parse_env_file(path: Path) -> Dict[str, str]:
    """
    Parse .env-like file safely:
    - supports KEY=VALUE lines
    - ignores comments and blank lines
    - strips surrounding single/double quotes
    - does NOT execute anything
    """
    env: Dict[str, str] = {}
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        key, val = s.split("=", 1)
        key = key.strip()
        val = val.strip()
        # drop inline comments only if unquoted (simple heuristic)
        # keep it conservative; don't try to be a full .env parser
        if val and val[0] not in ("'", '"'):
            if " #" in val:
                val = val.split(" #", 1)[0].rstrip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        env[key] = val
    return env


def http_json(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> Any:
    """
    Make an HTTP request and parse JSON response.
    Raises RuntimeError with readable details on errors.
    """
    data = None
    hdrs = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)

    req = Request(url, method=method, data=data, headers=hdrs)
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace").strip()
            if not body:
                return {}
            return json.loads(body)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {url}\n{body}") from None
    except URLError as e:
        raise RuntimeError(f"Network error calling {url}: {e}") from None
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from {url}: {e}") from None


def http_status_ok(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 8) -> bool:
    """Return True if GET url returns 200-ish."""
    req = Request(url, method="GET", headers=headers or {})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


# ----------------------------
# Domain
# ----------------------------

@dataclass(frozen=True)
class Config:
    forge_url: str
    admin_email: Optional[str]
    admin_password: Optional[str]
    context_forge_token: Optional[str]

    mcp_url: str
    mcp_health_url: str

    gateway_name: str
    gateway_desc: str
    transport: str
    visibility: str

    # token Forge forwards to StoragePilot (Authorization: Bearer ...)
    storagepilot_bearer_token: str


def normalize_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    return url


def build_config(env: Dict[str, str], args: argparse.Namespace) -> Config:
    forge_url = args.forge_url or env.get("FORGE_URL") or env.get("APP_DOMAIN") or "http://localhost:4444"
    forge_url = normalize_base_url(forge_url)

    # If APP_DOMAIN was used without port, add default 4444
    if forge_url.startswith("http://localhost") and forge_url.count(":") == 1:
        forge_url = forge_url + ":4444"

    admin_email = env.get("PLATFORM_ADMIN_EMAIL")
    admin_password = env.get("PLATFORM_ADMIN_PASSWORD")
    context_forge_token = env.get("CONTEXT_FORGE_TOKEN") or env.get("CONTEXT_FORGE_ACCESS_TOKEN")

    mcp_url = args.mcp_url or env.get("MCP_SERVER_URL") or "http://127.0.0.1:9000/mcp/sse"
    mcp_health_url = env.get("MCP_HEALTH_URL") or "http://127.0.0.1:9000/health"

    gateway_name = args.name or env.get("GATEWAY_NAME") or "storagepilot"
    gateway_desc = args.description or env.get("GATEWAY_DESC") or "StoragePilot MCP Server - AI-powered storage management"
    transport = (args.transport or env.get("GATEWAY_TRANSPORT") or "SSE").upper()
    visibility = (args.visibility or env.get("GATEWAY_VISIBILITY") or "private").lower()

    # If StoragePilot doesn't enforce auth, any token string is OK; Forge requires auth_token for bearer in this build.
    storagepilot_bearer_token = env.get("STORAGEPILOT_BEARER_TOKEN") or "storagepilot-token"

    return Config(
        forge_url=forge_url,
        admin_email=admin_email,
        admin_password=admin_password,
        context_forge_token=context_forge_token,

        mcp_url=mcp_url,
        mcp_health_url=mcp_health_url,

        gateway_name=gateway_name,
        gateway_desc=gateway_desc,
        transport=transport,
        visibility=visibility,
        storagepilot_bearer_token=storagepilot_bearer_token,
    )


# ----------------------------
# Forge operations
# ----------------------------

def login_and_get_token(cfg: Config) -> str:
    if cfg.context_forge_token and cfg.context_forge_token.strip():
        return cfg.context_forge_token.strip()

    if not cfg.admin_email or not cfg.admin_password:
        raise RuntimeError(
            "Missing authentication. Provide either CONTEXT_FORGE_TOKEN or "
            "PLATFORM_ADMIN_EMAIL + PLATFORM_ADMIN_PASSWORD in .env.local."
        )

    login_url = f"{cfg.forge_url}/auth/login"
    resp = http_json("POST", login_url, {"email": cfg.admin_email, "password": cfg.admin_password})
    token = (resp or {}).get("access_token")
    if not token:
        raise RuntimeError(f"Login succeeded but access_token missing. Response: {resp}")
    return token


def list_gateways(cfg: Config, token: str) -> List[dict]:
    url = f"{cfg.forge_url}/gateways"
    headers = {"Authorization": f"Bearer {token}"}
    data = http_json("GET", url, headers=headers)
    # Different builds return either {"items":[...]} or just [...]
    if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        return data["items"]
    if isinstance(data, list):
        return data
    # fallback
    return []


def find_gateway_id_by_name(cfg: Config, token: str, name: str) -> Optional[str]:
    for g in list_gateways(cfg, token):
        if isinstance(g, dict) and g.get("name") == name:
            gid = g.get("id")
            if isinstance(gid, str) and gid:
                return gid
    return None


def create_gateway(cfg: Config, token: str) -> dict:
    url = f"{cfg.forge_url}/gateways"
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "name": cfg.gateway_name,
        "url": cfg.mcp_url,
        "description": cfg.gateway_desc,
        "transport": cfg.transport,          # e.g. "SSE"
        "auth_type": "bearer",               # this build requires one of allowed enums
        "auth_token": cfg.storagepilot_bearer_token,  # correct field name for Context Forge
        "visibility": cfg.visibility,        # "private" or "public" depending on Forge rules
        "tags": ["storagepilot", "mcp", cfg.transport.lower()],
    }
    return http_json("POST", url, payload=payload, headers=headers)


def update_gateway(cfg: Config, token: str, gateway_id: str) -> dict:
    # Try PUT first, then PATCH (Forge variants)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "name": cfg.gateway_name,
        "url": cfg.mcp_url,
        "description": cfg.gateway_desc,
        "transport": cfg.transport,
        "auth_type": "bearer",
        "auth_token": cfg.storagepilot_bearer_token,
        "visibility": cfg.visibility,
        "tags": ["storagepilot", "mcp", cfg.transport.lower()],
    }

    put_url = f"{cfg.forge_url}/gateways/{gateway_id}"
    try:
        return http_json("PUT", put_url, payload=payload, headers=headers)
    except RuntimeError as e:
        # If PUT is not supported, PATCH might be.
        if "HTTP 405" in str(e) or "HTTP 404" in str(e):
            patch_url = f"{cfg.forge_url}/gateways/{gateway_id}"
            return http_json("PATCH", patch_url, payload=payload, headers=headers)
        raise


# ----------------------------
# CLI
# ----------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Register StoragePilot MCP server in MCP Context Forge.")
    p.add_argument("--env", default=".env.local", help="Path to .env.local file")
    p.add_argument("--forge-url", default=None, help="Override Forge URL (default from .env.local FORGE_URL)")
    p.add_argument("--mcp-url", default=None, help="Override MCP server URL (default http://127.0.0.1:9000/mcp/sse)")
    p.add_argument("--name", default=None, help="Gateway name (default storagepilot)")
    p.add_argument("--description", default=None, help="Gateway description")
    p.add_argument("--transport", default=None, help="Transport: SSE / STREAMABLEHTTP / WS (depends on server)")
    p.add_argument("--visibility", default=None, help="Visibility: private/public (depends on Forge)")
    p.add_argument("--skip-health-checks", action="store_true", help="Skip health checks")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()

    env_path = Path(args.env)
    if not env_path.exists():
        eprint(f"Error: Env file not found: {env_path}")
        return 2

    env = parse_env_file(env_path)
    cfg = build_config(env, args)

    # 0) Pre-checks
    if not args.skip_health_checks:
        if not http_status_ok(f"{cfg.forge_url}/health"):
            eprint(f"Error: Context Forge not reachable at {cfg.forge_url}/health")
            return 3
        if not http_status_ok(cfg.mcp_health_url):
            eprint(f"Error: StoragePilot MCP server not reachable at {cfg.mcp_health_url}")
            eprint("Hint: start it with: make mcp-server-http")
            return 4

    # 1) Authenticate
    try:
        token = login_and_get_token(cfg)
    except Exception as e:
        eprint(f"Error: {e}")
        return 5

    # 2) Create or update gateway
    try:
        # Attempt create first
        try:
            created = create_gateway(cfg, token)
            gid = created.get("id", "")
            print(f"Gateway created: {cfg.gateway_name}" + (f" (id={gid})" if gid else ""))
        except RuntimeError as e:
            msg = str(e)
            if "HTTP 409" in msg or "conflict" in msg.lower():
                gid = find_gateway_id_by_name(cfg, token, cfg.gateway_name)
                if not gid:
                    eprint("Gateway exists but could not locate it via GET /gateways. Update in Admin UI.")
                    eprint(msg)
                    return 6
                updated = update_gateway(cfg, token, gid)
                _ = updated  # for debugging if needed
                print(f"Gateway updated: {cfg.gateway_name} (id={gid})")
            else:
                raise

    except Exception as e:
        eprint(f"Error registering gateway: {e}")
        return 7

    # 3) Print next steps
    print("\nNext steps:")
    print(f"  export CONTEXT_FORGE_TOKEN='{token}'")
    print(f"  # MatrixShell (if installed):")
    print(f"  matrixsh login --url '{cfg.forge_url}' --token \"$CONTEXT_FORGE_TOKEN\"")
    print("  matrixsh sync\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
