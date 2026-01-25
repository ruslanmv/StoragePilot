#!/usr/bin/env python3
"""
StoragePilot - AI-Powered Storage Lifecycle Manager
=====================================================

A multi-agent AI system that autonomously analyzes, organizes, 
and optimizes storage on developer workstations.

Usage:
    python main.py --dry-run              # Preview mode (safe)
    python main.py --execute              # Execute with approval
    python main.py --scan-only            # Only scan, no actions
    python main.py --ui                   # Launch Streamlit UI
"""

import os
import sys
import argparse
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from crewai import Crew, Process
from agents import create_all_agents
from agents.tasks import create_all_tasks
from tools import TerminalTools


console = Console()


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_file = Path(__file__).parent / config_path
    
    if not config_file.exists():
        console.print(f"[yellow]Config file not found at {config_file}[/yellow]")
        console.print("[yellow]Using default configuration...[/yellow]")
        return get_default_config()
    
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)


def get_default_config() -> dict:
    """Get default configuration."""
    return {
        "scan_paths": {
            "primary": ["~/Downloads", "~/Desktop"],
            "secondary": ["~/Documents"],
            "workspace": ["~/workspace", "~/projects"]
        },
        "safety": {
            "dry_run": True,
            "require_approval": True,
            "backup_before_delete": True
        },
        "llm": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.1
        }
    }


def get_llm(config: dict):
    """Initialize the LLM based on configuration."""
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "openai")
    model = llm_config.get("model", "gpt-4o-mini")
    temperature = llm_config.get("temperature", 0.1)
    
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            temperature=temperature
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            temperature=temperature
        )
    else:
        # Default to OpenAI
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.1
        )


def get_scan_paths(config: dict) -> List[str]:
    """Extract all scan paths from configuration."""
    paths = []
    scan_config = config.get("scan_paths", {})
    
    for category in ["primary", "secondary", "workspace"]:
        paths.extend(scan_config.get(category, []))
    
    # Expand user paths and filter existing ones
    expanded_paths = []
    for path in paths:
        expanded = os.path.expanduser(path)
        if os.path.exists(expanded):
            expanded_paths.append(path)
        else:
            console.print(f"[dim]Skipping non-existent path: {path}[/dim]")
    
    return expanded_paths


def print_banner():
    """Print the application banner."""
    banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   ███████╗████████╗ ██████╗ ██████╗  █████╗  ██████╗ ███████╗ ║
    ║   ██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗██╔══██╗██╔════╝ ██╔════╝ ║
    ║   ███████╗   ██║   ██║   ██║██████╔╝███████║██║  ███╗█████╗   ║
    ║   ╚════██║   ██║   ██║   ██║██╔══██╗██╔══██║██║   ██║██╔══╝   ║
    ║   ███████║   ██║   ╚██████╔╝██║  ██║██║  ██║╚██████╔╝███████╗ ║
    ║   ╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝ ║
    ║                                                               ║
    ║               ██████╗ ██╗██╗      ██████╗ ████████╗           ║
    ║               ██╔══██╗██║██║     ██╔═══██╗╚══██╔══╝           ║
    ║               ██████╔╝██║██║     ██║   ██║   ██║              ║
    ║               ██╔═══╝ ██║██║     ██║   ██║   ██║              ║
    ║               ██║     ██║███████╗╚██████╔╝   ██║              ║
    ║               ╚═╝     ╚═╝╚══════╝ ╚═════╝    ╚═╝              ║
    ║                                                               ║
    ║          AI-Powered Storage Lifecycle Manager v1.0            ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


def print_config_summary(config: dict, scan_paths: List[str], dry_run: bool):
    """Print configuration summary."""
    table = Table(title="Configuration Summary", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Mode", "DRY RUN (Preview)" if dry_run else "EXECUTE (Live)")
    table.add_row("LLM Provider", config.get("llm", {}).get("provider", "openai"))
    table.add_row("LLM Model", config.get("llm", {}).get("model", "gpt-4o-mini"))
    table.add_row("Scan Paths", ", ".join(scan_paths))
    table.add_row("Require Approval", str(config.get("safety", {}).get("require_approval", True)))
    
    console.print(table)
    console.print()


def run_quick_scan(scan_paths: List[str]) -> Dict[str, Any]:
    """Run a quick storage scan before starting the crew."""
    console.print("\n[bold]🔍 Running Quick Storage Scan...[/bold]\n")
    
    tools = TerminalTools(dry_run=True)
    results = {
        "system": tools.get_system_overview(),
        "directories": {},
        "docker": None
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        # Scan each directory
        for path in scan_paths:
            task = progress.add_task(f"Scanning {path}...", total=None)
            results["directories"][path] = tools.get_disk_usage(path)
            progress.update(task, completed=True)
        
        # Check Docker
        task = progress.add_task("Checking Docker...", total=None)
        results["docker"] = tools.get_docker_usage()
        progress.update(task, completed=True)
    
    # Print summary
    console.print("\n[bold]📊 Quick Scan Results:[/bold]\n")
    
    if results["system"].get("disk"):
        disk = results["system"]["disk"]
        console.print(f"  💾 Disk Usage: {disk.get('used', 'N/A')} / {disk.get('total', 'N/A')} ({disk.get('percent_used', 'N/A')})")
    
    if results["system"].get("top_directories"):
        console.print("\n  📁 Top Space Consumers:")
        for item in results["system"]["top_directories"][:5]:
            console.print(f"     {item['size']:>8}  {item['path']}")
    
    if results["docker"] and not results["docker"].get("error"):
        console.print("\n  🐳 Docker detected - will analyze container storage")
    
    console.print()
    return results


def run_crew(config: dict, dry_run: bool = True, verbose: bool = True):
    """Run the StoragePilot crew."""
    
    # Get scan paths
    scan_paths = get_scan_paths(config)
    
    if not scan_paths:
        console.print("[red]No valid scan paths found. Please check your configuration.[/red]")
        return None
    
    # Print configuration
    print_config_summary(config, scan_paths, dry_run)
    
    # Run quick scan first
    quick_results = run_quick_scan(scan_paths)
    
    # Confirm before proceeding
    if not dry_run:
        console.print("[yellow]⚠️  EXECUTE mode is enabled. Actions will be performed![/yellow]")
        response = input("\nProceed? (yes/no): ")
        if response.lower() != "yes":
            console.print("[dim]Aborted.[/dim]")
            return None
    
    console.print("\n[bold]🚀 Starting StoragePilot Crew...[/bold]\n")
    
    try:
        # Initialize LLM
        llm = get_llm(config)
        
        # Create agents
        agents = create_all_agents(llm)
        
        # Create tasks
        tasks = create_all_tasks(agents, scan_paths)
        
        # Create crew
        crew = Crew(
            agents=list(agents.values()),
            tasks=tasks,
            process=Process.sequential,
            verbose=verbose,
        )
        
        # Run crew
        console.print("[bold cyan]═══ Crew Execution Started ═══[/bold cyan]\n")
        result = crew.kickoff()
        console.print("\n[bold cyan]═══ Crew Execution Completed ═══[/bold cyan]\n")
        
        return result
        
    except Exception as e:
        console.print(f"\n[red]Error running crew: {e}[/red]")
        console.print("[yellow]Tip: Make sure you have set OPENAI_API_KEY or ANTHROPIC_API_KEY[/yellow]")
        raise


def run_scan_only(config: dict):
    """Run only the storage scan without AI analysis."""
    scan_paths = get_scan_paths(config)
    
    console.print("\n[bold]📊 Storage Scan Results[/bold]\n")
    
    tools = TerminalTools(dry_run=True)
    
    # System overview
    overview = tools.get_system_overview()
    
    # Create results table
    table = Table(title="Disk Usage Overview")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    if overview.get("disk"):
        disk = overview["disk"]
        table.add_row("Total Space", disk.get("total", "N/A"))
        table.add_row("Used Space", disk.get("used", "N/A"))
        table.add_row("Available", disk.get("available", "N/A"))
        table.add_row("Usage %", disk.get("percent_used", "N/A"))
    
    console.print(table)
    console.print()
    
    # Top directories
    if overview.get("top_directories"):
        dir_table = Table(title="Top Space Consumers")
        dir_table.add_column("Size", style="yellow")
        dir_table.add_column("Path", style="white")
        
        for item in overview["top_directories"]:
            dir_table.add_row(item["size"], item["path"])
        
        console.print(dir_table)
        console.print()
    
    # Scan each target directory
    for path in scan_paths:
        usage = tools.get_disk_usage(path)
        
        if usage.get("error"):
            console.print(f"[dim]Skipping {path}: {usage['error']}[/dim]")
            continue
        
        path_table = Table(title=f"📁 {path} ({usage.get('total_size', 'N/A')})")
        path_table.add_column("Size", style="yellow")
        path_table.add_column("Subdirectory", style="white")
        
        for item in usage.get("breakdown", [])[:10]:
            path_table.add_row(item["size"], item["path"])
        
        console.print(path_table)
        console.print()
    
    # Check Docker
    docker = tools.get_docker_usage()
    if not docker.get("error"):
        console.print("[bold]🐳 Docker Storage[/bold]")
        console.print(json.dumps(docker, indent=2))


def launch_ui():
    """Launch the Streamlit UI."""
    import subprocess
    ui_path = Path(__file__).parent / "ui" / "dashboard.py"
    subprocess.run(["streamlit", "run", str(ui_path)])


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="StoragePilot - AI-Powered Storage Lifecycle Manager"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        default=True,
        help="Preview mode - no actual changes (default)"
    )
    parser.add_argument(
        "--execute", 
        action="store_true",
        help="Execute mode - perform actual changes"
    )
    parser.add_argument(
        "--scan-only", 
        action="store_true",
        help="Only scan storage, no AI analysis"
    )
    parser.add_argument(
        "--ui", 
        action="store_true",
        help="Launch Streamlit UI"
    )
    parser.add_argument(
        "--config", 
        type=str, 
        default="config/config.yaml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true",
        default=True,
        help="Verbose output"
    )
    parser.add_argument(
        "--quiet", 
        action="store_true",
        help="Minimal output"
    )
    
    args = parser.parse_args()
    
    # Print banner
    print_banner()
    
    # Load configuration
    config = load_config(args.config)
    
    # Determine dry_run mode
    dry_run = not args.execute
    
    if args.ui:
        launch_ui()
    elif args.scan_only:
        run_scan_only(config)
    else:
        result = run_crew(
            config, 
            dry_run=dry_run, 
            verbose=not args.quiet
        )
        
        if result:
            # Save results
            output_dir = Path(__file__).parent / "logs"
            output_dir.mkdir(exist_ok=True)
            
            output_file = output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(output_file, 'w') as f:
                f.write(str(result))
            
            console.print(f"\n[green]✓ Report saved to: {output_file}[/green]")


if __name__ == "__main__":
    main()
