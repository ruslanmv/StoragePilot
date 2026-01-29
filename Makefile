# StoragePilot Makefile
# =====================
# Quick setup and installation commands

.PHONY: help install install-deps install-ollama install-model setup-wizard run run-execute run-scan api api-prod test test-api test-all test-mcp clean mcp-server mcp-server-execute mcp-server-http mcp-server-http-execute mcp-inspector mcp-dev mcp-list mcp-register mcp-stop

# Virtual environment paths
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# Default model (smallest for quick start)
MODEL ?= qwen2.5:0.5b

help:
	@echo "StoragePilot - AI-Powered Storage Lifecycle Manager"
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
	@echo "  make mcp-stop                Stop all running MCP servers"
	@echo "  make mcp-inspector           Launch MCP Inspector UI (test/debug)"
	@echo "  make mcp-dev                 Start server with MCP dev mode"
	@echo "  make mcp-list                List all available MCP tools"
	@echo "  make mcp-register            Register StoragePilot to Context Forge"
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

# Clean generated files
clean:
	@echo "Cleaning up..."
	rm -rf __pycache__ tools/__pycache__ agents/__pycache__
	rm -rf .pytest_cache .mypy_cache
	rm -f logs/*.log logs/*.txt
	@echo "✓ Cleaned"

# =============================================================================
# MCP Server Commands
# =============================================================================

# Helper to check and install MCP SDK (with anyio upgrade for lowlevel module)
define check_mcp
	@$(PYTHON) -c "from mcp.server import Server" 2>/dev/null || (echo "MCP SDK not found or outdated. Installing..." && $(PIP) install --upgrade "anyio>=4.0.0" "mcp[cli]>=1.0.0" && echo "✓ MCP SDK installed")
endef

# Start MCP server (dry-run mode - stdio transport)
mcp-server:
	$(call check_mcp)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║           StoragePilot MCP Server (DRY-RUN MODE)              ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Transport: stdio                                             ║"
	@echo "║  Mode: DRY-RUN (preview only, no file changes)                ║"
	@echo "║                                                               ║"
	@echo "║  To test with MCP Inspector:                                  ║"
	@echo "║    make mcp-inspector                                         ║"
	@echo "║                                                               ║"
	@echo "║  To connect from Claude Desktop, add to config:               ║"
	@echo "║    \"storagepilot\": {                                          ║"
	@echo "║      \"command\": \"$(CURDIR)/$(PYTHON)\",                        ║"
	@echo "║      \"args\": [\"$(CURDIR)/mcp_server.py\", \"--dry-run\"]         ║"
	@echo "║    }                                                          ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(PYTHON) mcp_server.py --dry-run

# Start MCP server (execute mode - allows actual file changes)
mcp-server-execute:
	$(call check_mcp)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║         StoragePilot MCP Server (EXECUTE MODE)                ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  WARNING: This mode performs ACTUAL file operations!          ║"
	@echo "║                                                               ║"
	@echo "║  Transport: stdio                                             ║"
	@echo "║  Mode: EXECUTE (live file changes)                            ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(PYTHON) mcp_server.py --execute

# HTTP server port (default: 9000)
MCP_HTTP_PORT ?= 9000
MCP_HTTP_HOST ?= 127.0.0.1

# Start MCP server with HTTP/SSE transport (for Context Forge integration)
mcp-server-http:
	$(call check_mcp)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║      StoragePilot MCP Server (HTTP/SSE - DRY-RUN MODE)        ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Transport: HTTP/SSE (for Context Forge)                      ║"
	@echo "║  Mode: DRY-RUN (preview only, no file changes)                ║"
	@echo "║  URL: http://$(MCP_HTTP_HOST):$(MCP_HTTP_PORT)/mcp/sse        ║"
	@echo "║                                                               ║"
	@echo "║  After starting, run: make mcp-register                       ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(PYTHON) mcp_server.py --http --host $(MCP_HTTP_HOST) --port $(MCP_HTTP_PORT) --dry-run

# Start MCP server with HTTP/SSE transport (execute mode)
mcp-server-http-execute:
	$(call check_mcp)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║       StoragePilot MCP Server (HTTP/SSE - EXECUTE MODE)       ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  WARNING: This mode performs ACTUAL file operations!          ║"
	@echo "║                                                               ║"
	@echo "║  Transport: HTTP/SSE (for Context Forge)                      ║"
	@echo "║  Mode: EXECUTE (live file changes)                            ║"
	@echo "║  URL: http://$(MCP_HTTP_HOST):$(MCP_HTTP_PORT)/mcp/sse        ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(PYTHON) mcp_server.py --http --host $(MCP_HTTP_HOST) --port $(MCP_HTTP_PORT) --execute

# Launch MCP Inspector to test and debug tools
mcp-inspector:
	$(call check_mcp)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║              MCP Inspector - Tool Testing UI                  ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Starting MCP Inspector with StoragePilot server...           ║"
	@echo "║                                                               ║"
	@echo "║  The Inspector UI will open at: http://localhost:5173         ║"
	@echo "║                                                               ║"
	@echo "║  Features:                                                    ║"
	@echo "║    - Visualize all available tools                            ║"
	@echo "║    - Test tools with custom inputs                            ║"
	@echo "║    - Debug connection issues                                  ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@if command -v npx >/dev/null 2>&1; then \
		npx @modelcontextprotocol/inspector $(PYTHON) mcp_server.py --dry-run; \
	else \
		echo "Error: npx not found. Install Node.js 18+ first."; \
		echo "  brew install node  (macOS)"; \
		echo "  apt install nodejs npm  (Linux)"; \
		exit 1; \
	fi

# Start MCP server with dev mode (built-in inspector via mcp CLI)
mcp-dev:
	$(call check_mcp)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║              MCP Dev Mode (built-in inspector)                ║"
	@echo "╠═══════════════════════════════════════════════════════════════╣"
	@echo "║  Starting with: mcp dev mcp_server.py                         ║"
	@echo "║                                                               ║"
	@echo "║  This uses the MCP CLI's built-in development server.         ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	$(VENV)/bin/mcp dev mcp_server.py

# List all available MCP tools
mcp-list:
	$(call check_mcp)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║              StoragePilot MCP Tools                           ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Discovery Tools:"
	@echo "  • scan_directory          - Scan directory for disk usage"
	@echo "  • find_large_files        - Find files larger than threshold"
	@echo "  • find_old_files          - Find files not modified recently"
	@echo "  • find_developer_artifacts - Find node_modules, .venv, etc."
	@echo ""
	@echo "System Tools:"
	@echo "  • get_system_overview     - Get overall storage info"
	@echo "  • get_docker_usage        - Get Docker storage breakdown"
	@echo ""
	@echo "Classification Tools:"
	@echo "  • classify_files          - Classify all files in directory"
	@echo "  • classify_single_file    - Classify a single file"
	@echo "  • detect_duplicates       - Find duplicate files (MD5 hash)"
	@echo ""
	@echo "Execution Tools (respects dry-run mode):"
	@echo "  • move_file               - Move file to new location"
	@echo "  • delete_file             - Delete file (with backup option)"
	@echo "  • create_directory        - Create new directory"
	@echo "  • clean_docker            - Clean Docker resources"
	@echo ""
	@echo "Utility Tools:"
	@echo "  • calculate_file_hash     - Calculate file hash"
	@echo "  • get_server_info         - Get MCP server status"
	@echo ""
	@echo "Total: 15 tools available"
	@echo ""
	@echo "To test tools interactively: make mcp-inspector"
	@echo "To run automated tests:      make test-mcp"

# Test all MCP tools automatically
test-mcp:
	@echo "Running MCP tool tests..."
	@./scripts/test_mcp_tools.sh

# -----------------------------------------------------------------------------
# MCP Context Forge Registration
# -----------------------------------------------------------------------------
# Register StoragePilot as an HTTP/SSE gateway in MCP Context Forge
#
# Prerequisites:
#   1. Start StoragePilot HTTP server: make mcp-server-http
#   2. Create .env.local with Context Forge credentials
#   3. Ensure Context Forge is running (make serve in Context Forge repo)
#
# .env.local should contain:
#   PLATFORM_ADMIN_EMAIL=admin@example.com
#   PLATFORM_ADMIN_PASSWORD=your-password
#   FORGE_URL=http://localhost:4444  (optional, defaults to localhost:4444)
# -----------------------------------------------------------------------------

ENV_LOCAL ?= .env.local
MCP_SERVER_URL ?= http://$(MCP_HTTP_HOST):$(MCP_HTTP_PORT)/mcp/sse
MCP_REGISTER_SCRIPT ?= scripts/forge_register_storagepilot.sh

# Default Context Forge URL (can be overridden via .env.local or command line)
FORGE_URL ?= http://localhost:4444

mcp-register:
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║     Registering StoragePilot MCP Server to Context Forge      ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@test -f "$(ENV_LOCAL)" || (echo "Error: Missing $(ENV_LOCAL)"; echo "Create .env.local with PLATFORM_ADMIN_EMAIL and PLATFORM_ADMIN_PASSWORD"; exit 1)
	@test -x "$(MCP_REGISTER_SCRIPT)" || (echo "Error: Missing or not executable: $(MCP_REGISTER_SCRIPT)"; exit 1)
	@echo "Checking if Context Forge is running at $(FORGE_URL)..."
	@curl -sS "$(FORGE_URL)/health" > /dev/null 2>&1 || (echo ""; echo "Error: Context Forge not running at $(FORGE_URL)"; echo "Start Context Forge first (make serve in Context Forge repo)"; exit 1)
	@echo "Context Forge is running"
	@echo ""
	@echo "Checking if MCP server is running at http://$(MCP_HTTP_HOST):$(MCP_HTTP_PORT)..."
	@if ! curl -sS "http://$(MCP_HTTP_HOST):$(MCP_HTTP_PORT)/health" > /dev/null 2>&1; then \
		echo "MCP server not running. Starting in background..."; \
		$(PYTHON) mcp_server.py --http --host $(MCP_HTTP_HOST) --port $(MCP_HTTP_PORT) --dry-run > /dev/null 2>&1 & \
		echo "Waiting for MCP server to start..."; \
		for i in 1 2 3 4 5 6 7 8 9 10; do \
			sleep 1; \
			if curl -sS "http://$(MCP_HTTP_HOST):$(MCP_HTTP_PORT)/health" > /dev/null 2>&1; then \
				echo "MCP server started successfully"; \
				break; \
			fi; \
			if [ $$i -eq 10 ]; then \
				echo "Error: MCP server failed to start after 10 seconds"; \
				exit 1; \
			fi; \
		done; \
	else \
		echo "MCP server is already running"; \
	fi
	@echo ""
	@echo "MCP Server URL: $(MCP_SERVER_URL)"
	@echo ""
	@./$(MCP_REGISTER_SCRIPT) "$(ENV_LOCAL)" "$(MCP_SERVER_URL)"
	@echo ""
	@echo "Done. Check Context Forge Admin UI -> Gateways to verify."
	@echo ""
	@echo "Note: MCP server is running in background on http://$(MCP_HTTP_HOST):$(MCP_HTTP_PORT)"
	@echo "To stop it: make mcp-stop"

# Stop all running MCP servers
mcp-stop:
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║              Stopping StoragePilot MCP Servers                ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Checking for running MCP servers..."
	@ps aux 2>/dev/null | grep -v grep | grep -q 'mcp_server.py.*--http' && \
		(echo "Stopping HTTP/SSE MCP servers..." && pkill -f 'python.*mcp_server.py.*--http' && echo "Stopped") || \
		echo "No HTTP MCP servers running"
	@ps aux 2>/dev/null | grep -v grep | grep -q 'mcp_server.py.*--dry-run' && \
		(echo "Stopping STDIO dry-run servers..." && pkill -f 'python.*mcp_server.py.*--dry-run' && echo "Stopped") || \
		echo "No STDIO dry-run servers running"
	@ps aux 2>/dev/null | grep -v grep | grep -q 'mcp_server.py.*--execute' && \
		(echo "Stopping STDIO execute servers..." && pkill -f 'python.*mcp_server.py.*--execute' && echo "Stopped") || \
		echo "No STDIO execute servers running"
	@ps aux 2>/dev/null | grep -v grep | grep -q 'modelcontextprotocol/inspector' && \
		(echo "Stopping MCP Inspector..." && pkill -f 'modelcontextprotocol/inspector' && echo "Stopped") || \
		echo "No MCP Inspector running"
	@echo ""
	@echo "Done."
