"""
StoragePilot Agents Package
============================
"""

from .crew_agents import (
    create_scanner_agent,
    create_analyzer_agent,
    create_organizer_agent,
    create_cleaner_agent,
    create_reporter_agent,
    create_executor_agent,
    create_all_agents,
)

from .tasks import (
    create_scan_task,
    create_analyze_task,
    create_organize_task,
    create_cleanup_task,
    create_report_task,
    create_all_tasks,
)

__all__ = [
    # Agents
    "create_scanner_agent",
    "create_analyzer_agent",
    "create_organizer_agent",
    "create_cleaner_agent",
    "create_reporter_agent",
    "create_executor_agent",
    "create_all_agents",
    # Tasks
    "create_scan_task",
    "create_analyze_task",
    "create_organize_task",
    "create_cleanup_task",
    "create_report_task",
    "create_all_tasks",
]
