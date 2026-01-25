"""
StoragePilot Agents
====================
CrewAI agent definitions for storage management tasks.
"""

from crewai import Agent
from typing import List, Optional
from tools import (
    scan_directory,
    find_large_files,
    find_old_files,
    get_docker_usage_tool,
    get_system_overview_tool,
    find_developer_artifacts,
    classify_files,
    classify_single_file,
    detect_duplicates,
)


def create_scanner_agent(llm=None) -> Agent:
    """
    Scanner Agent: Storage Detective
    
    Discovers all files, folders, and their sizes across the system.
    Identifies space-consuming directories and hidden storage hogs.
    """
    return Agent(
        role="Storage Detective",
        goal="""Thoroughly scan the file system to discover all files, folders, 
        and their sizes. Identify the biggest space consumers, hidden caches, 
        and developer artifacts that occupy excessive storage.""",
        backstory="""You are an expert system administrator with deep knowledge 
        of file systems, developer workflows, and common storage patterns. You 
        know where developers typically accumulate storage waste: node_modules, 
        virtual environments, Docker images, AI model caches, and download folders.
        You excel at using terminal commands like 'du', 'find', and 'docker system df'
        to uncover storage usage patterns.""",
        tools=[
            scan_directory,
            find_large_files,
            find_old_files,
            get_docker_usage_tool,
            get_system_overview_tool,
            find_developer_artifacts,
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=15,
    )


def create_analyzer_agent(llm=None) -> Agent:
    """
    Analyzer Agent: AI Classifier
    
    Classifies files semantically, identifies duplicates, and detects patterns.
    """
    return Agent(
        role="AI File Classifier",
        goal="""Analyze and classify files based on their content, names, and 
        metadata. Identify duplicates, version conflicts, and misplaced files. 
        Understand the semantic meaning of files to categorize them correctly 
        (e.g., distinguishing an invoice PDF from a random document).""",
        backstory="""You are an AI specialist in document analysis and file 
        classification. You understand developer contexts - you know that a 
        'requirements.txt' is critical for recreating virtual environments, 
        while node_modules can be regenerated. You can identify patterns in 
        filenames that indicate versions, duplicates, or temporary files.
        You use semantic analysis to understand file purposes beyond just 
        extensions.""",
        tools=[
            classify_files,
            classify_single_file,
            detect_duplicates,
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )


def create_organizer_agent(llm=None) -> Agent:
    """
    Organizer Agent: File Architect
    
    Designs optimal folder structures and plans file movements.
    """
    return Agent(
        role="File Organization Architect",
        goal="""Design and implement an optimal folder structure for the user's 
        files. Create organization plans that group related files logically, 
        maintain easy navigation, and follow best practices for file management.
        Plan file movements that preserve context while reducing clutter.""",
        backstory="""You are a productivity expert specializing in digital 
        organization systems. You understand that good file organization should 
        be intuitive, scalable, and maintainable. You create folder hierarchies 
        that make sense for developer workflows - separating active projects from 
        archives, organizing downloads by purpose rather than just date, and 
        creating clear paths for different file types.""",
        tools=[
            classify_files,
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )


def create_cleaner_agent(llm=None) -> Agent:
    """
    Cleaner Agent: Storage Liberator
    
    Safely removes unnecessary files with proper justification.
    """
    return Agent(
        role="Storage Liberation Specialist",
        goal="""Identify and safely remove unnecessary files to free up disk 
        space. Focus on files that are: (1) Safe to delete (caches, temp files, 
        installers), (2) Redundant (duplicates), or (3) Regenerable (node_modules 
        with package.json). Always prioritize data safety over space savings.""",
        backstory="""You are a cautious storage optimization expert who 
        understands the fear of data loss. You never delete anything without 
        clear justification. You know which developer artifacts are safe to 
        remove (node_modules can be reinstalled with 'npm install') and which 
        are critical (configuration files, credentials). You always recommend 
        dry-run previews before actual deletions.""",
        tools=[
            find_developer_artifacts,
            get_docker_usage_tool,
            find_old_files,
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )


def create_reporter_agent(llm=None) -> Agent:
    """
    Reporter Agent: Insights Compiler
    
    Generates comprehensive reports and visualizations.
    """
    return Agent(
        role="Storage Insights Reporter",
        goal="""Compile comprehensive reports that summarize storage analysis, 
        proposed actions, and potential savings. Present information clearly 
        with actionable recommendations. Create summaries that help users 
        understand their storage situation at a glance.""",
        backstory="""You are a technical writer and data visualization expert 
        who excels at making complex information accessible. You create reports 
        that balance detail with clarity - showing the big picture while 
        providing drill-down details for those who want them. Your reports 
        always include specific recommendations with clear explanations of 
        benefits and risks.""",
        tools=[
            get_system_overview_tool,
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=5,
    )


def create_executor_agent(llm=None) -> Agent:
    """
    Executor Agent: Action Manager
    
    Executes approved actions with safety checks and logging.
    """
    return Agent(
        role="Safe Action Executor",
        goal="""Execute approved storage management actions safely. Implement 
        dry-run previews, maintain action logs for undo capability, and verify 
        successful completion of each action. Never execute destructive 
        operations without explicit confirmation.""",
        backstory="""You are a system operations expert with extensive 
        experience in safe automation. You follow the principle of 'measure 
        twice, cut once' - always previewing actions before execution. You 
        maintain detailed logs of every operation so actions can be undone 
        if needed. You understand that data integrity is more important than 
        speed.""",
        tools=[
            scan_directory,
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=15,
    )


def create_all_agents(llm=None) -> dict:
    """Create all agents and return them in a dictionary."""
    return {
        "scanner": create_scanner_agent(llm),
        "analyzer": create_analyzer_agent(llm),
        "organizer": create_organizer_agent(llm),
        "cleaner": create_cleaner_agent(llm),
        "reporter": create_reporter_agent(llm),
        "executor": create_executor_agent(llm),
    }
