"""
StoragePilot Tools Package
===========================
"""

from .terminal import (
    TerminalTools,
    CommandResult,
    ActionLog,
    scan_directory,
    find_large_files,
    find_old_files,
    get_docker_usage_tool,
    get_system_overview_tool,
    find_developer_artifacts
)

from .classifier import (
    FileClassifier,
    FileClassification,
    classify_files,
    classify_single_file,
    detect_duplicates
)

__all__ = [
    # Terminal Tools
    "TerminalTools",
    "CommandResult",
    "ActionLog",
    "scan_directory",
    "find_large_files",
    "find_old_files",
    "get_docker_usage_tool",
    "get_system_overview_tool",
    "find_developer_artifacts",
    # Classifier Tools
    "FileClassifier",
    "FileClassification",
    "classify_files",
    "classify_single_file",
    "detect_duplicates",
    # Path Resolver Tools
    "resolve_paths_tool",
    "resolve_scan_paths",
    "resolve_special_path",
    "is_wsl",
]


from .matrixllm import (
    pair_with_matrixllm,
    matrixllm_healthcheck,
    load_matrixllm_token,
    save_matrixllm_token,
    matrixllm_token_path,
    # Ollama integration
    ollama_healthcheck,
    ollama_list_models,
)

from .path_resolver import (
    resolve_paths_tool,
    resolve_scan_paths,
    resolve_special_path,
    is_wsl,
)
