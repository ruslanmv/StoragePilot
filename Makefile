# StoragePilot Makefile
# =====================
# Quick setup and installation commands

.PHONY: help install install-ollama install-model install-deps run test clean

# Default model (smallest for quick start)
MODEL ?= qwen2.5:0.5b

help:
	@echo "StoragePilot - AI-Powered Storage Lifecycle Manager"
	@echo ""
	@echo "Quick Start:"
	@echo "  make install          Install everything (deps + Ollama + model)"
	@echo "  make run              Run StoragePilot in dry-run mode"
	@echo ""
	@echo "Individual Targets:"
	@echo "  make install-deps     Install Python dependencies"
	@echo "  make install-ollama   Install Ollama (local LLM runtime)"
	@echo "  make install-model    Pull the default model ($(MODEL))"
	@echo "  make run              Run StoragePilot (dry-run mode)"
	@echo "  make run-execute      Run StoragePilot (execute mode)"
	@echo "  make test             Verify Ollama is working"
	@echo "  make clean            Clean up generated files"
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
	@echo "Run StoragePilot with: make run"

# Install Python dependencies
install-deps:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt

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

# Run StoragePilot (dry-run mode - safe preview)
run:
	@echo "Running StoragePilot (dry-run mode)..."
	OPENAI_API_KEY=ollama OPENAI_BASE_URL=http://127.0.0.1:11434/v1 python main.py --dry-run

# Run StoragePilot (execute mode - with actions)
run-execute:
	@echo "Running StoragePilot (execute mode)..."
	OPENAI_API_KEY=ollama OPENAI_BASE_URL=http://127.0.0.1:11434/v1 python main.py --execute

# Run scan only (no AI analysis)
run-scan:
	python main.py --scan-only

# Launch UI dashboard
run-ui:
	python main.py --ui

# Clean generated files
clean:
	@echo "Cleaning up..."
	rm -rf __pycache__ tools/__pycache__ agents/__pycache__
	rm -rf .pytest_cache .mypy_cache
	rm -f logs/*.log logs/*.txt
	@echo "✓ Cleaned"

# Start MCP server (for LLM tool integration)
mcp-server:
	python mcp_server.py --dry-run

mcp-server-execute:
	python mcp_server.py --execute
