#!/usr/bin/env python3
"""
StoragePilot Core Module
========================

Provides the main StoragePilot class for programmatic access.
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any


def _setup_path():
    """Add package root to path for imports."""
    root = Path(__file__).parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_setup_path()


class StoragePilot:
    """
    StoragePilot - AI-Powered Storage Lifecycle Manager

    Example:
        pilot = StoragePilot()
        results = pilot.scan()
        analysis = pilot.analyze()
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        dry_run: bool = True,
        verbose: bool = True,
    ):
        """
        Initialize StoragePilot.

        Args:
            config_path: Path to configuration YAML file
            dry_run: If True, no actual changes are made
            verbose: If True, print detailed output
        """
        self.dry_run = dry_run
        self.verbose = verbose
        self._config = None
        self._tools = None

        # Load configuration
        if config_path:
            self._config_path = config_path
        else:
            self._config_path = str(
                Path(__file__).parent.parent / "config" / "config.yaml"
            )

    @property
    def config(self) -> dict:
        """Load and return configuration."""
        if self._config is None:
            from main import load_config
            self._config = load_config(self._config_path)
        return self._config

    @property
    def tools(self):
        """Get terminal tools instance."""
        if self._tools is None:
            from tools import TerminalTools
            self._tools = TerminalTools(dry_run=self.dry_run)
        return self._tools

    def scan(self, paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Scan storage and return results.

        Args:
            paths: List of paths to scan. If None, uses config paths.

        Returns:
            Dictionary with scan results including system overview,
            directory breakdown, and Docker usage.
        """
        from main import get_scan_paths

        if paths is None:
            paths = get_scan_paths(self.config)

        results = {
            "system": self.tools.get_system_overview(),
            "directories": {},
            "docker": self.tools.get_docker_usage(),
        }

        for path in paths:
            if os.path.exists(path):
                results["directories"][path] = self.tools.get_disk_usage(path)

        return results

    def find_large_files(
        self,
        path: str = ".",
        min_size_mb: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find large files in a directory.

        Args:
            path: Directory to search
            min_size_mb: Minimum file size in MB

        Returns:
            List of large files with path and size info
        """
        return self.tools.find_large_files(path, min_size_mb)

    def find_old_files(
        self,
        path: str = ".",
        days: int = 365
    ) -> List[Dict[str, Any]]:
        """
        Find old files that haven't been modified.

        Args:
            path: Directory to search
            days: Number of days since last modification

        Returns:
            List of old files with metadata
        """
        return self.tools.find_old_files(path, days)

    def find_developer_artifacts(
        self,
        path: str = "."
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Find developer artifacts like node_modules, .venv, etc.

        Args:
            path: Directory to search

        Returns:
            Dictionary categorized by artifact type
        """
        return self.tools.find_developer_artifacts(path)

    def analyze(self, paths: Optional[List[str]] = None) -> Any:
        """
        Run full AI-powered analysis using CrewAI agents.

        Args:
            paths: List of paths to analyze

        Returns:
            Crew execution result
        """
        from main import run_crew

        return run_crew(
            self.config,
            dry_run=self.dry_run,
            verbose=self.verbose
        )

    def get_system_overview(self) -> Dict[str, Any]:
        """Get system storage overview."""
        return self.tools.get_system_overview()

    def get_docker_usage(self) -> Dict[str, Any]:
        """Get Docker storage usage."""
        return self.tools.get_docker_usage()

    def classify_file(self, file_path: str) -> Dict[str, str]:
        """
        Classify a single file using AI.

        Args:
            file_path: Path to the file

        Returns:
            Classification result with category and suggested action
        """
        from tools.classifier import classify_files

        result = classify_files([file_path])
        if result and file_path in result:
            return result[file_path]
        return {"category": "unknown", "action": "none"}

    def classify_files(self, file_paths: List[str]) -> Dict[str, Dict[str, str]]:
        """
        Classify multiple files using AI.

        Args:
            file_paths: List of file paths

        Returns:
            Dictionary mapping file paths to classification results
        """
        from tools.classifier import classify_files

        return classify_files(file_paths)

    def detect_duplicates(
        self,
        path: str = ".",
        method: str = "hash"
    ) -> List[Dict[str, Any]]:
        """
        Detect duplicate files.

        Args:
            path: Directory to search
            method: Detection method ("hash" or "name")

        Returns:
            List of duplicate groups
        """
        return self.tools.detect_duplicates(path, method)
