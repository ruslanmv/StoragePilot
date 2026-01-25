"""
StoragePilot Tasks
===================
CrewAI task definitions for the storage management workflow.
"""

from crewai import Task
from typing import List, Optional


def create_scan_task(agent, scan_paths: List[str]) -> Task:
    """
    Task 1: System Scan
    
    Scan the file system to identify storage usage patterns.
    """
    paths_str = ", ".join(scan_paths)
    
    return Task(
        description=f"""Perform a comprehensive storage scan of the following directories: {paths_str}

Your objectives:
1. Get the overall system storage overview (disk usage, available space)
2. Scan each target directory to get size breakdowns
3. Find the top 10 space-consuming directories
4. Identify large files (>100MB) in Downloads and Desktop
5. Find developer artifacts (node_modules, .venv, __pycache__)
6. Check Docker usage if available
7. Look for hidden cache directories (~/.cache, ~/Library/Caches)

For each finding, note:
- Path and size
- Last modified date if relevant
- Whether it appears to be an active project or abandoned
- Potential for cleanup (safe to delete, needs review, must keep)

Output a structured summary of storage usage patterns.""",
        expected_output="""A comprehensive storage analysis report containing:
1. System Overview: Total disk space, used, available, percentage
2. Top Space Consumers: List of largest directories with sizes
3. Developer Artifacts: node_modules, .venv, and cache directories found
4. Large Files: Files over 100MB in user folders
5. Docker Usage: Container, image, and volume sizes (if applicable)
6. Recommendations: Initial observations about potential cleanup opportunities""",
        agent=agent,
    )


def create_analyze_task(agent, context_tasks: List[Task]) -> Task:
    """
    Task 2: File Analysis & Classification
    
    Analyze and classify files for organization.
    """
    return Task(
        description="""Based on the storage scan results, perform detailed analysis and classification:

1. Classify files in Downloads folder:
   - Documents (invoices, contracts, reports)
   - Images (screenshots, photos, memes)
   - Code files and data
   - Installers (DMG, PKG, EXE)
   - Archives (ZIP, TAR)

2. Detect duplicates:
   - Exact duplicates (same content)
   - Version duplicates (file_v1, file_v2, file_final)
   - Similar filenames

3. Identify file patterns:
   - Screenshot naming patterns
   - Photo naming patterns
   - Temporary file patterns

4. Evaluate developer artifacts:
   - Check if node_modules directories have corresponding package.json
   - Check if .venv directories have requirements.txt
   - Determine project activity (last modified dates)

5. Flag files that need human review:
   - Unknown file types
   - Potentially important documents
   - Configuration files

Output a classification report with action recommendations for each file category.""",
        expected_output="""A detailed classification report containing:
1. Downloads Analysis: Breakdown by category with counts and sizes
2. Duplicate Report: Groups of duplicate files with recommendations
3. Developer Artifacts Analysis: Safe vs unsafe to delete
4. Action Plan: Files to move, delete, or review
5. Risk Assessment: Potential data loss risks for proposed actions""",
        agent=agent,
        context=context_tasks,
    )


def create_organize_task(agent, context_tasks: List[Task]) -> Task:
    """
    Task 3: Organization Planning
    
    Design the optimal folder structure and file organization plan.
    """
    return Task(
        description="""Based on the analysis, create a comprehensive organization plan:

1. Design folder structure:
   - ~/Documents/
     - Finance/ (Invoices/, Tax/, Receipts/)
     - Work/ (Notes/, Presentations/, Reports/)
     - Legal/ (Contracts/, Agreements/)
   - ~/Pictures/
     - Screenshots/
     - Photos/{year}/{month}/
     - Memes/
   - ~/workspace/
     - active/ (current projects)
     - archive/ (old projects)
     - code_downloads/

2. Create file movement plan:
   - List each file with source and destination
   - Group by action type (move, delete, review)
   - Prioritize by confidence level

3. Handle special cases:
   - Version conflicts (keep newest, archive old)
   - Duplicates (keep one, delete others)
   - Large files (move to external storage)

4. Create stub file plan:
   - For files moved to external storage
   - Include restore instructions

Output a detailed, actionable organization plan.""",
        expected_output="""An organization plan containing:
1. Folder Structure: Complete directory hierarchy to create
2. Move Operations: List of files with source -> destination
3. Delete Operations: List of files safe to delete with reasons
4. Review Queue: Files requiring human decision
5. Stub Files: Files to move externally with stub creation plan
6. Execution Order: Recommended sequence of operations""",
        agent=agent,
        context=context_tasks,
    )


def create_cleanup_task(agent, context_tasks: List[Task]) -> Task:
    """
    Task 4: Cleanup Planning
    
    Create safe cleanup recommendations for freeing space.
    """
    return Task(
        description="""Based on the analysis, create a cleanup plan to free disk space:

1. Developer Artifact Cleanup:
   - List inactive project dependencies (node_modules, .venv older than 30 days)
   - Calculate total space that can be recovered
   - Note regeneration commands (npm install, pip install -r requirements.txt)

2. Cache Cleanup:
   - Hugging Face model cache (keep recent, clear old)
   - NPM cache (safe to clear)
   - Pip cache (safe to clear)
   - System caches

3. Docker Cleanup:
   - Dangling images
   - Stopped containers
   - Unused volumes
   - Build cache

4. Trash/Temp Cleanup:
   - Empty trash
   - Clear temp directories
   - Remove .DS_Store files

5. Installer Cleanup:
   - DMG, PKG, EXE files that have been installed

For each cleanup action:
- Estimate space savings
- Assess risk level (low/medium/high)
- Provide undo/recovery instructions

IMPORTANT: Always err on the side of caution. If unsure, recommend review rather than deletion.""",
        expected_output="""A cleanup plan containing:
1. Safe Deletions: Files/folders that can be safely removed
   - Path, size, reason, risk level
2. Space Recovery Summary: Total potential space savings by category
3. Docker Cleanup Commands: Specific commands to run
4. Cache Cleanup Commands: Specific commands to run
5. Risk Warnings: Any actions that need extra caution
6. Recovery Instructions: How to undo or recover if needed""",
        agent=agent,
        context=context_tasks,
    )


def create_report_task(agent, context_tasks: List[Task]) -> Task:
    """
    Task 5: Final Report Generation
    
    Compile all findings into a comprehensive report.
    """
    return Task(
        description="""Compile all the analysis, organization plans, and cleanup recommendations 
into a comprehensive, user-friendly report:

1. Executive Summary:
   - Current storage situation (used/available)
   - Total potential space savings
   - Number of files to organize/delete/review
   - Risk assessment

2. Storage Breakdown:
   - Top space consumers
   - Developer artifacts
   - User files analysis

3. Action Plan Summary:
   - Phase 1: Safe cleanup (low risk)
   - Phase 2: Organization (move files)
   - Phase 3: Review items (need human decision)

4. Detailed Recommendations:
   - Specific commands to run
   - Files to move with destinations
   - Files to delete with reasons

5. Before/After Projection:
   - Current state
   - Projected state after cleanup

6. Maintenance Tips:
   - How to prevent future accumulation
   - Recommended periodic cleanup tasks

Format the report for both console output and UI display.""",
        expected_output="""A comprehensive report containing:
1. Executive Summary with key metrics
2. Detailed Storage Analysis
3. Categorized Action Plan (organize, cleanup, review)
4. Space Recovery Projection
5. Step-by-step Execution Guide
6. Maintenance Recommendations

The report should be clear, actionable, and help the user understand 
exactly what actions will be taken and why.""",
        agent=agent,
        context=context_tasks,
    )


def create_all_tasks(agents: dict, scan_paths: List[str]) -> List[Task]:
    """Create all tasks in sequence."""
    
    # Task 1: Scan
    scan_task = create_scan_task(agents["scanner"], scan_paths)
    
    # Task 2: Analyze (depends on scan)
    analyze_task = create_analyze_task(agents["analyzer"], [scan_task])
    
    # Task 3: Organize (depends on analysis)
    organize_task = create_organize_task(agents["organizer"], [scan_task, analyze_task])
    
    # Task 4: Cleanup (depends on analysis)
    cleanup_task = create_cleanup_task(agents["cleaner"], [scan_task, analyze_task])
    
    # Task 5: Report (depends on all)
    report_task = create_report_task(
        agents["reporter"], 
        [scan_task, analyze_task, organize_task, cleanup_task]
    )
    
    return [scan_task, analyze_task, organize_task, cleanup_task, report_task]
