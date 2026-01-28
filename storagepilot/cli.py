#!/usr/bin/env python3
"""
StoragePilot CLI Entry Point
============================

Command-line interface for StoragePilot.
This module provides the `storagepilot` command when installed via pip.
"""

import os
import sys
import argparse
from pathlib import Path


def get_package_root() -> Path:
    """Get the root directory of the StoragePilot package."""
    # When installed via pip, this file is in storagepilot/cli.py
    # The package root is the parent of storagepilot/
    return Path(__file__).parent.parent


def setup_path():
    """Add the package root to sys.path for imports."""
    root = get_package_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main():
    """Main CLI entry point for StoragePilot."""
    # Setup import path
    setup_path()

    # Check for --setup flag first (before importing heavy dependencies)
    if "--setup" in sys.argv:
        run_setup()
        return

    # Import and run the main function from the original main.py
    try:
        # Import the main module
        import main as storagepilot_main

        # Run the main function
        storagepilot_main.main()

    except ImportError as e:
        print(f"Error importing StoragePilot: {e}")
        print("Try running: pip install storagepilot")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)


def run_setup():
    """Run the Ollama setup script."""
    import subprocess
    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    console.print(Panel.fit(
        "[bold]StoragePilot Setup[/bold]\n\n"
        "This will install:\n"
        "1. Ollama (local LLM runtime)\n"
        "2. Default model (qwen2.5:0.5b, ~400MB)\n",
        title="Setup",
        border_style="cyan"
    ))

    # Find the setup script
    root = get_package_root()
    script_path = root / "scripts" / "setup_ollama.sh"

    if not script_path.exists():
        # Try to download and run Ollama directly
        console.print("[yellow]Setup script not found. Installing Ollama directly...[/yellow]")

        try:
            # Install Ollama
            console.print("[cyan]Installing Ollama...[/cyan]")
            result = subprocess.run(
                ["curl", "-fsSL", "https://ollama.com/install.sh"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                subprocess.run(["sh", "-c", result.stdout])

            # Pull default model
            console.print("[cyan]Pulling default model (qwen2.5:0.5b)...[/cyan]")
            subprocess.run(["ollama", "pull", "qwen2.5:0.5b"])

            console.print("[green]Setup complete![/green]")
            console.print("\nRun StoragePilot with: storagepilot --dry-run")

        except Exception as e:
            console.print(f"[red]Setup failed: {e}[/red]")
            console.print("\nManual installation:")
            console.print("  1. curl -fsSL https://ollama.com/install.sh | sh")
            console.print("  2. ollama pull qwen2.5:0.5b")
            sys.exit(1)
    else:
        # Run the setup script
        console.print(f"[cyan]Running setup script: {script_path}[/cyan]")
        subprocess.run(["bash", str(script_path)])


if __name__ == "__main__":
    main()
