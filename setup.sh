#!/bin/bash
# StoragePilot Setup Script
# ==========================
# Usage:
#   ./setup.sh           - Full installation + optional wizard
#   ./setup.sh --wizard  - Run only the interactive setup wizard
#   ./setup.sh --install - Run only the installation (no wizard)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Parse arguments
RUN_WIZARD=false
RUN_INSTALL=true

for arg in "$@"; do
    case $arg in
        --wizard)
            RUN_WIZARD=true
            RUN_INSTALL=false
            ;;
        --install)
            RUN_INSTALL=true
            RUN_WIZARD=false
            ;;
        --help|-h)
            echo "StoragePilot Setup Script"
            echo ""
            echo "Usage: ./setup.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --wizard   Run only the interactive setup wizard"
            echo "  --install  Run only the installation (no wizard)"
            echo "  --help     Show this help message"
            echo ""
            echo "Default: Runs installation, then optionally the wizard"
            exit 0
            ;;
    esac
done

# Run installation if requested
if [ "$RUN_INSTALL" = true ]; then
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║           StoragePilot Installation Script                    ║"
    echo "║       AI-Powered Storage Lifecycle Manager                    ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""

    # Check Python version
    echo "Checking Python version..."
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    echo "   Found Python $python_version"

    # Create virtual environment
    echo ""
    echo "Creating virtual environment..."
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
        echo "   Virtual environment created"
    else
        echo "   Virtual environment already exists"
    fi
    source .venv/bin/activate
    echo "   Virtual environment activated"

    # Upgrade pip
    echo ""
    echo "Upgrading pip..."
    pip install --upgrade pip -q

    # Install dependencies
    echo ""
    echo "Installing dependencies..."
    pip install -r requirements.txt -q
    echo "   Dependencies installed"

    # Create necessary directories
    echo ""
    echo "Creating directories..."
    mkdir -p logs
    mkdir -p config
    echo "   Directories created"

    # Check for API keys
    echo ""
    echo "Checking API keys..."
    if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
        echo "   No API key found (Ollama will be used by default)"
    else
        if [ -n "$OPENAI_API_KEY" ]; then
            echo "   OPENAI_API_KEY found"
        fi
        if [ -n "$ANTHROPIC_API_KEY" ]; then
            echo "   ANTHROPIC_API_KEY found"
        fi
    fi

    # Installation complete
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                 Installation Complete!                        ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""

    # Ask to run wizard
    if [ -z "$RUN_WIZARD" ] || [ "$RUN_WIZARD" = false ]; then
        echo "Would you like to run the interactive setup wizard? (y/N)"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            RUN_WIZARD=true
        fi
    fi
fi

# Run wizard if requested
if [ "$RUN_WIZARD" = true ]; then
    echo ""
    echo "Starting interactive setup wizard..."
    echo ""

    # Activate venv if not already
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi

    python3 scripts/setup_wizard.py
    exit 0
fi

# Print quick start if wizard wasn't run
echo ""
echo "Quick Start:"
echo ""
echo "   1. Activate the virtual environment:"
echo "      source .venv/bin/activate"
echo ""
echo "   2. Run the setup wizard to configure LLM and paths:"
echo "      make setup-wizard"
echo "      # or"
echo "      python scripts/setup_wizard.py"
echo ""
echo "   3. Run StoragePilot:"
echo "      make run              # CLI (dry-run mode)"
echo "      make api              # Web dashboard"
echo ""
echo "For more information, see README.md"
echo ""
