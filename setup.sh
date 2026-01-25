#!/bin/bash
# StoragePilot Setup Script
# ==========================

set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║           StoragePilot Installation Script                    ║"
echo "║       AI-Powered Storage Lifecycle Manager                    ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Check Python version
echo "🔍 Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "   Found Python $python_version"

# Create virtual environment
echo ""
echo "📦 Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
echo "   Virtual environment activated"

# Upgrade pip
echo ""
echo "⬆️  Upgrading pip..."
pip install --upgrade pip -q

# Install dependencies
echo ""
echo "📥 Installing dependencies..."
pip install -r requirements.txt -q
echo "   Dependencies installed"

# Create necessary directories
echo ""
echo "📁 Creating directories..."
mkdir -p logs
mkdir -p config
echo "   Directories created"

# Check for API keys
echo ""
echo "🔑 Checking API keys..."
if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "   ⚠️  No API key found!"
    echo ""
    echo "   Please set one of the following environment variables:"
    echo "   export OPENAI_API_KEY='your-key-here'"
    echo "   export ANTHROPIC_API_KEY='your-key-here'"
    echo ""
else
    if [ -n "$OPENAI_API_KEY" ]; then
        echo "   ✓ OPENAI_API_KEY found"
    fi
    if [ -n "$ANTHROPIC_API_KEY" ]; then
        echo "   ✓ ANTHROPIC_API_KEY found"
    fi
fi

# Installation complete
echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                 Installation Complete! ✓                      ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "🚀 Quick Start:"
echo ""
echo "   1. Activate the virtual environment:"
echo "      source .venv/bin/activate"
echo ""
echo "   2. Set your API key (if not already set):"
echo "      export OPENAI_API_KEY='your-key-here'"
echo ""
echo "   3. Run StoragePilot:"
echo ""
echo "      # Preview mode (safe, no changes):"
echo "      python main.py --dry-run"
echo ""
echo "      # Scan only (no AI analysis):"
echo "      python main.py --scan-only"
echo ""
echo "      # Launch the UI:"
echo "      python main.py --ui"
echo "      # or"
echo "      streamlit run ui/dashboard.py"
echo ""
echo "   4. Execute with approval (makes changes):"
echo "      python main.py --execute"
echo ""
echo "📖 For more information, see README.md"
echo ""
