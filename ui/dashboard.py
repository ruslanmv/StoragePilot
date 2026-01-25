"""
StoragePilot Dashboard
=======================
Streamlit-based UI for monitoring and controlling StoragePilot operations.
"""

import streamlit as st
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.terminal import TerminalTools
from tools.classifier import FileClassifier


# Page configuration
st.set_page_config(
    page_title="StoragePilot Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #00d4ff, #090979);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
    }
    .metric-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 100%);
        border-radius: 10px;
        padding: 1.5rem;
        margin: 0.5rem 0;
    }
    .action-card {
        border: 1px solid #444;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .safe-action {
        border-left: 4px solid #00ff00;
    }
    .review-action {
        border-left: 4px solid #ffff00;
    }
    .danger-action {
        border-left: 4px solid #ff0000;
    }
    .stProgress > div > div > div > div {
        background-color: #00d4ff;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables."""
    if 'scan_results' not in st.session_state:
        st.session_state.scan_results = None
    if 'classification_results' not in st.session_state:
        st.session_state.classification_results = None
    if 'action_queue' not in st.session_state:
        st.session_state.action_queue = []
    if 'action_log' not in st.session_state:
        st.session_state.action_log = []
    if 'dry_run' not in st.session_state:
        st.session_state.dry_run = True
    if 'scan_paths' not in st.session_state:
        st.session_state.scan_paths = ["~/Downloads", "~/Desktop", "~/Documents"]


def render_header():
    """Render the dashboard header."""
    st.markdown('<h1 class="main-header">🚀 StoragePilot Dashboard</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #888;">AI-Powered Storage Lifecycle Manager</p>', unsafe_allow_html=True)
    st.markdown("---")


def render_sidebar():
    """Render the sidebar with controls."""
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Mode selection
        st.subheader("Mode")
        mode = st.radio(
            "Execution Mode",
            ["🔍 Dry Run (Preview)", "⚡ Execute (Live)"],
            index=0 if st.session_state.dry_run else 1,
            help="Dry Run shows what would happen without making changes"
        )
        st.session_state.dry_run = "Dry Run" in mode
        
        if not st.session_state.dry_run:
            st.warning("⚠️ Execute mode is active. Actions will modify files!")
        
        st.markdown("---")
        
        # Scan paths
        st.subheader("📁 Scan Paths")
        paths_text = st.text_area(
            "Directories to scan (one per line)",
            value="\n".join(st.session_state.scan_paths),
            height=150
        )
        st.session_state.scan_paths = [p.strip() for p in paths_text.split("\n") if p.strip()]
        
        st.markdown("---")
        
        # Quick actions
        st.subheader("🚀 Quick Actions")
        
        if st.button("🔍 Scan Storage", use_container_width=True):
            run_storage_scan()
        
        if st.button("🏷️ Classify Files", use_container_width=True):
            run_file_classification()
        
        if st.button("🧹 Clean Docker", use_container_width=True):
            clean_docker()
        
        st.markdown("---")
        
        # Status
        st.subheader("📊 Status")
        if st.session_state.scan_results:
            st.success("✓ Storage scanned")
        else:
            st.info("○ Not scanned yet")
        
        if st.session_state.classification_results:
            st.success("✓ Files classified")
        else:
            st.info("○ Not classified yet")
        
        st.markdown("---")
        st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")


def run_storage_scan():
    """Run storage scan and update session state."""
    with st.spinner("🔍 Scanning storage..."):
        tools = TerminalTools(dry_run=True)
        
        results = {
            "system": tools.get_system_overview(),
            "directories": {},
            "docker": tools.get_docker_usage(),
            "developer_artifacts": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # Scan each directory
        progress_bar = st.progress(0)
        for i, path in enumerate(st.session_state.scan_paths):
            results["directories"][path] = tools.get_disk_usage(path)
            progress_bar.progress((i + 1) / len(st.session_state.scan_paths))
        
        # Find developer artifacts
        for path in st.session_state.scan_paths:
            if "workspace" in path.lower() or "projects" in path.lower():
                artifacts = tools.find_files(path, pattern="node_modules", file_type="d")
                results["developer_artifacts"]["node_modules"] = artifacts
        
        st.session_state.scan_results = results
        st.success("✓ Storage scan complete!")
        st.rerun()


def run_file_classification():
    """Run file classification on Downloads folder."""
    with st.spinner("🏷️ Classifying files..."):
        downloads_path = os.path.expanduser("~/Downloads")
        
        if os.path.exists(downloads_path):
            classifier = FileClassifier()
            classifications = classifier.classify_directory(downloads_path)
            plan = classifier.generate_organization_plan(classifications)
            
            st.session_state.classification_results = {
                "classifications": [c.__dict__ for c in classifications],
                "plan": plan,
                "timestamp": datetime.now().isoformat()
            }
            
            st.success(f"✓ Classified {len(classifications)} files!")
            st.rerun()
        else:
            st.error("Downloads folder not found")


def clean_docker():
    """Clean Docker resources."""
    with st.spinner("🧹 Cleaning Docker..."):
        tools = TerminalTools(dry_run=st.session_state.dry_run)
        results = tools.clean_docker()
        
        st.session_state.action_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "docker_clean",
            "dry_run": st.session_state.dry_run,
            "results": results
        })
        
        if st.session_state.dry_run:
            st.info("🔍 Dry run - no changes made")
        else:
            st.success("✓ Docker cleaned!")


def render_overview_tab():
    """Render the system overview tab."""
    if not st.session_state.scan_results:
        st.info("👆 Click 'Scan Storage' in the sidebar to get started")
        return
    
    results = st.session_state.scan_results
    
    # Disk usage metrics
    col1, col2, col3, col4 = st.columns(4)
    
    if results["system"].get("disk"):
        disk = results["system"]["disk"]
        with col1:
            st.metric("Total Space", disk.get("total", "N/A"))
        with col2:
            st.metric("Used", disk.get("used", "N/A"))
        with col3:
            st.metric("Available", disk.get("available", "N/A"))
        with col4:
            percent = disk.get("percent_used", "0%").replace("%", "")
            st.metric("Usage", f"{percent}%")
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Top Space Consumers")
        if results["system"].get("top_directories"):
            # Parse sizes to numeric for chart
            data = []
            for item in results["system"]["top_directories"][:10]:
                size_str = item["size"]
                path = item["path"]
                
                # Convert size to GB for comparison
                multiplier = 1
                if "G" in size_str:
                    multiplier = 1
                elif "M" in size_str:
                    multiplier = 0.001
                elif "K" in size_str:
                    multiplier = 0.000001
                
                try:
                    size_num = float(size_str.replace("G", "").replace("M", "").replace("K", "").replace("B", "").strip()) * multiplier
                except:
                    size_num = 0
                
                data.append({
                    "Path": os.path.basename(path) or path,
                    "Size (GB)": size_num,
                    "Full Path": path
                })
            
            df = pd.DataFrame(data)
            fig = px.bar(
                df, 
                x="Size (GB)", 
                y="Path",
                orientation='h',
                color="Size (GB)",
                color_continuous_scale="Blues"
            )
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("🐳 Docker Storage")
        if results.get("docker") and not results["docker"].get("error"):
            docker = results["docker"]
            
            # Create Docker usage chart
            docker_data = []
            for key in ["images", "containers", "volumes"]:
                if isinstance(docker.get(key), dict):
                    docker_data.append({
                        "Type": key.capitalize(),
                        "Size": docker[key].get("Size", "0B"),
                        "Reclaimable": docker[key].get("Reclaimable", "0B")
                    })
            
            if docker_data:
                st.dataframe(pd.DataFrame(docker_data), use_container_width=True)
            
            if st.button("🧹 Clean Docker Resources"):
                clean_docker()
        else:
            st.info("Docker not available or not running")
    
    st.markdown("---")
    
    # Directory breakdown
    st.subheader("📁 Directory Analysis")
    
    for path, usage in results["directories"].items():
        with st.expander(f"📁 {path} ({usage.get('total_size', 'N/A')})"):
            if usage.get("error"):
                st.error(usage["error"])
            elif usage.get("breakdown"):
                df = pd.DataFrame(usage["breakdown"])
                st.dataframe(df, use_container_width=True)


def render_organize_tab():
    """Render the file organization tab."""
    if not st.session_state.classification_results:
        st.info("👆 Click 'Classify Files' in the sidebar to analyze your downloads")
        return
    
    results = st.session_state.classification_results
    plan = results["plan"]
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📦 Total Files", len(results["classifications"]))
    with col2:
        st.metric("📁 To Move", len(plan["move"]))
    with col3:
        st.metric("🗑️ To Delete", len(plan["delete"]))
    with col4:
        st.metric("🔍 To Review", len(plan["review"]))
    
    st.markdown("---")
    
    # Action tabs
    action_tab1, action_tab2, action_tab3 = st.tabs(["📁 Move", "🗑️ Delete", "🔍 Review"])
    
    with action_tab1:
        st.subheader("Files to Move")
        if plan["move"]:
            for item in plan["move"]:
                with st.container():
                    col1, col2, col3 = st.columns([3, 3, 1])
                    with col1:
                        st.text(f"📄 {os.path.basename(item['source'])}")
                        st.caption(f"Category: {item['category']}/{item['subcategory']}")
                    with col2:
                        st.text(f"→ {item['destination']}")
                    with col3:
                        if st.button("✓", key=f"move_{item['source']}"):
                            execute_move(item['source'], item['destination'])
                    st.markdown("---")
            
            if st.button("✅ Move All", use_container_width=True):
                execute_all_moves(plan["move"])
        else:
            st.info("No files to move")
    
    with action_tab2:
        st.subheader("Files to Delete")
        if plan["delete"]:
            for item in plan["delete"]:
                with st.container():
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.text(f"🗑️ {os.path.basename(item['source'])}")
                        st.caption(f"Reason: {item['reason']}")
                    with col2:
                        if st.button("🗑️", key=f"del_{item['source']}"):
                            execute_delete(item['source'])
                    st.markdown("---")
            
            if st.button("🗑️ Delete All (Careful!)", use_container_width=True, type="secondary"):
                execute_all_deletes(plan["delete"])
        else:
            st.success("No files recommended for deletion")
    
    with action_tab3:
        st.subheader("Files Needing Review")
        if plan["review"]:
            for item in plan["review"]:
                with st.container():
                    st.text(f"❓ {os.path.basename(item['source'])}")
                    st.caption(f"Reason: {item['reason']}")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("✓ Keep", key=f"keep_{item['source']}"):
                            st.session_state.action_log.append({
                                "action": "keep",
                                "file": item['source']
                            })
                    with col2:
                        if st.button("📁 Move", key=f"mv_{item['source']}"):
                            # Show move dialog
                            pass
                    with col3:
                        if st.button("🗑️ Delete", key=f"rm_{item['source']}"):
                            execute_delete(item['source'])
                    st.markdown("---")
        else:
            st.success("No files need manual review")


def render_cleanup_tab():
    """Render the cleanup recommendations tab."""
    st.subheader("🧹 Cleanup Recommendations")
    
    if not st.session_state.scan_results:
        st.info("👆 Run a storage scan first")
        return
    
    results = st.session_state.scan_results
    
    # Developer artifacts
    st.markdown("### 🔧 Developer Artifacts")
    
    if results.get("developer_artifacts", {}).get("node_modules"):
        node_modules = results["developer_artifacts"]["node_modules"]
        st.warning(f"Found {len(node_modules)} node_modules directories")
        
        for item in node_modules[:10]:
            with st.expander(f"📁 {item['path']} ({item.get('size_human', 'N/A')})"):
                st.text(f"Last modified: {item.get('modified', 'N/A')}")
                if st.button(f"Delete node_modules", key=f"del_nm_{item['path']}"):
                    execute_delete(item['path'])
    else:
        st.success("No stale node_modules found")
    
    # Docker cleanup
    st.markdown("### 🐳 Docker Cleanup")
    
    if results.get("docker") and not results["docker"].get("error"):
        docker = results["docker"]
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🧹 Prune Dangling Images", use_container_width=True):
                tools = TerminalTools(dry_run=st.session_state.dry_run)
                result = tools.run_command("docker image prune -f")
                st.code(result.stdout or result.stderr)
        
        with col2:
            if st.button("🧹 Prune All Unused", use_container_width=True, type="secondary"):
                if st.session_state.dry_run:
                    st.info("Dry run - would clean all unused Docker resources")
                else:
                    tools = TerminalTools(dry_run=False)
                    result = tools.run_command("docker system prune -af")
                    st.code(result.stdout or result.stderr)
    
    # Cache cleanup
    st.markdown("### 🗄️ Cache Cleanup")
    
    cache_paths = [
        ("~/.npm/_cacache", "NPM Cache"),
        ("~/.cache/pip", "Pip Cache"),
        ("~/Library/Caches", "macOS Caches"),
    ]
    
    for path, name in cache_paths:
        expanded_path = os.path.expanduser(path)
        if os.path.exists(expanded_path):
            tools = TerminalTools(dry_run=True)
            usage = tools.get_disk_usage(path)
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.text(f"🗄️ {name}: {usage.get('total_size', 'N/A')}")
            with col2:
                if st.button("Clear", key=f"clear_{path}"):
                    if st.session_state.dry_run:
                        st.info(f"Would clear {path}")
                    else:
                        tools = TerminalTools(dry_run=False)
                        tools.run_command(f"rm -rf {path}/*")
                        st.success(f"Cleared {name}")


def render_log_tab():
    """Render the action log tab."""
    st.subheader("📜 Action Log")
    
    if not st.session_state.action_log:
        st.info("No actions recorded yet")
        return
    
    # Reverse to show newest first
    for entry in reversed(st.session_state.action_log[-50:]):
        with st.container():
            col1, col2 = st.columns([1, 4])
            with col1:
                st.caption(entry.get("timestamp", "N/A")[:19])
            with col2:
                action = entry.get("action", "unknown")
                dry_run = "🔍 " if entry.get("dry_run") else "⚡ "
                st.text(f"{dry_run}{action}")
                if entry.get("file"):
                    st.caption(entry["file"])
            st.markdown("---")
    
    if st.button("Clear Log"):
        st.session_state.action_log = []
        st.rerun()


def execute_move(source: str, destination: str):
    """Execute a file move operation."""
    tools = TerminalTools(dry_run=st.session_state.dry_run)
    result = tools.move_file(source, destination)
    
    st.session_state.action_log.append({
        "timestamp": datetime.now().isoformat(),
        "action": "move",
        "file": source,
        "destination": destination,
        "dry_run": st.session_state.dry_run,
        "success": result.success
    })
    
    if st.session_state.dry_run:
        st.info(f"🔍 Would move: {source} → {destination}")
    else:
        st.success(f"✓ Moved: {os.path.basename(source)}")


def execute_delete(path: str):
    """Execute a file delete operation."""
    tools = TerminalTools(dry_run=st.session_state.dry_run)
    result = tools.delete_file(path, backup=True)
    
    st.session_state.action_log.append({
        "timestamp": datetime.now().isoformat(),
        "action": "delete",
        "file": path,
        "dry_run": st.session_state.dry_run,
        "success": result.success
    })
    
    if st.session_state.dry_run:
        st.info(f"🔍 Would delete: {path}")
    else:
        st.success(f"✓ Deleted: {os.path.basename(path)}")


def execute_all_moves(items: List[Dict]):
    """Execute all move operations."""
    for item in items:
        execute_move(item['source'], item['destination'])


def execute_all_deletes(items: List[Dict]):
    """Execute all delete operations."""
    if not st.session_state.dry_run:
        st.warning("⚠️ This will permanently delete files!")
    
    for item in items:
        execute_delete(item['source'])


def main():
    """Main dashboard function."""
    init_session_state()
    
    render_header()
    render_sidebar()
    
    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Overview",
        "📁 Organize",
        "🧹 Cleanup",
        "📜 Log"
    ])
    
    with tab1:
        render_overview_tab()
    
    with tab2:
        render_organize_tab()
    
    with tab3:
        render_cleanup_tab()
    
    with tab4:
        render_log_tab()


if __name__ == "__main__":
    main()
