#!/usr/bin/env python3
"""
StoragePilot Setup Wizard
=========================
Cross-platform interactive CLI for configuring StoragePilot.

Supports:
- Windows, macOS, Linux, WSL
- Ollama (auto-detect models), OpenAI, Anthropic, MatrixLLM
- Cross-platform scan path configuration
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

# Add project root for imports
sys.path.insert(0, str(PROJECT_ROOT))


# ----------------------------
# Platform detection helpers
# ----------------------------

def is_windows() -> bool:
    return platform.system().lower() == "windows"


def is_macos() -> bool:
    return platform.system().lower() == "darwin"


def is_linux() -> bool:
    return platform.system().lower() == "linux"


def is_wsl() -> bool:
    if not is_linux():
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


def get_os_description() -> str:
    """Get a human-readable OS description."""
    if is_wsl():
        return "WSL (Windows Subsystem for Linux)"
    elif is_windows():
        return f"Windows {platform.release()}"
    elif is_macos():
        return f"macOS {platform.mac_ver()[0]}"
    elif is_linux():
        # Try to get distro name
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
        return f"Linux {platform.release()}"
    return platform.system()


# ----------------------------
# Input helpers
# ----------------------------

def prompt(msg: str, default: Optional[str] = None) -> str:
    """Prompt for input with optional default value."""
    if default is not None and default != "":
        s = input(f"{msg} [{default}]: ").strip()
        return s if s else default
    return input(f"{msg}: ").strip()


def prompt_secret(msg: str) -> str:
    """Prompt for secret input (API keys)."""
    try:
        import getpass
        return getpass.getpass(f"{msg}: ").strip()
    except Exception:
        # Fallback for terminals that don't support getpass
        return input(f"{msg} (visible): ").strip()


def choose(title: str, options: List[str], default_index: int = 0) -> str:
    """Present a numbered menu and return the selected option."""
    print(f"\n{title}")
    for i, opt in enumerate(options, start=1):
        marker = " (default)" if (i - 1) == default_index else ""
        print(f"  {i}. {opt}{marker}")
    while True:
        raw = input("Select number: ").strip()
        if raw == "":
            return options[default_index]
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        print("Invalid selection. Try again.")


def yes_no(msg: str, default: bool = True) -> bool:
    """Ask a yes/no question."""
    suffix = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{msg} [{suffix}]: ").strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Please answer y or n.")


# ----------------------------
# Network helpers
# ----------------------------

def http_json(url: str, timeout_s: int = 5) -> Any:
    """Make HTTP GET request and return JSON."""
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout_s) as resp:
        data = resp.read().decode("utf-8", errors="ignore")
        return json.loads(data)


def try_run(cmd: List[str]) -> Tuple[int, str]:
    """Run a command and return (returncode, output)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
        return p.returncode, out.strip()
    except Exception as e:
        return 1, str(e)


# ----------------------------
# Ollama helpers
# ----------------------------

def detect_default_ollama_base_url() -> str:
    """Detect the default Ollama base URL."""
    return "http://127.0.0.1:11434/v1"


def check_ollama_running(base_url: str) -> Tuple[bool, str]:
    """Check if Ollama is running and return (ok, message)."""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    root = root.rstrip("/")

    try:
        http_json(f"{root}/api/tags", timeout_s=3)
        return True, "Ollama is running"
    except Exception as e:
        return False, str(e)


def list_ollama_models(base_url: str) -> List[str]:
    """
    List installed Ollama models.
    Tries HTTP API first, then CLI fallback.
    """
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    root = root.rstrip("/")

    # 1) HTTP native API
    try:
        j = http_json(f"{root}/api/tags", timeout_s=4)
        models = []
        for m in (j.get("models") or []):
            name = m.get("name")
            if name:
                models.append(name)
        models = sorted(set(models))
        if models:
            return models
    except Exception:
        pass

    # 2) CLI fallback
    code, out = try_run(["ollama", "list"])
    if code == 0 and out:
        models = []
        for line in out.splitlines()[1:]:  # Skip header
            parts = line.split()
            if parts:
                models.append(parts[0])
        models = sorted(set(models))
        return models

    return []


# ----------------------------
# OpenAI helpers
# ----------------------------

def list_openai_models(api_key: str, base_url: str = "https://api.openai.com/v1") -> List[str]:
    """List available OpenAI models."""
    try:
        req = Request(
            f"{base_url.rstrip('/')}/models",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["id"] for m in data.get("data", [])]
            # Filter to common chat models
            chat_models = [m for m in models if any(x in m for x in ["gpt", "o1", "o3"])]
            return sorted(chat_models) if chat_models else sorted(models)[:20]
    except Exception:
        return []


# ----------------------------
# File helpers
# ----------------------------

def write_env(env_path: Path, kv: Dict[str, str]) -> None:
    """Update or create .env file with key-value pairs."""
    existing = ""
    if env_path.exists():
        existing = env_path.read_text(errors="ignore")

    lines = existing.splitlines()
    present = {}
    for i, line in enumerate(lines):
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$", line)
        if m:
            present[m.group(1)] = i

    for k, v in kv.items():
        new_line = f"{k}={v}"
        if k in present:
            lines[present[k]] = new_line
        else:
            lines.append(new_line)

    env_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def yaml_dump_minimal(d: Dict[str, Any], indent: int = 0) -> str:
    """
    Minimal YAML writer (avoids PyYAML dependency).
    Handles nested dicts, lists, and scalars.
    """
    sp = "  " * indent
    lines = []

    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{sp}{k}:")
            lines.append(yaml_dump_minimal(v, indent + 1))
        elif isinstance(v, list):
            lines.append(f"{sp}{k}:")
            for item in v:
                if isinstance(item, dict):
                    # Complex list item
                    lines.append(f"{sp}  -")
                    for ik, iv in item.items():
                        lines.append(f"{sp}    {ik}: {_yaml_scalar(iv)}")
                else:
                    lines.append(f"{sp}  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{sp}{k}: {_yaml_scalar(v)}")

    return "\n".join(lines)


def _yaml_scalar(x: Any) -> str:
    """Convert a scalar value to YAML string."""
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, (int, float)):
        return str(x)
    s = str(x)
    # Quote if special characters
    needs_quote = (
        s == "" or
        any(c in s for c in [":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", ">", "!", "%", "@", "`", "\"", "'"]) or
        s.strip() != s
    )
    if needs_quote:
        s = s.replace("\\", "\\\\").replace("\"", "\\\"")
        return f'"{s}"'
    return s


# ----------------------------
# Path resolution preview
# ----------------------------

def preview_resolved_paths(raw_paths: List[str]) -> List[Tuple[str, str, bool]]:
    """
    Preview how paths will be resolved.
    Returns list of (raw_path, resolved_path, exists).
    """
    try:
        from tools.path_resolver import resolve_special_path
    except ImportError:
        # Fallback if path_resolver not available
        def resolve_special_path(raw):
            expanded = Path(os.path.expanduser(os.path.expandvars(raw))).resolve()
            return [expanded] if expanded.exists() else []

    results = []
    for raw in raw_paths:
        if raw == ".":
            resolved = str(Path.cwd())
            exists = True
        else:
            cands = resolve_special_path(raw)
            if cands:
                resolved = str(cands[0])
                exists = True
            else:
                resolved = os.path.expanduser(raw)
                exists = os.path.exists(resolved)
        results.append((raw, resolved, exists))
    return results


# ----------------------------
# Wizard flow
# ----------------------------

def print_banner():
    """Print the setup wizard banner."""
    print()
    print("=" * 60)
    print("        StoragePilot Setup Wizard")
    print("        AI-Powered Storage Lifecycle Manager")
    print("=" * 60)
    print()
    print(f"  Project:  {PROJECT_ROOT}")
    print(f"  OS:       {get_os_description()}")
    print()


def configure_llm() -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Configure LLM provider. Returns (llm_config, env_vars)."""
    env_vars = {}
    llm = {}

    provider_choice = choose(
        "Choose LLM provider:",
        [
            "Ollama (local, no API key needed)",
            "OpenAI (official API)",
            "OpenAI-compatible (custom endpoint)",
            "Anthropic (Claude API)",
            "MatrixLLM (local adapter)",
        ],
        default_index=0
    )

    llm["temperature"] = float(prompt("LLM temperature (0.0-1.0)", "0.1") or "0.1")

    if provider_choice.startswith("Ollama"):
        llm["provider"] = "ollama"
        base_url = prompt("Ollama base URL", detect_default_ollama_base_url())
        llm["base_url"] = base_url

        # Check if Ollama is running
        ok, msg = check_ollama_running(base_url)
        if ok:
            print(f"\n  [OK] {msg}")
            models = list_ollama_models(base_url)
            if models:
                print(f"  Found {len(models)} installed model(s)")
                model = choose("Select Ollama model:", models, default_index=0)
            else:
                print("  No models found. You may need to run: ollama pull <model>")
                model = prompt("Enter model name", "llama3:8b")
        else:
            print(f"\n  [WARNING] Ollama not running: {msg}")
            print("  You can start it with: ollama serve")
            model = prompt("Enter model name (will be used when Ollama starts)", "llama3:8b")

        llm["model"] = model

    elif provider_choice.startswith("OpenAI (official"):
        llm["provider"] = "openai"
        api_key = prompt_secret("OpenAI API key")

        if api_key:
            env_vars["OPENAI_API_KEY"] = api_key
            # Try to list models
            print("\n  Fetching available models...")
            models = list_openai_models(api_key)
            if models:
                # Prioritize common models
                priority = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
                sorted_models = [m for m in priority if m in models]
                sorted_models += [m for m in models if m not in sorted_models]
                model = choose("Select OpenAI model:", sorted_models[:10], default_index=0)
            else:
                model = prompt("Enter model name", "gpt-4o-mini")
        else:
            model = prompt("Enter model name", "gpt-4o-mini")

        llm["model"] = model

    elif provider_choice.startswith("OpenAI-compatible"):
        llm["provider"] = "openai"
        llm["base_url"] = prompt("Custom base URL", "http://localhost:8000/v1")
        api_key = prompt_secret("API key (or press Enter for none)")
        if api_key:
            env_vars["OPENAI_API_KEY"] = api_key
        llm["model"] = prompt("Model name", "default")

    elif provider_choice.startswith("Anthropic"):
        llm["provider"] = "anthropic"
        api_key = prompt_secret("Anthropic API key")
        if api_key:
            env_vars["ANTHROPIC_API_KEY"] = api_key

        models = [
            "claude-3-5-sonnet-20241022",
            "claude-3-haiku-20240307",
            "claude-3-opus-20240229",
        ]
        llm["model"] = choose("Select Anthropic model:", models, default_index=0)

    elif provider_choice.startswith("MatrixLLM"):
        llm["provider"] = "matrixllm"
        llm["base_url"] = prompt("MatrixLLM base URL", "http://127.0.0.1:11435/v1")
        llm["model"] = prompt("Model name", "deepseek-r1")

        if yes_no("Do you have a MatrixLLM token?", default=False):
            token = prompt_secret("MatrixLLM token")
            if token:
                env_vars["MATRIXLLM_TOKEN"] = token

    return llm, env_vars


def configure_scan_paths() -> Dict[str, List[str]]:
    """Configure scan paths with cross-platform support."""
    print("\n--- Scan Paths Configuration ---")

    scan_paths = {
        "primary": [],
        "secondary": [],
        "workspace": []
    }

    if yes_no("Use recommended scan paths for your platform?", default=True):
        # Common paths that work on all platforms
        scan_paths["primary"] = [".", "~/Downloads", "~/Desktop"]
        scan_paths["secondary"] = ["~/Documents", "~/Pictures"]
        scan_paths["workspace"] = ["~/workspace", "~/projects", "~/dev"]

        # WSL-specific additions
        if is_wsl():
            print("\n  Detected WSL - adding Windows path mappings")
            scan_paths["workspace"].extend([
                "/mnt/c/workspace",
                "/mnt/c/projects",
                "/mnt/c/dev"
            ])

        # Preview resolved paths
        all_paths = scan_paths["primary"] + scan_paths["secondary"] + scan_paths["workspace"]
        print("\n  Path resolution preview:")
        for raw, resolved, exists in preview_resolved_paths(all_paths):
            status = "[OK]" if exists else "[SKIP]"
            if raw != resolved and exists:
                print(f"    {status} {raw} -> {resolved}")
            else:
                print(f"    {status} {raw}")

    else:
        print("\nEnter paths (comma-separated) for each category:")

        primary = prompt("Primary paths (e.g., ~/Downloads,~/Desktop)", "~/Downloads,~/Desktop")
        scan_paths["primary"] = [p.strip() for p in primary.split(",") if p.strip()]

        secondary = prompt("Secondary paths (e.g., ~/Documents)", "~/Documents")
        scan_paths["secondary"] = [p.strip() for p in secondary.split(",") if p.strip()]

        workspace = prompt("Workspace paths (e.g., ~/projects)", "~/workspace,~/projects")
        scan_paths["workspace"] = [p.strip() for p in workspace.split(",") if p.strip()]

    return scan_paths


def configure_safety() -> Dict[str, Any]:
    """Configure safety settings."""
    print("\n--- Safety Settings ---")

    safety = {
        "dry_run": yes_no("Default to DRY RUN mode (preview only)?", default=True),
        "require_approval": yes_no("Require approval before cleanup actions?", default=True),
        "backup_before_delete": yes_no("Create backups before deleting files?", default=True),
        "backup_location": "~/.storagepilot_backup",
        "backup_retention_days": 30,
        "protected_paths": [
            "~/.ssh",
            "~/.gnupg",
            "~/.aws",
            "~/.config",
            "~/.local/share"
        ],
        "protected_extensions": [".env", ".pem", ".key", ".crt"],
        "max_single_delete_gb": 10,
        "enable_undo_log": True,
        "undo_log_path": "logs/undo.json"
    }

    return safety


def wizard() -> None:
    """Run the interactive setup wizard."""
    print_banner()

    # Config paths
    config_path = Path(prompt("Config file path", str(DEFAULT_CONFIG_PATH))).expanduser()
    env_path = Path(prompt("Env file path", str(DEFAULT_ENV_PATH))).expanduser()

    # LLM configuration
    print("\n--- LLM Configuration ---")
    llm_config, env_vars = configure_llm()

    # Scan paths configuration
    scan_paths = configure_scan_paths()

    # Safety settings
    safety = configure_safety()

    # Build final config
    cfg = {
        "llm": llm_config,
        "scan_paths": scan_paths,
        "safety": safety,
        "ui": {
            "theme": "dark",
            "refresh_interval": 2,
            "show_terminal_output": True,
            "enable_sounds": False
        },
        "logging": {
            "level": "INFO",
            "file": "logs/storagepilot.log",
            "console": True,
            "rotation": "10 MB"
        }
    }

    # Write config file
    print("\n--- Writing Configuration ---")

    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Add header comment
    config_text = "# StoragePilot Configuration\n"
    config_text += f"# Generated by setup wizard on {platform.node()}\n"
    config_text += "# =========================\n\n"
    config_text += yaml_dump_minimal(cfg)

    config_path.write_text(config_text, encoding="utf-8")
    print(f"  Wrote config: {config_path}")

    # Write env file if needed
    if env_vars:
        write_env(env_path, env_vars)
        print(f"  Updated env:  {env_path}")

    # Success message
    print()
    print("=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print()
    print("  1. Review your configuration:")
    print(f"     cat {config_path}")
    print()
    print("  2. Run StoragePilot:")
    print("     make run              # CLI (dry-run mode)")
    print("     make api              # Web dashboard")
    print()
    if llm_config.get("provider") == "ollama":
        print("  3. Make sure Ollama is running:")
        print("     ollama serve")
        print(f"     ollama pull {llm_config.get('model', 'llama3:8b')}")
        print()
    print()


def main():
    """Main entry point."""
    try:
        wizard()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
