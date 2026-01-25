#!/usr/bin/env python3
"""
StoragePilot Quick Start
=========================
A standalone scanner that works without CrewAI or API keys.
Perfect for quick storage analysis.

Usage:
    python quick_scan.py
    python quick_scan.py --path ~/Downloads
    python quick_scan.py --all
"""

import os
import sys
import argparse
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import hashlib

# Rich console for pretty output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Tip: Install 'rich' for prettier output: pip install rich")

console = Console() if RICH_AVAILABLE else None


def human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def get_dir_size(path: str) -> int:
    """Get total size of a directory."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False):
                total += get_dir_size(entry.path)
    except (PermissionError, FileNotFoundError):
        pass
    return total


def scan_directory(path: str) -> dict:
    """Scan a directory and return analysis."""
    path = os.path.expanduser(path)
    
    if not os.path.exists(path):
        return {"error": f"Path not found: {path}"}
    
    result = {
        "path": path,
        "total_size": 0,
        "file_count": 0,
        "dir_count": 0,
        "by_extension": defaultdict(lambda: {"count": 0, "size": 0}),
        "by_category": defaultdict(lambda: {"count": 0, "size": 0, "files": []}),
        "large_files": [],
        "old_files": [],
        "potential_duplicates": [],
        "developer_artifacts": [],
    }
    
    # Extension to category mapping
    categories = {
        ".pdf": "documents", ".doc": "documents", ".docx": "documents",
        ".txt": "documents", ".md": "documents",
        ".jpg": "images", ".jpeg": "images", ".png": "images",
        ".gif": "images", ".webp": "images", ".svg": "images",
        ".mp4": "videos", ".mov": "videos", ".avi": "videos",
        ".mp3": "audio", ".wav": "audio", ".flac": "audio",
        ".py": "code", ".js": "code", ".ts": "code", ".java": "code",
        ".zip": "archives", ".tar": "archives", ".gz": "archives",
        ".dmg": "installers", ".pkg": "installers", ".exe": "installers",
        ".csv": "data", ".json": "data", ".xml": "data",
    }
    
    # Developer artifact patterns
    dev_artifacts = ["node_modules", ".venv", "venv", "__pycache__", 
                     ".git", "target", "build", "dist"]
    
    now = datetime.now()
    hash_to_files = defaultdict(list)
    
    try:
        for root, dirs, files in os.walk(path):
            # Check for developer artifacts
            for d in dirs:
                if d in dev_artifacts:
                    artifact_path = os.path.join(root, d)
                    try:
                        size = get_dir_size(artifact_path)
                        result["developer_artifacts"].append({
                            "path": artifact_path,
                            "type": d,
                            "size": size,
                            "size_human": human_readable_size(size)
                        })
                    except:
                        pass
            
            result["dir_count"] += len(dirs)
            
            for file in files:
                if file.startswith('.'):
                    continue
                    
                file_path = os.path.join(root, file)
                
                try:
                    stat = os.stat(file_path)
                    size = stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    
                    result["file_count"] += 1
                    result["total_size"] += size
                    
                    # By extension
                    ext = os.path.splitext(file)[1].lower()
                    result["by_extension"][ext]["count"] += 1
                    result["by_extension"][ext]["size"] += size
                    
                    # By category
                    category = categories.get(ext, "other")
                    result["by_category"][category]["count"] += 1
                    result["by_category"][category]["size"] += size
                    if len(result["by_category"][category]["files"]) < 10:
                        result["by_category"][category]["files"].append(file)
                    
                    # Large files (> 100MB)
                    if size > 100 * 1024 * 1024:
                        result["large_files"].append({
                            "path": file_path,
                            "name": file,
                            "size": size,
                            "size_human": human_readable_size(size)
                        })
                    
                    # Old files (> 90 days)
                    age_days = (now - mtime).days
                    if age_days > 90:
                        result["old_files"].append({
                            "path": file_path,
                            "name": file,
                            "age_days": age_days,
                            "size": size
                        })
                    
                    # Potential duplicates (by size, quick check)
                    if size > 1024:  # Only files > 1KB
                        hash_to_files[size].append(file_path)
                        
                except (PermissionError, FileNotFoundError):
                    pass
                    
    except Exception as e:
        result["error"] = str(e)
    
    # Find potential duplicates
    for size, files in hash_to_files.items():
        if len(files) > 1:
            result["potential_duplicates"].append({
                "size": size,
                "size_human": human_readable_size(size),
                "files": files[:5]  # Limit to 5
            })
    
    # Sort results
    result["large_files"].sort(key=lambda x: x["size"], reverse=True)
    result["old_files"].sort(key=lambda x: x["age_days"], reverse=True)
    result["developer_artifacts"].sort(key=lambda x: x["size"], reverse=True)
    result["potential_duplicates"].sort(key=lambda x: x["size"] * len(x["files"]), reverse=True)
    
    # Limit results
    result["large_files"] = result["large_files"][:20]
    result["old_files"] = result["old_files"][:20]
    result["potential_duplicates"] = result["potential_duplicates"][:10]
    
    # Convert defaultdicts to regular dicts
    result["by_extension"] = dict(result["by_extension"])
    result["by_category"] = dict(result["by_category"])
    
    result["total_size_human"] = human_readable_size(result["total_size"])
    
    return result


def print_results(results: dict):
    """Print scan results."""
    
    if RICH_AVAILABLE:
        print_results_rich(results)
    else:
        print_results_plain(results)


def print_results_rich(results: dict):
    """Print results using rich library."""
    
    # Header
    console.print(Panel.fit(
        f"[bold cyan]📁 {results['path']}[/bold cyan]\n"
        f"[green]{results['total_size_human']}[/green] in "
        f"[yellow]{results['file_count']}[/yellow] files",
        title="Storage Analysis",
        border_style="cyan"
    ))
    
    # Categories
    console.print("\n[bold]📊 By Category:[/bold]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Size", justify="right", style="green")
    
    sorted_cats = sorted(
        results["by_category"].items(),
        key=lambda x: x[1]["size"],
        reverse=True
    )
    
    for cat, data in sorted_cats[:10]:
        table.add_row(
            cat.capitalize(),
            str(data["count"]),
            human_readable_size(data["size"])
        )
    
    console.print(table)
    
    # Large files
    if results["large_files"]:
        console.print("\n[bold]📦 Large Files (>100MB):[/bold]")
        table = Table(show_header=True)
        table.add_column("File", style="yellow")
        table.add_column("Size", justify="right", style="red")
        
        for f in results["large_files"][:10]:
            table.add_row(f["name"][:50], f["size_human"])
        
        console.print(table)
    
    # Developer artifacts
    if results["developer_artifacts"]:
        console.print("\n[bold]🔧 Developer Artifacts:[/bold]")
        total_artifact_size = sum(a["size"] for a in results["developer_artifacts"])
        console.print(f"   [yellow]Total: {human_readable_size(total_artifact_size)}[/yellow]")
        
        table = Table(show_header=True)
        table.add_column("Type", style="cyan")
        table.add_column("Path")
        table.add_column("Size", justify="right", style="green")
        
        for a in results["developer_artifacts"][:10]:
            table.add_row(
                a["type"],
                a["path"][-50:],
                a["size_human"]
            )
        
        console.print(table)
    
    # Potential duplicates
    if results["potential_duplicates"]:
        console.print("\n[bold]🔄 Potential Duplicates:[/bold]")
        for dup in results["potential_duplicates"][:5]:
            console.print(f"   [dim]{dup['size_human']}[/dim]: {len(dup['files'])} files")
    
    # Recommendations
    console.print("\n[bold]💡 Recommendations:[/bold]")
    
    if results["developer_artifacts"]:
        total = sum(a["size"] for a in results["developer_artifacts"])
        console.print(f"   • Clean developer artifacts to save [green]{human_readable_size(total)}[/green]")
    
    if results["large_files"]:
        console.print(f"   • Review {len(results['large_files'])} large files")
    
    cat = results["by_category"].get("installers", {})
    if cat.get("size", 0) > 0:
        console.print(f"   • Remove installers to save [green]{human_readable_size(cat['size'])}[/green]")


def print_results_plain(results: dict):
    """Print results using plain text."""
    
    print("\n" + "=" * 60)
    print(f"📁 Storage Analysis: {results['path']}")
    print("=" * 60)
    print(f"\nTotal: {results['total_size_human']} in {results['file_count']} files")
    
    print("\n📊 By Category:")
    sorted_cats = sorted(
        results["by_category"].items(),
        key=lambda x: x[1]["size"],
        reverse=True
    )
    for cat, data in sorted_cats[:10]:
        print(f"   {cat:15} {data['count']:5} files  {human_readable_size(data['size']):>10}")
    
    if results["large_files"]:
        print("\n📦 Large Files (>100MB):")
        for f in results["large_files"][:5]:
            print(f"   {f['size_human']:>10}  {f['name'][:40]}")
    
    if results["developer_artifacts"]:
        print("\n🔧 Developer Artifacts:")
        total = sum(a["size"] for a in results["developer_artifacts"])
        print(f"   Total: {human_readable_size(total)}")
        for a in results["developer_artifacts"][:5]:
            print(f"   {a['size_human']:>10}  {a['type']:15} {a['path'][-40:]}")
    
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="StoragePilot Quick Scan - Analyze storage usage"
    )
    parser.add_argument(
        "--path", "-p",
        type=str,
        default="~/Downloads",
        help="Path to scan (default: ~/Downloads)"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Scan all common directories"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    
    args = parser.parse_args()
    
    if args.all:
        paths = ["~/Downloads", "~/Desktop", "~/Documents", "~/workspace"]
    else:
        paths = [args.path]
    
    all_results = {}
    
    for path in paths:
        expanded_path = os.path.expanduser(path)
        if os.path.exists(expanded_path):
            if RICH_AVAILABLE:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task(f"Scanning {path}...", total=None)
                    results = scan_directory(path)
                    progress.update(task, completed=True)
            else:
                print(f"Scanning {path}...")
                results = scan_directory(path)
            
            all_results[path] = results
            
            if args.json:
                print(json.dumps(results, indent=2, default=str))
            else:
                print_results(results)
    
    # Summary if multiple paths
    if len(all_results) > 1 and not args.json:
        total_size = sum(r.get("total_size", 0) for r in all_results.values())
        total_files = sum(r.get("file_count", 0) for r in all_results.values())
        
        if RICH_AVAILABLE:
            console.print(Panel.fit(
                f"[bold]Total across all directories:[/bold]\n"
                f"[green]{human_readable_size(total_size)}[/green] in "
                f"[yellow]{total_files}[/yellow] files",
                title="Summary",
                border_style="green"
            ))
        else:
            print(f"\n{'=' * 60}")
            print(f"TOTAL: {human_readable_size(total_size)} in {total_files} files")
            print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
