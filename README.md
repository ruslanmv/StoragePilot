# 🚀 StoragePilot v1.0

## AI-Powered Storage Lifecycle Manager for Developers

StoragePilot is a **multi-agent AI system** built with CrewAI that autonomously analyzes, organizes, and optimizes storage on developer workstations—understanding not just file types, but **developer context**.

---

## 📋 Executive Summary

### The Core Problem: "Digital Hoarding & Context-Blindness"

Developers suffer from **critical storage exhaustion** and **file disorganization**. The accumulation of:
- High-velocity "transient files" (Downloads/Screenshots)
- Heavy "technical debt" (abandoned `.venv`, `node_modules`, Docker images)

Creates a chaotic environment where the fear of data loss prevents manual cleanup.

---

## 🔍 Problem Taxonomy

| Category | Symptom | Root Cause |
|----------|---------|------------|
| **Technical Bloat** | 50GB+ in `node_modules`, `.venv`, `.cache` | Projects abandoned but dependencies retained |
| **AI Model Drift** | Hidden 10GB+ Hugging Face/Torch caches | Model experimentation without cleanup |
| **Container Zombies** | Dangling Docker images, stopped containers | Experiment-driven development lifecycle |
| **Download Entropy** | Flat folder with 1000+ mixed files | No automated intake/triage system |
| **Version Proliferation** | `file_v1`, `file_v2_final`, `file_REAL` | Manual versioning without deduplication |
| **Storage Paralysis** | Files kept "just in case" indefinitely | No safe migration path to cold storage |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STORAGEPILOT v1.0                                 │
│              "AI-Powered Storage Lifecycle Manager"                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        CREW ORCHESTRATOR                             │   │
│  │                   (CrewAI Sequential Process)                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│         ┌──────────────────────────┼──────────────────────────┐            │
│         ▼                          ▼                          ▼            │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐       │
│  │   SCANNER   │           │  ANALYZER   │           │  ORGANIZER  │       │
│  │    Agent    │──────────▶│    Agent    │──────────▶│    Agent    │       │
│  └─────────────┘           └─────────────┘           └─────────────┘       │
│         │                          │                          │            │
│         └──────────────────────────┼──────────────────────────┘            │
│                                    ▼                                        │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐       │
│  │   CLEANER   │◀──────────│  REPORTER   │◀──────────│  EXECUTOR   │       │
│  │    Agent    │           │    Agent    │           │    Agent    │       │
│  └─────────────┘           └─────────────┘           └─────────────┘       │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         STREAMLIT UI                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🤖 Agent Roles

### 1. Scanner Agent
**Role:** Storage Detective  
**Goal:** Discover all files, folders, and their sizes across the system  
**Tools:** `du`, `find`, `docker system df`, `tree`

### 2. Analyzer Agent
**Role:** AI Classifier  
**Goal:** Classify files semantically, identify duplicates, detect developer artifacts  
**Tools:** File content analysis, hash comparison, pattern matching

### 3. Organizer Agent
**Role:** File Architect  
**Goal:** Create optimal folder structure and move files appropriately  
**Tools:** `mkdir`, `mv`, symlink creation

### 4. Cleaner Agent
**Role:** Storage Liberator  
**Goal:** Safely remove unnecessary files with user approval  
**Tools:** `rm`, `docker prune`, cache clearing

### 5. Reporter Agent
**Role:** Insights Compiler  
**Goal:** Generate comprehensive reports and recommendations  
**Tools:** Report generation, visualization

### 6. Executor Agent
**Role:** Action Manager  
**Goal:** Execute approved actions with safety checks  
**Tools:** Terminal commands with dry-run support

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure target directories
cp config/config.example.yaml config/config.yaml
# Edit config.yaml with your paths

# 3. Run in DRY-RUN mode (safe preview)
python main.py --dry-run

# 4. Launch the UI
streamlit run ui/dashboard.py

# 5. Run with execution (after review)
python main.py --execute
```

---

## 📁 Project Structure

```
storagepilot/
├── main.py                 # Entry point
├── requirements.txt        # Dependencies
├── config/
│   ├── config.yaml         # User configuration
│   └── categories.yaml     # File classification rules
├── agents/
│   ├── __init__.py
│   ├── scanner.py          # Scanner Agent
│   ├── analyzer.py         # Analyzer Agent
│   ├── organizer.py        # Organizer Agent
│   ├── cleaner.py          # Cleaner Agent
│   ├── reporter.py         # Reporter Agent
│   └── executor.py         # Executor Agent
├── tools/
│   ├── __init__.py
│   ├── terminal.py         # Terminal command tools
│   ├── file_ops.py         # File operation tools
│   ├── docker_tools.py     # Docker cleanup tools
│   └── classifier.py       # AI classification tools
├── ui/
│   ├── dashboard.py        # Streamlit main dashboard
│   └── components.py       # UI components
└── logs/
    └── actions.log         # Action history
```

---

## ⚙️ Configuration

Edit `config/config.yaml`:

```yaml
# Target directories to analyze
scan_paths:
  - ~/Downloads
  - ~/Desktop
  - ~/Documents
  - ~/workspace

# Developer-specific paths
developer_paths:
  workspace: ~/workspace
  node_modules_pattern: "**/node_modules"
  venv_pattern: "**/.venv"
  cache_paths:
    - ~/.cache/huggingface
    - ~/.cache/torch
    - ~/.npm/_cacache

# Organization rules
organization:
  downloads_sorting:
    documents: ~/Documents/Sorted
    images: ~/Pictures/Sorted
    installers: ~/Trash/Installers
    code: ~/workspace/downloads

# Safety settings
safety:
  dry_run: true
  require_approval: true
  backup_before_delete: true
```

---

## 📊 Real-World Examples

### Example 1: Downloads Folder Analysis

**Before:**
```
~/Downloads/ (847 files, 34 GB)
├── invoice_2024_03.pdf
├── Screenshot_2024-01-15.png
├── node-v20.10.0.pkg
├── random_meme.jpg
├── tax_return_2023.pdf
└── ... 842 more files
```

**After StoragePilot:**
```
~/Documents/
├── Finance/
│   ├── Invoices/invoice_2024_03.pdf
│   └── Tax/tax_return_2023.pdf
~/Pictures/
├── Screenshots/Screenshot_2024-01-15.png
└── Memes/random_meme.jpg
~/Trash/
└── Installers/node-v20.10.0.pkg (marked for deletion)
```

### Example 2: Developer Artifact Cleanup

**Identified:**
```
📊 DEVELOPER ARTIFACTS REPORT
═══════════════════════════════════════════════════
Project: old-react-project (Last modified: 8 months ago)
└── node_modules/: 847 MB → SAFE TO DELETE ✓

Project: ml-experiment-2023 (Last modified: 14 months ago)
└── .venv/: 2.3 GB → SAFE TO DELETE ✓

Project: avatar-animator (Last modified: 2 days ago)
└── .venv/: 1.8 GB → KEEP (active project)

POTENTIAL SAVINGS: 3.1 GB
═══════════════════════════════════════════════════
```

---

## 🔒 Safety Features

1. **Dry-Run Mode**: Preview all actions without executing
2. **Approval Gates**: Require explicit user approval for deletions
3. **Stub Files**: Leave traces when moving files to external storage
4. **Backup Support**: Optional backup before destructive operations
5. **Undo Log**: Track all actions for potential rollback

---

## 📜 License

MIT License - Use freely for personal and commercial projects.
