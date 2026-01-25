"""
Terminal Tools for StoragePilot
================================
Tools for executing system commands safely with logging and dry-run support.
"""

import subprocess
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import shutil


@dataclass
class CommandResult:
    """Result of a terminal command execution."""
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration: float
    dry_run: bool = False


@dataclass
class ActionLog:
    """Log entry for an action."""
    timestamp: str
    action_type: str
    source: str
    destination: Optional[str]
    size_bytes: int
    success: bool
    dry_run: bool
    reversible: bool
    undo_command: Optional[str] = None


class TerminalTools:
    """Safe terminal command execution with logging."""
    
    def __init__(self, dry_run: bool = True, log_path: str = "logs/actions.log"):
        self.dry_run = dry_run
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.action_history: List[ActionLog] = []
    
    def run_command(self, command: str, timeout: int = 300) -> CommandResult:
        """Execute a shell command with timeout and logging."""
        start_time = datetime.now()
        
        if self.dry_run:
            return CommandResult(
                command=command,
                returncode=0,
                stdout=f"[DRY RUN] Would execute: {command}",
                stderr="",
                duration=0.0,
                dry_run=True
            )
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            duration = (datetime.now() - start_time).total_seconds()
            
            return CommandResult(
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration=duration,
                dry_run=False
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                duration=timeout,
                dry_run=False
            )
        except Exception as e:
            return CommandResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr=str(e),
                duration=0.0,
                dry_run=False
            )
    
    def get_disk_usage(self, path: str) -> Dict[str, Any]:
        """Get disk usage for a path using du command."""
        path = os.path.expanduser(path)
        
        # Get total size
        result = self.run_command(f'du -sh "{path}" 2>/dev/null')
        if result.returncode != 0:
            return {"error": result.stderr, "path": path}
        
        total_size = result.stdout.strip().split('\t')[0] if result.stdout else "0"
        
        # Get breakdown by subdirectory
        result = self.run_command(f'du -h --max-depth=1 "{path}" 2>/dev/null | sort -hr | head -20')
        breakdown = []
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 2:
                    breakdown.append({"size": parts[0], "path": parts[1]})
        
        return {
            "path": path,
            "total_size": total_size,
            "breakdown": breakdown
        }
    
    def find_files(
        self,
        path: str,
        pattern: str = "*",
        file_type: str = "f",  # f=file, d=directory
        min_size: Optional[str] = None,
        max_depth: int = 10,
        modified_days: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Find files matching criteria."""
        path = os.path.expanduser(path)
        
        cmd = f'find "{path}" -maxdepth {max_depth} -type {file_type} -name "{pattern}"'
        
        if min_size:
            cmd += f' -size +{min_size}'
        
        if modified_days:
            cmd += f' -mtime +{modified_days}'
        
        cmd += ' 2>/dev/null'
        
        result = self.run_command(cmd)
        
        files = []
        if result.returncode == 0 and result.stdout:
            for file_path in result.stdout.strip().split('\n'):
                if file_path:
                    files.append(self._get_file_info(file_path))
        
        return files
    
    def _get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get detailed information about a file."""
        try:
            stat = os.stat(file_path)
            return {
                "path": file_path,
                "name": os.path.basename(file_path),
                "size_bytes": stat.st_size,
                "size_human": self._human_readable_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "is_dir": os.path.isdir(file_path),
                "extension": os.path.splitext(file_path)[1].lower()
            }
        except Exception as e:
            return {"path": file_path, "error": str(e)}
    
    def _human_readable_size(self, size_bytes: int) -> str:
        """Convert bytes to human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"
    
    def get_docker_usage(self) -> Dict[str, Any]:
        """Get Docker disk usage."""
        result = self.run_command('docker system df --format "{{json .}}"')
        
        if result.returncode != 0:
            return {"error": "Docker not available or not running"}
        
        docker_info = {
            "images": [],
            "containers": [],
            "volumes": [],
            "total_reclaimable": "0B"
        }
        
        # Parse JSON output
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                try:
                    item = json.loads(line)
                    docker_info[item['Type'].lower() + 's'] = item
                except json.JSONDecodeError:
                    pass
        
        # Get detailed image list
        result = self.run_command('docker images --format "{{json .}}"')
        if result.returncode == 0 and result.stdout:
            images = []
            for line in result.stdout.strip().split('\n'):
                try:
                    images.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            docker_info['images_detail'] = images
        
        return docker_info
    
    def move_file(self, source: str, destination: str) -> ActionLog:
        """Move a file with logging and undo support."""
        source = os.path.expanduser(source)
        destination = os.path.expanduser(destination)
        
        # Get file size before moving
        size_bytes = 0
        try:
            size_bytes = os.path.getsize(source)
        except:
            pass
        
        # Ensure destination directory exists
        dest_dir = os.path.dirname(destination)
        if not self.dry_run:
            os.makedirs(dest_dir, exist_ok=True)
        
        result = self.run_command(f'mv "{source}" "{destination}"')
        
        action_log = ActionLog(
            timestamp=datetime.now().isoformat(),
            action_type="move",
            source=source,
            destination=destination,
            size_bytes=size_bytes,
            success=result.returncode == 0,
            dry_run=self.dry_run,
            reversible=True,
            undo_command=f'mv "{destination}" "{source}"'
        )
        
        self.action_history.append(action_log)
        self._write_log(action_log)
        
        return action_log
    
    def delete_file(self, path: str, backup: bool = True) -> ActionLog:
        """Delete a file with optional backup."""
        path = os.path.expanduser(path)
        
        size_bytes = 0
        backup_path = None
        
        try:
            size_bytes = os.path.getsize(path)
        except:
            pass
        
        # Create backup if requested
        if backup and not self.dry_run:
            backup_dir = os.path.expanduser("~/.storagepilot_backup")
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(path)}")
            shutil.copy2(path, backup_path)
        
        result = self.run_command(f'rm -rf "{path}"')
        
        action_log = ActionLog(
            timestamp=datetime.now().isoformat(),
            action_type="delete",
            source=path,
            destination=backup_path,
            size_bytes=size_bytes,
            success=result.returncode == 0,
            dry_run=self.dry_run,
            reversible=backup_path is not None,
            undo_command=f'mv "{backup_path}" "{path}"' if backup_path else None
        )
        
        self.action_history.append(action_log)
        self._write_log(action_log)
        
        return action_log
    
    def create_directory(self, path: str) -> ActionLog:
        """Create a directory."""
        path = os.path.expanduser(path)
        
        result = self.run_command(f'mkdir -p "{path}"')
        
        action_log = ActionLog(
            timestamp=datetime.now().isoformat(),
            action_type="mkdir",
            source=path,
            destination=None,
            size_bytes=0,
            success=result.returncode == 0,
            dry_run=self.dry_run,
            reversible=True,
            undo_command=f'rmdir "{path}"'
        )
        
        self.action_history.append(action_log)
        self._write_log(action_log)
        
        return action_log
    
    def clean_docker(self, prune_all: bool = False) -> Dict[str, Any]:
        """Clean Docker resources."""
        results = {}
        
        # Remove dangling images
        result = self.run_command('docker image prune -f')
        results['dangling_images'] = result.stdout if result.returncode == 0 else result.stderr
        
        # Remove stopped containers
        result = self.run_command('docker container prune -f')
        results['stopped_containers'] = result.stdout if result.returncode == 0 else result.stderr
        
        # Remove unused volumes
        result = self.run_command('docker volume prune -f')
        results['unused_volumes'] = result.stdout if result.returncode == 0 else result.stderr
        
        # Remove build cache
        result = self.run_command('docker builder prune -f')
        results['build_cache'] = result.stdout if result.returncode == 0 else result.stderr
        
        if prune_all:
            result = self.run_command('docker system prune -af')
            results['full_prune'] = result.stdout if result.returncode == 0 else result.stderr
        
        return results
    
    def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """Calculate xxhash of a file for duplicate detection."""
        try:
            import xxhash
            hasher = xxhash.xxh64()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            # Fallback to md5
            hasher = hashlib.md5()
            try:
                with open(file_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(65536), b''):
                        hasher.update(chunk)
                return hasher.hexdigest()
            except:
                return None
    
    def create_stub_file(self, original_path: str, moved_to: str) -> ActionLog:
        """Create a stub file that references where the original was moved."""
        stub_path = original_path + ".stub"
        stub_content = json.dumps({
            "original_path": original_path,
            "moved_to": moved_to,
            "moved_at": datetime.now().isoformat(),
            "restore_command": f'storagepilot restore "{moved_to}" "{original_path}"'
        }, indent=2)
        
        if not self.dry_run:
            with open(stub_path, 'w') as f:
                f.write(stub_content)
        
        action_log = ActionLog(
            timestamp=datetime.now().isoformat(),
            action_type="create_stub",
            source=original_path,
            destination=stub_path,
            size_bytes=len(stub_content),
            success=True,
            dry_run=self.dry_run,
            reversible=True,
            undo_command=f'rm "{stub_path}"'
        )
        
        self.action_history.append(action_log)
        return action_log
    
    def _write_log(self, action_log: ActionLog):
        """Write action log to file."""
        log_entry = {
            "timestamp": action_log.timestamp,
            "action": action_log.action_type,
            "source": action_log.source,
            "destination": action_log.destination,
            "size": action_log.size_bytes,
            "success": action_log.success,
            "dry_run": action_log.dry_run,
            "undo": action_log.undo_command
        }
        
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def get_system_overview(self) -> Dict[str, Any]:
        """Get overall system storage information."""
        # Disk usage
        result = self.run_command('df -h ~ | tail -1')
        disk_info = {}
        if result.returncode == 0 and result.stdout:
            parts = result.stdout.split()
            if len(parts) >= 5:
                disk_info = {
                    "total": parts[1],
                    "used": parts[2],
                    "available": parts[3],
                    "percent_used": parts[4]
                }
        
        # Top space consumers
        result = self.run_command('du -sh ~/* 2>/dev/null | sort -hr | head -15')
        top_dirs = []
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 2:
                    top_dirs.append({"size": parts[0], "path": parts[1]})
        
        return {
            "disk": disk_info,
            "top_directories": top_dirs
        }


# CrewAI Tool Wrappers
from crewai.tools import tool


@tool("scan_directory")
def scan_directory(path: str) -> str:
    """
    Scan a directory and return disk usage information.
    
    Args:
        path: The directory path to scan (e.g., ~/Downloads)
    
    Returns:
        JSON string with directory size breakdown
    """
    tools = TerminalTools(dry_run=True)
    result = tools.get_disk_usage(path)
    return json.dumps(result, indent=2)


@tool("find_large_files")
def find_large_files(path: str, min_size: str = "100M") -> str:
    """
    Find large files in a directory.
    
    Args:
        path: The directory path to search
        min_size: Minimum file size (e.g., "100M", "1G")
    
    Returns:
        JSON string with list of large files
    """
    tools = TerminalTools(dry_run=True)
    files = tools.find_files(path, pattern="*", min_size=min_size)
    return json.dumps(files, indent=2)


@tool("find_old_files")
def find_old_files(path: str, days: int = 90) -> str:
    """
    Find files not modified in the specified number of days.
    
    Args:
        path: The directory path to search
        days: Number of days since last modification
    
    Returns:
        JSON string with list of old files
    """
    tools = TerminalTools(dry_run=True)
    files = tools.find_files(path, pattern="*", modified_days=days)
    return json.dumps(files, indent=2)


@tool("get_docker_usage")
def get_docker_usage_tool() -> str:
    """
    Get Docker disk usage information.
    
    Returns:
        JSON string with Docker storage breakdown
    """
    tools = TerminalTools(dry_run=True)
    result = tools.get_docker_usage()
    return json.dumps(result, indent=2)


@tool("get_system_overview")
def get_system_overview_tool() -> str:
    """
    Get overall system storage overview.
    
    Returns:
        JSON string with system storage information
    """
    tools = TerminalTools(dry_run=True)
    result = tools.get_system_overview()
    return json.dumps(result, indent=2)


@tool("find_developer_artifacts")
def find_developer_artifacts(workspace_path: str) -> str:
    """
    Find developer artifacts like node_modules, .venv, __pycache__ directories.
    
    Args:
        workspace_path: The workspace directory to search
    
    Returns:
        JSON string with list of developer artifact directories
    """
    tools = TerminalTools(dry_run=True)
    
    artifacts = {
        "node_modules": [],
        "venv": [],
        "pycache": [],
        "build_artifacts": []
    }
    
    # Find node_modules
    for f in tools.find_files(workspace_path, pattern="node_modules", file_type="d"):
        artifacts["node_modules"].append(f)
    
    # Find .venv and venv
    for pattern in [".venv", "venv"]:
        for f in tools.find_files(workspace_path, pattern=pattern, file_type="d"):
            artifacts["venv"].append(f)
    
    # Find __pycache__
    for f in tools.find_files(workspace_path, pattern="__pycache__", file_type="d"):
        artifacts["pycache"].append(f)
    
    # Find build directories
    for pattern in ["build", "dist", "target"]:
        for f in tools.find_files(workspace_path, pattern=pattern, file_type="d"):
            artifacts["build_artifacts"].append(f)
    
    return json.dumps(artifacts, indent=2)
