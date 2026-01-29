#!/usr/bin/env python3
"""
scripts/forge_publish_storagepilot.py

Layer 2 automation:
Create (or update) a Catalog Server in Context Forge that references the MCP Gateway,
so MatrixShell can sync it as a plugin.

This script auto-discovers the correct tools endpoint via OpenAPI and tries multiple
known admin endpoints to find tools visible to the token.

Usage:
  python3 scripts/forge_publish_storagepilot.py --env .env.local

Minimum .env.local:
  PLATFORM_ADMIN_EMAIL=admin@example.com
  PLATFORM_ADMIN_PASSWORD=changeme1
  FORGE_URL=http://localhost:4444

Optional .env.local:
  CONTEXT_FORGE_TOKEN=...          # skip login if present
  GATEWAY_NAME=storagepilot
  CATALOG_SERVER_NAME=storagepilot
  CATALOG_SERVER_DESC=StoragePilot tools exposed to MatrixShell
  CATALOG_VISIBILITY=private
  TEAM_ID=...                      # optional team ID
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def parse_env_file(path: Path) -> Dict[str, str]:
    """Parse .env-like file safely without shell execution."""
    env: Dict[str, str] = {}
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        env[k] = v
    return env


def normalize_url(u: str) -> str:
    return u.strip().rstrip("/")


def http_json(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 25,
) -> Any:
    """Make an HTTP request and parse JSON response."""
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
            return json.loads(body) if body else {}
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"HTTP {e.code} {method} {url}\n{body}") from None
    except URLError as e:
        raise RuntimeError(f"Network error calling {url}: {e}") from None
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from {url}: {e}") from None


@dataclass(frozen=True)
class Config:
    forge_url: str
    email: str
    password: str
    token: Optional[str]

    gateway_name: str

    server_name: str
    server_desc: str
    visibility: str
    team_id: Optional[str]


def login_get_token(cfg: Config) -> str:
    """Get token from config or login to get one."""
    if cfg.token and cfg.token.strip():
        return cfg.token.strip()

    login = http_json(
        "POST",
        f"{cfg.forge_url}/auth/login",
        {"email": cfg.email, "password": cfg.password},
    )
    tok = (login or {}).get("access_token")
    if not tok:
        raise RuntimeError(f"Login succeeded but access_token missing: {login}")
    return tok


def list_gateways(forge_url: str, token: str) -> List[dict]:
    """List all gateways from Context Forge."""
    data = http_json("GET", f"{forge_url}/gateways", headers={"Authorization": f"Bearer {token}"})
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(data, list):
        return data
    return []


def find_gateway_id(forge_url: str, token: str, name: str) -> str:
    """Find gateway ID by name."""
    for g in list_gateways(forge_url, token):
        if isinstance(g, dict) and g.get("name") == name and g.get("id"):
            return str(g["id"])
    raise RuntimeError(f"Gateway '{name}' not found. Run forge_register_storagepilot.py first.")


def _extract_tool_list(resp: Any) -> List[dict]:
    """Extract tools list from various response formats."""
    if isinstance(resp, list):
        return [x for x in resp if isinstance(x, dict)]
    if isinstance(resp, dict):
        if isinstance(resp.get("tools"), list):
            return [x for x in resp["tools"] if isinstance(x, dict)]
        if isinstance(resp.get("items"), list):
            return [x for x in resp["items"] if isinstance(x, dict)]
        if isinstance(resp.get("data"), list):
            return [x for x in resp["data"] if isinstance(x, dict)]
    return []


def _tool_gateway_id(tool: dict) -> Optional[str]:
    """Extract gateway ID from tool object."""
    if tool.get("gateway_id") is not None:
        return str(tool["gateway_id"])
    if tool.get("gatewayId") is not None:
        return str(tool["gatewayId"])
    gw = tool.get("gateway")
    if isinstance(gw, dict) and gw.get("id") is not None:
        return str(gw["id"])
    return None


def discover_tool_paths(forge_url: str, token: str) -> List[str]:
    """
    Read openapi.json and return all GET-able paths containing 'tool'.
    """
    try:
        spec = http_json("GET", f"{forge_url}/openapi.json", headers={"Authorization": f"Bearer {token}"})
        paths = spec.get("paths", {})
        out: List[str] = []
        if isinstance(paths, dict):
            for p, methods in paths.items():
                if "tool" in str(p).lower() and isinstance(methods, dict) and ("get" in methods):
                    out.append(str(p))
        # Prefer admin/cp/catalog paths first (typical for UI)
        pref = ["admin", "cp", "catalog"]
        out.sort(key=lambda x: (0 if any(k in x.lower() for k in pref) else 1, len(x)))
        return out
    except Exception:
        return []


def fetch_tools_from_any_endpoint(
    forge_url: str,
    token: str,
    gateway_id: str,
    visibility: str,
) -> Tuple[List[dict], List[str]]:
    """
    Try multiple endpoints to find tools visible to this token.
    Returns (tools, tried_urls)
    """
    headers = {"Authorization": f"Bearer {token}"}
    tried: List[str] = []

    # Known common endpoints + any discovered ones from OpenAPI
    candidates = [
        "/tools",
        "/admin/tools",
        "/cp/tools",
        "/catalog/tools",
        "/registry/tools",
        "/mcp/tools",
    ]

    discovered = discover_tool_paths(forge_url, token)
    for p in discovered:
        if p not in candidates:
            candidates.append(p)

    # We try each endpoint with a few query shapes
    query_variants = [
        {"gateway_id": gateway_id, "limit": "0", "include_pagination": "true"},
        {"gateway_id": gateway_id, "limit": "0", "include_inactive": "true", "include_pagination": "true"},
        {"gateway_id": gateway_id, "limit": "0", "include_inactive": "true", "visibility": visibility, "include_pagination": "true"},
        {"limit": "0", "include_inactive": "true", "include_pagination": "true"},
    ]

    for path in candidates:
        for q in query_variants:
            url = f"{forge_url}{path}?{urlencode(q)}"
            tried.append(url)
            try:
                resp = http_json("GET", url, headers=headers)
                tools = _extract_tool_list(resp)

                # Filter by gateway locally if endpoint doesn't filter
                out: List[dict] = []
                for t in tools:
                    gid = _tool_gateway_id(t)
                    if gid is None or gid == str(gateway_id):
                        out.append(t)

                if out:
                    return out, tried
            except Exception:
                continue

    return [], tried


def find_server_by_name(forge_url: str, token: str, name: str) -> Optional[str]:
    """Find server ID by name."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        data = http_json("GET", f"{forge_url}/servers", headers=headers)
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return None
        for s in items:
            if isinstance(s, dict) and s.get("name") == name and s.get("id"):
                return str(s["id"])
    except Exception:
        pass
    return None


def create_or_update_server(cfg: Config, token: str, tool_ids: List[str]) -> str:
    """Create or update a catalog server with associated tools."""
    headers = {"Authorization": f"Bearer {token}"}

    server_obj: Dict[str, Any] = {
        "name": cfg.server_name,
        "description": cfg.server_desc,
        "tags": ["storagepilot", "mcp"],
        "associated_tools": tool_ids,
        "associated_resources": [],
        "associated_prompts": [],
    }

    wrapped_payload: Dict[str, Any] = {
        "server": server_obj,
        "team_id": cfg.team_id,
        "visibility": cfg.visibility,
    }

    try:
        resp = http_json("POST", f"{cfg.forge_url}/servers", payload=wrapped_payload, headers=headers)
        sid = str(resp.get("id") or resp.get("server_id") or "")
        return sid or "(created)"
    except RuntimeError as e:
        msg = str(e)
        if "HTTP 409" in msg or "conflict" in msg.lower():
            sid = find_server_by_name(cfg.forge_url, token, cfg.server_name)
            if not sid:
                raise RuntimeError("Server exists (409) but could not locate it via GET /servers.") from None
            # Update basic fields
            try:
                http_json(
                    "PUT",
                    f"{cfg.forge_url}/servers/{sid}",
                    payload={"name": cfg.server_name, "description": cfg.server_desc, "tags": ["storagepilot", "mcp"]},
                    headers=headers,
                )
            except Exception:
                pass
            # Try to update associations
            try:
                http_json(
                    "PATCH",
                    f"{cfg.forge_url}/servers/{sid}",
                    payload={"associated_tools": tool_ids, "associated_resources": [], "associated_prompts": []},
                    headers=headers,
                )
            except Exception:
                pass
            return sid
        raise


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Publish StoragePilot to Forge Catalog (Layer 2) for MatrixShell sync.")
    p.add_argument("--env", default=".env.local", help="Path to .env.local")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()

    env_path = Path(args.env)
    if not env_path.exists():
        eprint(f"Error: missing env file: {env_path}")
        return 2

    env = parse_env_file(env_path)
    forge_url = normalize_url(env.get("FORGE_URL", "http://localhost:4444"))

    email = env.get("PLATFORM_ADMIN_EMAIL", "").strip()
    password = env.get("PLATFORM_ADMIN_PASSWORD", "").strip()
    if not email or not password:
        eprint("Error: PLATFORM_ADMIN_EMAIL and PLATFORM_ADMIN_PASSWORD are required in .env.local")
        return 3

    cfg = Config(
        forge_url=forge_url,
        email=email,
        password=password,
        token=env.get("CONTEXT_FORGE_TOKEN"),
        gateway_name=env.get("GATEWAY_NAME", "storagepilot"),
        server_name=env.get("CATALOG_SERVER_NAME", env.get("GATEWAY_NAME", "storagepilot")),
        server_desc=env.get("CATALOG_SERVER_DESC", "StoragePilot tools exposed to MatrixShell"),
        visibility=env.get("CATALOG_VISIBILITY", "private").lower(),
        team_id=env.get("TEAM_ID") or None,
    )

    print(f"Checking if Context Forge is running at {cfg.forge_url}...")
    try:
        http_json("GET", f"{cfg.forge_url}/health")
    except Exception as e:
        eprint(f"Error: Context Forge not reachable: {e}")
        return 4
    print("Context Forge is running\n")

    try:
        token = login_get_token(cfg)
        gw_id = find_gateway_id(cfg.forge_url, token, cfg.gateway_name)
    except Exception as e:
        eprint(f"Error: {e}")
        return 5

    print(f"Forge:   {cfg.forge_url}")
    print(f"Gateway: {cfg.gateway_name}")
    print(f"Gateway id: {gw_id}")

    tools, tried = fetch_tools_from_any_endpoint(cfg.forge_url, token, gw_id, cfg.visibility)
    tool_ids = [str(t["id"]) for t in tools if isinstance(t, dict) and t.get("id")]

    if not tool_ids:
        eprint("\nWarning: No tools visible via API for this token.")
        eprint("This may mean the Admin UI uses a different endpoint than /tools.")
        eprint("Tried URLs (first few):")
        for u in tried[:6]:
            eprint("  -", u)
        eprint("\nProceeding to create server without tool associations...")
        eprint("You can manually associate tools in the Admin UI.\n")

    print(f"Tools found: {len(tool_ids)}")
    print("Creating Catalog Server (Layer 2) at POST /servers ...")

    try:
        sid = create_or_update_server(cfg, token, tool_ids)
    except Exception as e:
        eprint("Failed to create/update Catalog Server.")
        eprint(str(e))
        return 7

    print(f"Catalog Server ready: {cfg.server_name} (id={sid})")
    print("\nNext (MatrixShell):")
    print(f"  export CONTEXT_FORGE_URL='{cfg.forge_url}'")
    print(f"  export CONTEXT_FORGE_TOKEN='{token}'")
    print("  matrixsh login --url \"$CONTEXT_FORGE_URL\" --token \"$CONTEXT_FORGE_TOKEN\"")
    print("  matrixsh sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
