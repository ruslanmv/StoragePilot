#!/usr/bin/env python3
"""
scripts/forge_publish_storagepilot.py

Layer 2 automation:
Create (or update) a Catalog Server / Virtual Server in Context Forge that references the MCP Gateway,
so MatrixShell can sync it as a plugin.

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
  CATALOG_INCLUDE_ALL_TOOLS=true

Advanced override if your Forge uses a different endpoint:
  FORGE_CATALOG_ENDPOINT=/servers   (or /catalog/servers, /virtual-servers, etc.)
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
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {url}\n{body}") from None
    except URLError as e:
        raise RuntimeError(f"Network error calling {url}: {e}") from None
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from {url}: {e}") from None


def normalize_url(u: str) -> str:
    return u.strip().rstrip("/")


@dataclass(frozen=True)
class Config:
    forge_url: str
    token: Optional[str]
    email: Optional[str]
    password: Optional[str]

    gateway_name: str

    catalog_name: str
    catalog_desc: str
    catalog_visibility: str
    include_all_tools: bool

    catalog_endpoint_override: Optional[str]


def login_get_token(cfg: Config) -> str:
    """Get token from config or login to get one."""
    if cfg.token and cfg.token.strip():
        return cfg.token.strip()
    if not cfg.email or not cfg.password:
        raise RuntimeError("Missing CONTEXT_FORGE_TOKEN and missing PLATFORM_ADMIN_EMAIL/PLATFORM_ADMIN_PASSWORD")
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


def try_create_catalog_server(
    forge_url: str,
    token: str,
    endpoint: str,
    payload: Dict[str, Any],
) -> Tuple[bool, str]:
    """Try POST create; return (success, message)."""
    url = f"{forge_url}{endpoint}"
    try:
        resp = http_json("POST", url, payload=payload, headers={"Authorization": f"Bearer {token}"})
        sid = ""
        if isinstance(resp, dict):
            sid = str(resp.get("id") or resp.get("server_id") or "")
        return True, f"Created via POST {endpoint}" + (f" (id={sid})" if sid else "")
    except RuntimeError as e:
        msg = str(e)
        # Check for conflict (already exists)
        if "HTTP 409" in msg or "conflict" in msg.lower():
            return True, f"Already exists at {endpoint}"
        return False, msg


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create Layer-2 Catalog Server / Virtual Server for MatrixShell sync.")
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
    cfg = Config(
        forge_url=forge_url,
        token=env.get("CONTEXT_FORGE_TOKEN"),
        email=env.get("PLATFORM_ADMIN_EMAIL"),
        password=env.get("PLATFORM_ADMIN_PASSWORD"),
        gateway_name=env.get("GATEWAY_NAME", "storagepilot"),
        catalog_name=env.get("CATALOG_SERVER_NAME", env.get("GATEWAY_NAME", "storagepilot")),
        catalog_desc=env.get("CATALOG_SERVER_DESC", "StoragePilot tools exposed to MatrixShell"),
        catalog_visibility=env.get("CATALOG_VISIBILITY", "private").lower(),
        include_all_tools=(env.get("CATALOG_INCLUDE_ALL_TOOLS", "true").lower() == "true"),
        catalog_endpoint_override=env.get("FORGE_CATALOG_ENDPOINT"),
    )

    # Login
    try:
        token = login_get_token(cfg)
    except Exception as e:
        eprint(f"Error: {e}")
        return 3

    # Find gateway
    try:
        gw_id = find_gateway_id(cfg.forge_url, token, cfg.gateway_name)
    except Exception as e:
        eprint(f"Error: {e}")
        return 4

    # Candidate endpoints (Layer 2 object)
    endpoints: List[str] = []
    if cfg.catalog_endpoint_override:
        ep = cfg.catalog_endpoint_override.strip()
        if not ep.startswith("/"):
            ep = "/" + ep
        endpoints.append(ep)

    endpoints += [
        "/servers",
        "/catalog/servers",
        "/virtual-servers",
        "/tool-servers",
    ]

    # Candidate payload shapes (Forge variants)
    # We try multiple shapes because different builds name fields differently.
    payloads: List[Dict[str, Any]] = [
        # Shape A (common): server references gateway_id and includes all tools
        {
            "name": cfg.catalog_name,
            "description": cfg.catalog_desc,
            "source_type": "mcp",
            "gateway_id": gw_id,
            "visibility": cfg.catalog_visibility,
            "include_all_tools": cfg.include_all_tools,
            "tags": ["storagepilot", "mcp"],
        },
        # Shape B: "mcp_server_id" naming
        {
            "name": cfg.catalog_name,
            "description": cfg.catalog_desc,
            "mcp_server_id": gw_id,
            "visibility": cfg.catalog_visibility,
            "include_all_tools": cfg.include_all_tools,
        },
        # Shape C: "source" object
        {
            "name": cfg.catalog_name,
            "description": cfg.catalog_desc,
            "visibility": cfg.catalog_visibility,
            "source": {"type": "mcp", "gateway_id": gw_id},
            "include_all_tools": cfg.include_all_tools,
        },
    ]

    print(f"Forge:    {cfg.forge_url}")
    print(f"Gateway:  {cfg.gateway_name} (id={gw_id})")
    print(f"Catalog:  {cfg.catalog_name}")
    print("Creating Layer-2 Catalog Server so MatrixShell can sync...")

    errors: List[str] = []
    for ep in endpoints:
        for p in payloads:
            ok, msg = try_create_catalog_server(cfg.forge_url, token, ep, p)
            if ok:
                print(f"  {msg}")
                print("\nNext steps:")
                print(f"  export CONTEXT_FORGE_TOKEN='{token}'")
                print(f"  # In MatrixShell dir:")
                print(f"  matrixsh login --url '{cfg.forge_url}' --token \"$CONTEXT_FORGE_TOKEN\"")
                print("  matrixsh sync")
                return 0
            errors.append(f"{ep}: {msg.splitlines()[0]}")

    eprint("\nCould not create Catalog Server with known endpoints/payloads.")
    eprint("This usually means your Forge build uses a different endpoint or schema.")
    eprint("\nTry setting FORGE_CATALOG_ENDPOINT in .env.local to the correct path, e.g.:")
    eprint("  FORGE_CATALOG_ENDPOINT=/servers")
    eprint("or /catalog/servers or /virtual-servers depending on your build.\n")
    eprint("First-line errors tried:")
    for line in errors[:8]:
        eprint("  -", line)
    eprint("\nTip: If you can find the API call in your browser DevTools when you click 'Create Server',")
    eprint("set FORGE_CATALOG_ENDPOINT to that path and we can match the payload.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
