<p align="center">
  <img src="./assets/logo.svg" alt="StoragePilot Logo" width="120" height="120">
</p>

<h1 align="center">StoragePilot</h1>

<p align="center">
  <strong>AI-Powered Storage Lifecycle Manager</strong><br>
  Multi-agent system for intelligent storage analysis and optimization
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#features">Features</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#architecture">Architecture</a>
</p>

---

## Overview

StoragePilot is an enterprise-grade storage management solution that uses AI agents to analyze, classify, and optimize file storage. Built with CrewAI, it understands developer context—distinguishing active projects from abandoned artifacts.

**Key Benefits:**
- Zero-config local LLM support via Ollama
- Safe dry-run mode by default
- Developer-aware artifact detection
- Automated file classification and organization

---

## Installation

### Prerequisites
- Python 3.10+
- 4GB RAM minimum

### One-Command Setup

```bash
make install
```

This installs:
- Python dependencies
- Ollama (local LLM runtime)
- Default model (`qwen2.5:0.5b`, ~400MB)

### Manual Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install Ollama
./scripts/setup_ollama.sh

# Or use cloud providers (set API keys)
export OPENAI_API_KEY=your-key
```

---

## Quick Start

```bash
# Run in safe preview mode
make run

# Scan only (no AI analysis)
make run-scan

# Execute with actions (after review)
make run-execute

# Launch web dashboard
make run-ui
```

---

## Features

### Storage Analysis
| Feature | Description |
|---------|-------------|
| **Directory Scanning** | Size breakdown, large file detection |
| **Developer Artifacts** | Detects `node_modules`, `.venv`, `__pycache__`, build dirs |
| **Docker Analysis** | Images, containers, volumes, build cache |
| **Duplicate Detection** | Content-hash and filename-pattern matching |

### File Classification
| Category | Actions |
|----------|---------|
| Documents | Organize by type (invoices, contracts, tax) |
| Images | Sort screenshots, photos, memes |
| Code/Data | Move to workspace directories |
| Installers | Mark for cleanup |
| Archives | Analyze contents |

### Safety
- **Dry-run by default** — Preview before execution
- **Approval gates** — Confirm destructive actions
- **Backup support** — Optional pre-delete backups
- **Undo logging** — Track all actions for rollback
- **Protected paths** — Never touches `.ssh`, `.gnupg`, `.aws`

---

## Configuration

Edit `config/config.yaml`:

```yaml
# LLM Provider
llm:
  provider: "ollama"           # ollama | openai | anthropic | matrixllm
  model: "qwen2.5:0.5b"
  base_url: "http://127.0.0.1:11434/v1"

# Scan Targets
scan_paths:
  primary:
    - "."                      # Current directory
    - "~/Downloads"
    - "~/Desktop"
  workspace:
    - "~/workspace"
    - "~/projects"

# Safety Settings
safety:
  dry_run: true
  require_approval: true
  backup_before_delete: true
```

### LLM Providers

| Provider | Setup | Use Case |
|----------|-------|----------|
| `ollama` | `make install` | Local inference, no API keys |
| `matrixllm` | `--pair-matrixllm` | Custom LLM gateway |
| `openai` | `OPENAI_API_KEY` | Cloud inference |
| `anthropic` | `ANTHROPIC_API_KEY` | Cloud inference |

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                      StoragePilot                          │
├────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Scanner  │→ │ Analyzer │→ │Organizer │→ │ Cleaner  │   │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│       ↓              ↓             ↓             ↓        │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                    Tool Layer                        │  │
│  │  terminal.py │ classifier.py │ matrixllm.py         │  │
│  └─────────────────────────────────────────────────────┘  │
│       ↓              ↓             ↓             ↓        │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              LLM Provider (Ollama/OpenAI)           │  │
│  └─────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### Agents

| Agent | Role | Capabilities |
|-------|------|--------------|
| **Scanner** | Storage Detective | Disk usage, large files, Docker stats |
| **Analyzer** | AI Classifier | File classification, duplicate detection |
| **Organizer** | File Architect | Folder structure, move planning |
| **Cleaner** | Storage Liberator | Safe cleanup recommendations |
| **Reporter** | Insights Compiler | Summary reports |
| **Executor** | Action Manager | Execute with safety checks |

---

## MCP Server

StoragePilot includes an MCP (Model Context Protocol) server for tool integration:

```bash
# Start MCP server (dry-run)
make mcp-server

# Start MCP server (execute mode)
make mcp-server-execute
```

Add to Claude Desktop config:
```json
{
  "mcpServers": {
    "storagepilot": {
      "command": "python",
      "args": ["/path/to/StoragePilot/mcp_server.py"]
    }
  }
}
```

---

## Project Structure

```
StoragePilot/
├── main.py              # CLI entry point
├── mcp_server.py        # MCP server for tool integration
├── Makefile             # Build and run commands
├── config/
│   └── config.yaml      # User configuration
├── agents/
│   ├── crew_agents.py   # Agent definitions
│   └── tasks.py         # Task definitions
├── tools/
│   ├── terminal.py      # File system operations
│   ├── classifier.py    # AI file classification
│   └── matrixllm.py     # LLM integration (Ollama/MatrixLLM)
├── scripts/
│   └── setup_ollama.sh  # Ollama installation script
└── ui/
    └── dashboard.py     # Streamlit web UI
```

---

## License

MIT License — Free for personal and commercial use.

---

<p align="center">
  <sub>Built with <a href="https://crewai.com">CrewAI</a> and <a href="https://ollama.com">Ollama</a></sub>
</p>
