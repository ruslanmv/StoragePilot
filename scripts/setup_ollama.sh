#!/bin/bash
# =============================================================================
# StoragePilot - Ollama Setup Script
# =============================================================================
# This script installs Ollama and pulls the smallest model for quick start.
#
# Usage:
#   ./scripts/setup_ollama.sh              # Install + pull smallest model
#   ./scripts/setup_ollama.sh --model X    # Install + pull specific model
#
# Models (smallest to largest):
#   qwen2.5:0.5b  (~400MB) - Default, fastest
#   llama3.2:1b   (~1GB)   - Small but capable
#   llama3        (~4GB)   - Good general purpose
#   mistral       (~4GB)   - Good balance
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default model (smallest)
MODEL="${1:-qwen2.5:0.5b}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  StoragePilot - Ollama Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# -----------------------------------------------------------------------------
# Step 1: Check/Install Ollama
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[1/4] Checking Ollama installation...${NC}"

if command -v ollama &> /dev/null; then
    echo -e "${GREEN}✓ Ollama is already installed${NC}"
    ollama --version
else
    echo -e "${YELLOW}Installing Ollama...${NC}"

    # Detect OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "Detected: Linux"
        curl -fsSL https://ollama.com/install.sh | sh
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "Detected: macOS"
        if command -v brew &> /dev/null; then
            brew install ollama
        else
            curl -fsSL https://ollama.com/install.sh | sh
        fi
    else
        echo -e "${RED}Unsupported OS: $OSTYPE${NC}"
        echo "Please install Ollama manually from: https://ollama.com/download"
        exit 1
    fi

    echo -e "${GREEN}✓ Ollama installed${NC}"
fi

# -----------------------------------------------------------------------------
# Step 2: Start Ollama service
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[2/4] Starting Ollama service...${NC}"

# Check if Ollama is already running
if curl -s http://127.0.0.1:11434/api/tags &> /dev/null; then
    echo -e "${GREEN}✓ Ollama is already running${NC}"
else
    echo "Starting Ollama in background..."

    # Try to start Ollama
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS: Ollama might be a GUI app
        open -a Ollama 2>/dev/null || ollama serve &>/dev/null &
    else
        # Linux: Start as background process
        ollama serve &>/dev/null &
    fi

    # Wait for Ollama to start (up to 30 seconds)
    echo -n "Waiting for Ollama to start"
    for i in {1..30}; do
        if curl -s http://127.0.0.1:11434/api/tags &> /dev/null; then
            echo ""
            echo -e "${GREEN}✓ Ollama service started${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done

    # Final check
    if ! curl -s http://127.0.0.1:11434/api/tags &> /dev/null; then
        echo ""
        echo -e "${RED}✗ Failed to start Ollama${NC}"
        echo "Please start Ollama manually with: ollama serve"
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# Step 3: Pull the model
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[3/4] Pulling model: ${MODEL}${NC}"
echo "This may take a few minutes on first run..."
echo ""

ollama pull "$MODEL"

echo ""
echo -e "${GREEN}✓ Model ${MODEL} ready${NC}"

# -----------------------------------------------------------------------------
# Step 4: Verify installation
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[4/4] Verifying installation...${NC}"

# List available models
echo ""
echo "Available models:"
ollama list

# Test the model with a simple prompt
echo ""
echo "Testing model with a simple prompt..."
RESPONSE=$(ollama run "$MODEL" "Say 'Hello, StoragePilot!' in exactly 3 words" 2>/dev/null | head -1)
echo -e "Model response: ${GREEN}${RESPONSE}${NC}"

# -----------------------------------------------------------------------------
# Done!
# -----------------------------------------------------------------------------
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Ollama is running at: http://127.0.0.1:11434"
echo "Model ready: ${MODEL}"
echo ""
echo "Next steps:"
echo "  1. Install StoragePilot deps: make install-deps"
echo "  2. Run StoragePilot:          make run"
echo ""
