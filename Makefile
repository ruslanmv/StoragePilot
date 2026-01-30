# StoragePilot Makefile
# =====================
# Quick setup and installation commands
#
# Context Forge / MCP Gateway compatibility notes:
# - Gateway expects an HTTP/SSE MCP server reachable by URL.
# - Canonical endpoints (recommended):
#     GET  /sse
#     POST /messages
# - This Makefile uses the canonical /sse URL by default.
#
# Inspector notes:
# - `@modelcontextprotocol/inspector` spawns the MCP server via stdio.
# - It must receive an absolute path to python + script for reliability.
# - This Makefile fixes inspector command paths accordingly.
#
# MCP Server v1.1.0 Compatibility:
# - Self-contained server (no external tool imports required)
# - Supports --debug flag for verbose logging
# - Proper signal handling for graceful shutdown
# - Separate SSE transports for canonical and namespaced endpoints

.PHONY: help install install-deps install-ollama install-model setup-wizard \
        run run-execute run-scan api api-prod \
        test test-api test-all test-mcp clean \
        mcp-server mcp-server-execute mcp-server-http mcp-server-http-execute \
        mcp-server-http-debug mcp-inspector mcp-dev mcp-list \
        mcp-register mcp-publish mcp-stop mcp-health mcp-info \
        mcp-inspector-http

# =============================================================================
# Configuration
# =============================================================================

# Virtual environment paths
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# Repo root (absolute path)
ROOT := $(CURDIR)

# MCP Server script
MCP_SERVER := $(ROOT)/mcp_server.py

# Default model (smallest for quick start)
MODEL ?= qwen2.5:0.5b

# ----------------------------
# HTTP/SSE settings (StoragePilot MCP Server)
# ----------------------------
MCP_HTTP_PORT ?= 9000
MCP_HTTP_HOST ?= 127.0.0.1

# Client-side connect host (never use 0.0.0.0 as a connect URL)
# - If you run StoragePilot with --host 0.0.0.0, keep MCP_HTTP_HOST=0.0.0.0
#   but set MCP_CONNECT_HOST=127.0.0.1 (local) or LAN IP / host.docker.internal (docker).
MCP_CONNECT_HOST ?= 127.0.0.1

# Canonical MCP endpoints expected by Context Forge / MCP Gateway
MCP_SSE_PATH ?= /sse
MCP_MESSAGES_PATH ?= /messages
MCP_HEALTH_PATH ?= /health
MCP_INFO_PATH ?= /info

# Server URLs (use connect host, not bind host)
MCP_SERVER_URL ?= http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)$(MCP_SSE_PATH)
MCP_HEALTH_URL ?= http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)$(MCP_HEALTH_PATH)
MCP_INFO_URL ?= http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)$(MCP_INFO_PATH)

# Environment and scripts
ENV_LOCAL ?= .env.local
MCP_REGISTER_SCRIPT ?= scripts/forge_register_storagepilot.py
MCP_PUBLISH_SCRIPT ?= scripts/forge_publish_storagepilot.py

# ----------------------------
# Context Forge (Gateway) settings
# ----------------------------
FORGE_URL ?= http://localhost:4444

# =============================================================================
# Help
# =============================================================================

help:
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║       StoragePilot - AI-Powered Storage Lifecycle Manager     ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Quick Start:"
	@echo "  make install          Install everything (deps + Ollama + model)"
	@echo "  make setup-wizard     Run interactive setup wizard (configure LLM, paths)"
	@echo "  make api              Start web dashboard UI"
	@echo "  make run              Run CLI in dry-run mode"
	@echo ""
	@echo "Installation:"
	@echo "  make install          Full install (deps + Ollama + model)"
	@echo "  make setup-wizard     Interactive setup wizard (LLM, scan paths, etc.)"
	@echo "  make install-deps     Install Python dependencies only"
	@echo "  make install-ollama   Install Ollama (local LLM runtime)"
	@echo "  make install-model    Pull the default model ($(MODEL))"
	@echo ""
	@echo "Web Dashboard (React UI):"
	@echo "  make api              Start dashboard (dev mode, auto-reload)"
	@echo "  make api-prod         Start dashboard (production mode)"
	@echo ""
	@echo "CLI Commands:"
	@echo "  make run              Run StoragePilot CLI (dry-run mode)"
	@echo "  make run-execute      Run StoragePilot CLI (execute mode)"
	@echo "  make run-scan         Run scan only (no AI analysis)"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Verify Ollama is working"
	@echo "  make test-api         Run API unit tests"
	@echo "  make test-all         Run all tests with coverage"
	@echo "  make test-mcp         Test all MCP server tools"
	@echo ""
	@echo "MCP Server (Model Context Protocol):"
	@echo "  make mcp-server              Start MCP server (dry-run, stdio transport)"
	@echo "  make mcp-server-execute      Start MCP server (execute mode, stdio)"
	@echo "  make mcp-server-http         Start MCP HTTP server (for Context Forge)"
	@echo "  make mcp-server-http-execute Start MCP HTTP server (execute mode)"
	@echo "  make mcp-server-http-debug   Start MCP HTTP server (debug logging)"
	@echo "  make mcp-stop                Stop all running MCP servers"
	@echo "  make mcp-health              Check MCP server health"
	@echo "  make mcp-info                Get MCP server info"
	@echo "  make mcp-inspector           Launch MCP Inspector UI (stdio mode)"
	@echo "  make mcp-inspector-http      Launch MCP Inspector UI (HTTP/SSE mode)"
	@echo "  make mcp-dev                 Start server with MCP dev mode"
	@echo "  make mcp-list                List all available MCP tools"
	@echo "  make mcp-register            Register gateway to Context Forge (Layer 1)"
	@echo "  make mcp-publish             Publish catalog server for MatrixShell (Layer 2)"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean            Clean up generated files"
	@echo "  make help             Show this help message"
	@echo ""
	@echo "Model Options:"
	@echo "  make install-model MODEL=qwen2.5:0.5b   Smallest (~400MB)"
	@echo "  make install-model MODEL=llama3.2:1b   Small (~1GB)"
	@echo "  make install-model MODEL=llama3        Medium (~4GB)"
	@echo "  make install-model MODEL=mistral       Good balance (~4GB)"
	@echo ""
	@echo "MCP Server Configuration:"
	@echo "  MCP_HTTP_HOST=$(MCP_HTTP_HOST)  (bind address)"
	@echo "  MCP_HTTP_PORT=$(MCP_HTTP_PORT)  (port)"
	@echo "  MCP_CONNECT_HOST=$(MCP_CONNECT_HOST)  (client connect address)"
	@echo ""
	@echo "Examples:"
	@echo "  make mcp-server-http MCP_HTTP_HOST=0.0.0.0  # Bind to all interfaces"
	@echo "  make mcp-register MCP_CONNECT_HOST=host.docker.internal  # Docker"

# =============================================================================
# Installation Targets
# =============================================================================

# Full installation
install: install-deps install-ollama install-model
	@echo ""
	@echo "✓ Installation complete!"
	@echo ""
	@echo "Virtual environment: $(VENV)"
	@echo ""
	@echo "Run StoragePilot with: make run"
	@echo "Or activate venv manually: source $(VENV)/bin/activate"

# Install Python dependencies in virtual environment
install-deps:
	@echo "Creating virtual environment..."
	@if [ ! -d "$(VENV)" ]; then \
		python3 -m venv $(VENV); \
		echo "✓ Virtual environment created at $(VENV)"; \
	else \
		echo "✓ Virtual environment already exists"; \
	fi
	@echo ""
	@echo "Installing Python dependencies..."
	@if command -v uv >/dev/null 2>&1; then \
		echo "Using uv (fast mode)..."; \
		uv pip install --python $(PYTHON) --upgrade pip; \
		uv pip install --python $(PYTHON) -r requirements.txt; \
	else \
		echo "Using pip (install 'uv' for faster installs: pip install uv)..."; \
		$(PIP) install --upgrade pip; \
		$(PIP) install -r requirements.txt; \
	fi
	@echo ""
	@echo "✓ Dependencies installed in $(VENV)"

# Install Ollama
install-ollama:
	@echo "Installing Ollama..."
	@if command -v ollama >/dev/null 2>&1; then \
		echo "✓ Ollama already installed"; \
		ollama --version; \
	else \
		echo "Downloading Ollama installer..."; \
		curl -fsSL https://ollama.com/install.sh | sh; \
		echo "✓ Ollama installed"; \
	fi
	@echo ""
	@echo "Starting Ollama service..."
	@if pgrep -x "ollama" >/dev/null; then \
		echo "✓ Ollama already running"; \
	else \
		ollama serve >/dev/null 2>&1 & \
		sleep 2; \
		echo "✓ Ollama service started"; \
	fi

# Pull the smallest model
install-model:
	@echo "Pulling model: $(MODEL)"
	@echo "This may take a few minutes on first run..."
	ollama pull $(MODEL)
	@echo ""
	@echo "✓ Model $(MODEL) ready"

# Interactive setup wizard
setup-wizard:
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║           StoragePilot Setup Wizard                           ║"
	@echo "║       Configure LLM, scan paths, and safety settings          ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(PYTHON) scripts/setup_wizard.py

# =============================================================================
# Testing Targets
# =============================================================================

# Verify Ollama is working
test:
	@echo "Testing Ollama connection..."
	@if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then \
		echo "✓ Ollama is running"; \
		echo ""; \
		echo "Available models:"; \
		curl -s http://127.0.0.1:11434/api/tags | python3 -c "import sys,json; d=json.load(sys.stdin); print('\n'.join(['  - '+m['name'] for m in d.get('models',[])]))" 2>/dev/null || echo "  (none)"; \
	else \
		echo "✗ Ollama is not running"; \
		echo ""; \
		echo "Start with: ollama serve"; \
		exit 1; \
	fi

# Run API unit tests
test-api:
	@echo "Running API unit tests..."
	$(PYTHON) -m pytest tests/test_dashboard_api.py -v

# Run all tests (API + coverage)
test-all:
	@echo "Running all tests with coverage..."
	$(PYTHON) -m pytest tests/ -v --cov=ui --cov-report=term-missing

# Test all MCP tools automatically
test-mcp:
	@echo "Running MCP tool tests..."
	@if [ -f "./scripts/test_mcp_tools.sh" ]; then \
		./scripts/test_mcp_tools.sh; \
	else \
		echo "Test script not found. Running basic connectivity test..."; \
		$(MAKE) mcp-health || echo "Start MCP server first: make mcp-server-http"; \
	fi

# =============================================================================
# CLI Run Targets
# =============================================================================

# Run StoragePilot (dry-run mode - safe preview)
run:
	@echo "Running StoragePilot (dry-run mode)..."
	OPENAI_API_KEY=ollama OPENAI_BASE_URL=http://127.0.0.1:11434/v1 $(PYTHON) main.py --dry-run

# Run StoragePilot (execute mode - with actions)
run-execute:
	@echo "Running StoragePilot (execute mode)..."
	OPENAI_API_KEY=ollama OPENAI_BASE_URL=http://127.0.0.1:11434/v1 $(PYTHON) main.py --execute

# Run scan only (no AI analysis)
run-scan:
	$(PYTHON) main.py --scan-only

# =============================================================================
# Web Dashboard Targets
# =============================================================================

# Launch web dashboard (React UI)
api:
	@echo "Starting StoragePilot Dashboard..."
	@echo "Dashboard will be available at: http://127.0.0.1:8000"
	@echo "API docs at: http://127.0.0.1:8000/docs"
	$(PYTHON) -m uvicorn ui.dashboard:app --host 127.0.0.1 --port 8000 --reload

# Launch FastAPI dashboard (production mode)
api-prod:
	@echo "Starting StoragePilot Dashboard (production)..."
	$(PYTHON) -m uvicorn ui.dashboard:app --host 0.0.0.0 --port 8000

# =============================================================================
# MCP Server Commands
# =============================================================================

# Helper to check and install MCP SDK (with anyio upgrade for lowlevel module)
define check_mcp
	@$(PYTHON) -c "from mcp.server import Server" 2>/dev/null || \
		(echo "MCP SDK not found or outdated. Installing..." && \
		$(PIP) install --upgrade "anyio>=4.0.0" "mcp[cli]>=1.0.0" "starlette>=0.27.0" "uvicorn>=0.23.0" "sse-starlette>=1.6.0" && \
		echo "✓ MCP SDK installed")
endef

# Helper to check if MCP server script exists
define check_mcp_server
	@if [ ! -f "$(MCP_SERVER)" ]; then \
		echo "Error: MCP server script not found at $(MCP_SERVER)"; \
		exit 1; \
	fi
endef

# -----------------------------------------------------------------------------
# stdio Transport (for Claude Desktop, local clients)
# -----------------------------------------------------------------------------

# Start MCP server (dry-run mode - stdio transport)
mcp-server:
	$(call check_mcp)
	$(call check_mcp_server)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║           StoragePilot MCP Server v1.1.0                      ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Transport: stdio                                             ║"
	@echo "║  Mode:      DRY-RUN (preview only, no file changes)           ║"
	@echo "║  Tools:     15 available                                      ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(PYTHON) $(MCP_SERVER) --dry-run

# Start MCP server (execute mode - allows actual file changes)
mcp-server-execute:
	$(call check_mcp)
	$(call check_mcp_server)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║           StoragePilot MCP Server v1.1.0                      ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  ⚠️  WARNING: EXECUTE MODE - ACTUAL FILE OPERATIONS!          ║"
	@echo "║  Transport: stdio                                             ║"
	@echo "║  Mode:      EXECUTE (live file changes)                       ║"
	@echo "║  Tools:     15 available                                      ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(PYTHON) $(MCP_SERVER) --execute

# -----------------------------------------------------------------------------
# HTTP/SSE Transport (for Context Forge, MCP Gateway)
# -----------------------------------------------------------------------------

# Start MCP server with HTTP/SSE transport (DRY-RUN mode)
mcp-server-http:
	$(call check_mcp)
	$(call check_mcp_server)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║           StoragePilot MCP Server v1.1.0                      ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Transport: HTTP/SSE (for Context Forge / MCP Gateway)        ║"
	@echo "║  Mode:      DRY-RUN (preview only, no file changes)           ║"
	@echo "║  Tools:     15 available                                      ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Endpoints (canonical):                                       ║"
	@echo "║    SSE:      http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/sse               ║"
	@echo "║    Messages: http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/messages          ║"
	@echo "║  Endpoints (namespaced):                                      ║"
	@echo "║    SSE:      http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/mcp/sse           ║"
	@echo "║    Messages: http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/mcp/messages      ║"
	@echo "║  Utility:                                                     ║"
	@echo "║    Health:   http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/health            ║"
	@echo "║    Info:     http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/info              ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(PYTHON) $(MCP_SERVER) --http --host $(MCP_HTTP_HOST) --port $(MCP_HTTP_PORT) --dry-run

# Start MCP server with HTTP/SSE transport (EXECUTE mode)
mcp-server-http-execute:
	$(call check_mcp)
	$(call check_mcp_server)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║           StoragePilot MCP Server v1.1.0                      ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  ⚠️  WARNING: EXECUTE MODE - ACTUAL FILE OPERATIONS!          ║"
	@echo "║  Transport: HTTP/SSE (for Context Forge / MCP Gateway)        ║"
	@echo "║  Mode:      EXECUTE (live file changes)                       ║"
	@echo "║  Tools:     15 available                                      ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Endpoints (canonical):                                       ║"
	@echo "║    SSE:      http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/sse               ║"
	@echo "║    Messages: http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/messages          ║"
	@echo "║  Endpoints (namespaced):                                      ║"
	@echo "║    SSE:      http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/mcp/sse           ║"
	@echo "║    Messages: http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/mcp/messages      ║"
	@echo "║  Utility:                                                     ║"
	@echo "║    Health:   http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/health            ║"
	@echo "║    Info:     http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/info              ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(PYTHON) $(MCP_SERVER) --http --host $(MCP_HTTP_HOST) --port $(MCP_HTTP_PORT) --execute

# Start MCP server with HTTP/SSE transport (DEBUG mode)
mcp-server-http-debug:
	$(call check_mcp)
	$(call check_mcp_server)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║           StoragePilot MCP Server v1.1.0 (DEBUG)              ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Transport: HTTP/SSE                                          ║"
	@echo "║  Mode:      DRY-RUN + DEBUG (verbose logging)                 ║"
	@echo "║  SSE URL:   http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/sse               ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(PYTHON) $(MCP_SERVER) --http --host $(MCP_HTTP_HOST) --port $(MCP_HTTP_PORT) --dry-run --debug

# -----------------------------------------------------------------------------
# MCP Server Utilities
# -----------------------------------------------------------------------------

# Check MCP server health
mcp-health:
	@echo "Checking MCP server health..."
	@if curl -sS "$(MCP_HEALTH_URL)" 2>/dev/null; then \
		echo ""; \
		echo "✓ MCP server is healthy"; \
	else \
		echo "✗ MCP server not responding at $(MCP_HEALTH_URL)"; \
		echo "Start with: make mcp-server-http"; \
		exit 1; \
	fi

# Get MCP server info
mcp-info:
	@echo "Getting MCP server info..."
	@if curl -sS "$(MCP_INFO_URL)" 2>/dev/null | python3 -m json.tool 2>/dev/null; then \
		echo ""; \
	else \
		echo "✗ MCP server not responding at $(MCP_INFO_URL)"; \
		echo "Start with: make mcp-server-http"; \
		exit 1; \
	fi

# List all available MCP tools
mcp-list:
	$(call check_mcp)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║              StoragePilot MCP Tools (15 total)                ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Discovery Tools:"
	@echo "  • scan_directory         - Scan directory and show disk usage"
	@echo "  • find_large_files       - Find files larger than specified size"
	@echo "  • find_old_files         - Find files not modified within N days"
	@echo "  • find_developer_artifacts - Find node_modules, .venv, __pycache__, etc."
	@echo ""
	@echo "System Tools:"
	@echo "  • get_system_overview    - Get overall system storage info"
	@echo "  • get_docker_usage       - Get Docker storage breakdown"
	@echo ""
	@echo "Classification Tools:"
	@echo "  • classify_files         - Classify files and generate organization plan"
	@echo "  • classify_single_file   - Classify a single file"
	@echo "  • detect_duplicates      - Find duplicate files using content hashing"
	@echo ""
	@echo "Execution Tools:"
	@echo "  • move_file              - Move a file to new location"
	@echo "  • delete_file            - Delete a file (with optional backup)"
	@echo "  • create_directory       - Create a new directory"
	@echo "  • clean_docker           - Clean Docker resources"
	@echo ""
	@echo "Utility Tools:"
	@echo "  • calculate_file_hash    - Calculate file hash (xxhash/MD5)"
	@echo "  • get_server_info        - Get MCP server status and config"

# Stop all running MCP servers
mcp-stop:
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║              Stopping StoragePilot MCP Servers                ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Checking for running MCP servers..."
	@STOPPED=0; \
	if pgrep -f 'python.*mcp_server.py' >/dev/null 2>&1; then \
		echo "Stopping MCP server processes..."; \
		pkill -f 'python.*mcp_server.py' 2>/dev/null && STOPPED=1 && echo "  ✓ MCP servers stopped"; \
	else \
		echo "  No MCP servers running"; \
	fi; \
	if pgrep -f 'modelcontextprotocol/inspector' >/dev/null 2>&1; then \
		echo "Stopping MCP Inspector..."; \
		pkill -f 'modelcontextprotocol/inspector' 2>/dev/null && STOPPED=1 && echo "  ✓ MCP Inspector stopped"; \
	else \
		echo "  No MCP Inspector running"; \
	fi; \
	echo ""; \
	echo "Done."

# -----------------------------------------------------------------------------
# MCP Inspector / Dev Tools
# -----------------------------------------------------------------------------

# Launch MCP Inspector to test and debug tools (stdio mode)
mcp-inspector:
	$(call check_mcp)
	$(call check_mcp_server)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║              MCP Inspector - Tool Testing UI                  ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Mode:     stdio (spawns server directly)                     ║"
	@echo "║  Server:   $(MCP_SERVER)"
	@echo "║  Python:   $(ROOT)/$(PYTHON)"
	@echo "║  UI:       http://localhost:5173                              ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@if command -v npx >/dev/null 2>&1; then \
		npx @modelcontextprotocol/inspector "$(ROOT)/$(PYTHON)" "$(MCP_SERVER)" --dry-run; \
	else \
		echo "Error: npx not found. Install Node.js 18+ first."; \
		echo "  brew install node  (macOS)"; \
		echo "  apt install nodejs npm  (Linux)"; \
		exit 1; \
	fi

# Launch MCP Inspector for HTTP/SSE mode (connect by URL)
mcp-inspector-http:
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║              MCP Inspector - HTTP/SSE Mode                    ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Mode:     HTTP/SSE (connects to running server)              ║"
	@echo "║                                                               ║"
	@echo "║  1. Start MCP server first:                                   ║"
	@echo "║     make mcp-server-http                                      ║"
	@echo "║                                                               ║"
	@echo "║  2. In Inspector UI, set:                                     ║"
	@echo "║     Transport: SSE                                            ║"
	@echo "║     URL: http://$(MCP_CONNECT_HOST):$(MCP_HTTP_PORT)/sse                  ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@if command -v npx >/dev/null 2>&1; then \
		echo "Starting MCP Inspector..."; \
		npx @modelcontextprotocol/inspector; \
	else \
		echo "Error: npx not found. Install Node.js 18+ first."; \
		echo "  brew install node  (macOS)"; \
		echo "  apt install nodejs npm  (Linux)"; \
		exit 1; \
	fi

# Start MCP server with dev mode (built-in inspector via mcp CLI)
mcp-dev:
	$(call check_mcp)
	$(call check_mcp_server)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║              MCP Dev Mode (built-in inspector)                ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Command: mcp dev $(MCP_SERVER)"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(VENV)/bin/mcp dev $(MCP_SERVER)

# -----------------------------------------------------------------------------
# Context Forge Registration (Layer 1)
# -----------------------------------------------------------------------------

mcp-register:
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║     Registering StoragePilot MCP Server to Context Forge      ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@# Check prerequisites
	@test -f "$(ENV_LOCAL)" || (echo "Error: Missing $(ENV_LOCAL)"; \
		echo "Create .env.local with PLATFORM_ADMIN_EMAIL and PLATFORM_ADMIN_PASSWORD"; exit 1)
	@test -f "$(MCP_REGISTER_SCRIPT)" || (echo "Error: Missing: $(MCP_REGISTER_SCRIPT)"; exit 1)
	@# Check Context Forge
	@echo "Checking Context Forge at $(FORGE_URL)..."
	@curl -sS "$(FORGE_URL)/health" > /dev/null 2>&1 || \
		(echo ""; echo "Error: Context Forge not running at $(FORGE_URL)"; \
		echo "Start Context Forge first (make serve in Context Forge repo)"; exit 1)
	@echo "  ✓ Context Forge is running"
	@echo ""
	@# Check/start MCP server
	@echo "Checking MCP server at $(MCP_HEALTH_URL)..."
	@if ! curl -sS "$(MCP_HEALTH_URL)" > /dev/null 2>&1; then \
		echo "  MCP server not running. Starting in background..."; \
		$(PYTHON) $(MCP_SERVER) --http --host $(MCP_HTTP_HOST) --port $(MCP_HTTP_PORT) --dry-run > /tmp/mcp_server.log 2>&1 & \
		echo "  Waiting for MCP server to start..."; \
		for i in 1 2 3 4 5 6 7 8 9 10; do \
			sleep 1; \
			if curl -sS "$(MCP_HEALTH_URL)" > /dev/null 2>&1; then \
				echo "  ✓ MCP server started"; \
				break; \
			fi; \
			if [ $$i -eq 10 ]; then \
				echo "  Error: MCP server failed to start after 10 seconds"; \
				echo "  Check logs: cat /tmp/mcp_server.log"; \
				exit 1; \
			fi; \
		done; \
	else \
		echo "  ✓ MCP server is already running"; \
	fi
	@echo ""
	@echo "Registering with Context Forge..."
	@echo "  MCP Server URL: $(MCP_SERVER_URL)"
	@echo ""
	@$(PYTHON) $(MCP_REGISTER_SCRIPT) --env "$(ENV_LOCAL)" --mcp-url "$(MCP_SERVER_URL)" --skip-health-checks
	@echo ""
	@echo "Done. Check Context Forge Admin UI -> Gateways to verify."

# -----------------------------------------------------------------------------
# Context Forge - Publish Catalog Server (Layer 2)
# -----------------------------------------------------------------------------

mcp-publish:
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║     Publishing StoragePilot to Context Forge Catalog          ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@test -f "$(ENV_LOCAL)" || (echo "Error: Missing $(ENV_LOCAL)"; exit 1)
	@test -f "$(MCP_PUBLISH_SCRIPT)" || (echo "Error: Missing: $(MCP_PUBLISH_SCRIPT)"; exit 1)
	@echo "Checking Context Forge at $(FORGE_URL)..."
	@curl -sS "$(FORGE_URL)/health" > /dev/null 2>&1 || \
		(echo ""; echo "Error: Context Forge not running at $(FORGE_URL)"; exit 1)
	@echo "  ✓ Context Forge is running"
	@echo ""
	@$(PYTHON) $(MCP_PUBLISH_SCRIPT) --env "$(ENV_LOCAL)"
	@echo ""
	@echo "Done. MatrixShell can now sync StoragePilot tools."

# =============================================================================
# Cleanup
# =============================================================================

# Clean generated files
clean:
	@echo "Cleaning up..."
	rm -rf __pycache__ tools/__pycache__ agents/__pycache__
	rm -rf .pytest_cache .mypy_cache
	rm -f logs/*.log logs/*.txt
	rm -f /tmp/mcp_server.log
	@echo "✓ Cleaned"
