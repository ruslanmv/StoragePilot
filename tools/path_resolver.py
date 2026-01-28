# tools/path_resolver.py
"""
Cross-platform path resolution for StoragePilot.
Handles Windows, macOS, Linux, and WSL path mappings automatically.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from crewai.tools import tool


# -------------------------
# Platform detection helpers
# -------------------------

def is_wsl() -> bool:
    """Check if running under Windows Subsystem for Linux."""
    if platform.system().lower() != "linux":
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


def _read_xdg_user_dirs() -> Dict[str, Path]:
    """
    Reads ~/.config/user-dirs.dirs if present (Linux XDG user dirs).
    Returns keys: DOWNLOAD, DESKTOP, DOCUMENTS, PICTURES, etc.
    """
    result: Dict[str, Path] = {}
    cfg = Path.home() / ".config" / "user-dirs.dirs"
    if not cfg.exists():
        return result

    # Example line: XDG_DOWNLOAD_DIR="$HOME/Downloads"
    pattern = re.compile(r'XDG_(\w+)_DIR="?(.+?)"?$')
    for line in cfg.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = pattern.search(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        val = val.replace("$HOME", str(Path.home()))
        p = Path(os.path.expandvars(val)).expanduser()
        result[key] = p
    return result


def _wsl_windows_userprofile_mount() -> Optional[Path]:
    """
    In WSL, try to get Windows %USERPROFILE% and convert:
      C:\\Users\\Name  -> /mnt/c/Users/Name
    """
    if not is_wsl():
        return None

    # Try cmd.exe first, then powershell
    for cmd in (
        ["cmd.exe", "/c", "echo", "%USERPROFILE%"],
        ["powershell.exe", "-NoProfile", "-Command", "$env:USERPROFILE"]
    ):
        try:
            out = subprocess.check_output(
                cmd, stderr=subprocess.DEVNULL, text=True
            ).strip()
            if not out or "%" in out:  # Variable not expanded
                continue
            # Normalize: C:\Users\Name -> /mnt/c/Users/Name
            drive = out[0].lower()
            rest = out[2:].replace("\\", "/")
            candidate = Path(f"/mnt/{drive}{rest}")
            if candidate.exists():
                return candidate
        except Exception:
            pass

    # Fallback: guess /mnt/c/Users/<linuxuser>
    linux_user = os.getenv("USER") or ""
    guess = Path("/mnt/c/Users") / linux_user
    if guess.exists():
        return guess

    # Fallback: pick first user dir under /mnt/c/Users with Downloads
    base = Path("/mnt/c/Users")
    if base.exists():
        for p in base.iterdir():
            if p.is_dir() and p.name.lower() not in ("public", "default", "default user", "all users"):
                if (p / "Downloads").exists():
                    return p

    return None


# -------------------------
# Core resolution logic
# -------------------------

def resolve_special_path(raw: str) -> List[Path]:
    """
    Takes a raw path from config like "~/Downloads" and returns a list of
    candidate existing paths (best-first).
    """
    raw = (raw or "").strip()
    if not raw:
        return []

    # 1) Standard expansion
    expanded = Path(os.path.expanduser(os.path.expandvars(raw))).resolve()
    if expanded.exists():
        return [expanded]

    # If it wasn't one of the typical home folders, stop here.
    # We only "guess" alternates for common folders.
    homeish = raw.startswith("~/") or raw.startswith("~\\")
    if not homeish:
        return []

    leaf = Path(raw).name.lower()  # Downloads, Desktop, Documents...
    candidates: List[Path] = []

    sysname = platform.system().lower()

    # 2) Linux XDG dirs (non-WSL)
    if sysname == "linux" and not is_wsl():
        xdg = _read_xdg_user_dirs()
        mapping = {
            "downloads": xdg.get("DOWNLOAD"),
            "desktop": xdg.get("DESKTOP"),
            "documents": xdg.get("DOCUMENTS"),
            "pictures": xdg.get("PICTURES"),
            "music": xdg.get("MUSIC"),
            "videos": xdg.get("VIDEOS"),
        }
        p = mapping.get(leaf)
        if p:
            candidates.append(p)

    # 3) macOS standard dirs (usually exist, but still check)
    if sysname == "darwin":
        mapping = {
            "downloads": Path.home() / "Downloads",
            "desktop": Path.home() / "Desktop",
            "documents": Path.home() / "Documents",
            "pictures": Path.home() / "Pictures",
            "music": Path.home() / "Music",
            "movies": Path.home() / "Movies",
        }
        p = mapping.get(leaf)
        if p:
            candidates.append(p)

    # 4) WSL: map to Windows user profile folders
    if is_wsl():
        winhome = _wsl_windows_userprofile_mount()
        if winhome:
            mapping = {
                "downloads": winhome / "Downloads",
                "desktop": winhome / "Desktop",
                "documents": winhome / "Documents",
                "pictures": winhome / "Pictures",
                "music": winhome / "Music",
                "videos": winhome / "Videos",
            }
            p = mapping.get(leaf)
            if p:
                candidates.append(p)

    # 5) Windows native (when running Python for Windows)
    if sysname == "windows":
        # Use USERPROFILE or HOMEDRIVE+HOMEPATH
        win_home = os.environ.get("USERPROFILE")
        if win_home:
            win_home_path = Path(win_home)
            mapping = {
                "downloads": win_home_path / "Downloads",
                "desktop": win_home_path / "Desktop",
                "documents": win_home_path / "Documents",
                "pictures": win_home_path / "Pictures",
                "music": win_home_path / "Music",
                "videos": win_home_path / "Videos",
            }
            p = mapping.get(leaf)
            if p:
                candidates.append(p)

    # 6) Generic fallback under Linux home
    generic = Path.home() / leaf.capitalize()
    candidates.append(generic)

    # 7) Add workspace-like folders
    if leaf in {"workspace", "projects", "dev"}:
        candidates.append(Path.home() / leaf)

        if is_wsl():
            # Common Windows dev roots
            candidates.append(Path("/mnt/c/workspace"))
            candidates.append(Path("/mnt/c/projects"))
            candidates.append(Path("/mnt/c/dev"))

    # Keep only existing, unique paths
    uniq: List[Path] = []
    seen = set()
    for c in candidates:
        if not c or str(c) in seen:
            continue
        seen.add(str(c))
        if c.exists():
            uniq.append(c)

    return uniq


def resolve_scan_paths(raw_paths: List[str]) -> List[str]:
    """
    Resolves a list of raw paths and returns existing resolved paths as strings.
    """
    resolved: List[str] = []
    for raw in raw_paths:
        if raw == ".":
            p = Path.cwd()
            resolved.append(str(p))
            continue

        # Best-first: expanded, then alternates
        cands = resolve_special_path(raw)
        if cands:
            resolved.append(str(cands[0]))
        else:
            # Fallback: try simple expansion one more time
            expanded = os.path.expanduser(os.path.expandvars(raw))
            if os.path.exists(expanded):
                resolved.append(expanded)

    # De-dupe preserving order
    out: List[str] = []
    seen = set()
    for p in resolved:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


# -------------------------
# CrewAI Tool wrapper
# -------------------------

@tool("resolve_paths")
def resolve_paths_tool(paths_csv: str) -> str:
    """
    Resolve a comma-separated list of paths into OS-correct existing paths.
    Example input: "~/Downloads,~/Desktop,~/Documents"
    Returns resolved paths, one per line, or a message if none found.
    """
    raw = [p.strip() for p in (paths_csv or "").split(",") if p.strip()]
    resolved = resolve_scan_paths(raw)
    return "\n".join(resolved) if resolved else "(no existing paths resolved)"
