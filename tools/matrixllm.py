"""MatrixLLM integration helpers for StoragePilot.

MatrixLLM exposes an OpenAI-compatible API under /v1 and a simple health endpoint at /health.
It can also run in "pairing" auth mode, where a short pairing code is exchanged for a long-lived token.

This module provides:
  - pair_with_matrixllm(): exchange pairing code -> token
  - matrixllm_healthcheck(): check /health is reachable
  - load/save token in a user config directory (so you pair once)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

import requests


def _strip_v1(base_url: str) -> str:
    """Return server root URL (without trailing /v1) if present."""
    url = (base_url or "").strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
        url = url.rstrip("/")
    return url


def matrixllm_token_path() -> Path:
    """Cross-platform per-user token storage path."""
    appdata = os.getenv("APPDATA")
    base = Path(appdata) if appdata else (Path.home() / ".config")
    d = base / "storagepilot"
    d.mkdir(parents=True, exist_ok=True)
    return d / "matrixllm_token"


def save_matrixllm_token(token: str) -> Path:
    path = matrixllm_token_path()
    path.write_text((token or "").strip())
    # Best-effort permissions on Unix-like systems
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return path


def load_matrixllm_token() -> Optional[str]:
    path = matrixllm_token_path()
    if not path.exists():
        return None
    token = path.read_text().strip()
    return token or None


def matrixllm_healthcheck(
    base_url: str,
    token: Optional[str] = None,
    timeout_s: int = 3,
) -> Tuple[bool, str]:
    """Check MatrixLLM /health.

    Returns (ok, message).
    """
    root = _strip_v1(base_url)
    if not root:
        return False, "Missing base_url"

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        r = requests.get(f"{root}/health", headers=headers, timeout=timeout_s)
        if r.status_code >= 200 and r.status_code < 300:
            return True, "ok"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.RequestException as e:
        return False, str(e)


def pair_with_matrixllm(
    base_url: str,
    code: str,
    timeout_s: int = 10,
) -> str:
    """Exchange a pairing code for a long-lived token via POST /pair."""
    root = _strip_v1(base_url)
    if not root:
        raise ValueError("Missing base_url")

    r = requests.post(f"{root}/pair", json={"code": code}, timeout=timeout_s)
    r.raise_for_status()
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    token = data.get("token") or data.get("access_token") or data.get("key")
    if not token:
        raise RuntimeError(f"Pairing response missing token field: {data}")
    return str(token).strip()
