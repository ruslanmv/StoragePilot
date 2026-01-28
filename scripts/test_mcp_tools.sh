#!/bin/bash
# =============================================================================
# StoragePilot MCP Server - Tool Testing Script
# =============================================================================
# Tests all MCP server tools by sending JSON-RPC requests via stdio
#
# Usage:
#   ./scripts/test_mcp_tools.sh
#   make test-mcp
#
# Requirements:
#   - jq (for JSON parsing)
#   - Python venv with mcp[cli] installed
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
MCP_SERVER="$PROJECT_ROOT/mcp_server.py"

# Check dependencies
check_deps() {
    if ! command -v jq &> /dev/null; then
        echo -e "${RED}Error: jq is required but not installed.${NC}"
        echo "Install with: apt install jq (Linux) or brew install jq (macOS)"
        exit 1
    fi

    if [ ! -f "$PYTHON" ]; then
        echo -e "${RED}Error: Virtual environment not found at $PROJECT_ROOT/.venv${NC}"
        echo "Run: make install"
        exit 1
    fi
}

# Send a JSON-RPC request to the MCP server and get response
call_mcp_tool() {
    local tool_name="$1"
    local args="$2"
    local request_id="${3:-1}"

    # Build JSON-RPC request
    local request=$(cat <<EOF
{"jsonrpc":"2.0","id":$request_id,"method":"tools/call","params":{"name":"$tool_name","arguments":$args}}
EOF
)

    # Send to MCP server (with timeout)
    echo "$request" | timeout 30 "$PYTHON" "$MCP_SERVER" --dry-run 2>/dev/null | head -1
}

# Test a single tool and display result
test_tool() {
    local tool_name="$1"
    local args="$2"
    local description="$3"

    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}Testing: $tool_name${NC}"
    echo -e "${BLUE}Description: $description${NC}"
    echo -e "${BLUE}Arguments: $args${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    local response=$(call_mcp_tool "$tool_name" "$args")

    if [ -n "$response" ]; then
        echo "$response" | jq -r '.result.content[0].text // .error // .' 2>/dev/null || echo "$response"
        echo -e "${GREEN}✓ Tool responded${NC}"
    else
        echo -e "${RED}✗ No response or timeout${NC}"
    fi
}

# Initialize MCP session
init_session() {
    local init_request='{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test-client","version":"1.0.0"}}}'
    echo "$init_request"
}

# Main test function using a single MCP session
run_tests() {
    echo -e "${GREEN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║        StoragePilot MCP Server - Tool Test Suite              ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # Create a test directory for some operations
    TEST_DIR="/tmp/storagepilot_test_$$"
    mkdir -p "$TEST_DIR"
    echo "Test file content" > "$TEST_DIR/test_file.txt"
    echo "Another test file" > "$TEST_DIR/another_file.txt"
    cp "$TEST_DIR/test_file.txt" "$TEST_DIR/duplicate_file.txt"
    mkdir -p "$TEST_DIR/subdir"

    echo -e "${YELLOW}Test directory created: $TEST_DIR${NC}"

    # Build all test requests
    local requests=""
    local id=1

    # Initialize
    requests+='{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test-client","version":"1.0.0"}}}'$'\n'

    # 1. get_server_info
    requests+='{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_server_info","arguments":{}}}'$'\n'

    # 2. get_system_overview
    requests+='{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_system_overview","arguments":{}}}'$'\n'

    # 3. scan_directory
    requests+='{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"scan_directory","arguments":{"path":"'"$TEST_DIR"'"}}}'$'\n'

    # 4. find_large_files
    requests+='{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"find_large_files","arguments":{"path":"'"$TEST_DIR"'","min_size":"1B"}}}'$'\n'

    # 5. find_old_files
    requests+='{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"find_old_files","arguments":{"path":"'"$TEST_DIR"'","days":1}}}'$'\n'

    # 6. find_developer_artifacts
    requests+='{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"find_developer_artifacts","arguments":{"workspace_path":"'"$PROJECT_ROOT"'"}}}'$'\n'

    # 7. get_docker_usage
    requests+='{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"get_docker_usage","arguments":{}}}'$'\n'

    # 8. classify_single_file
    requests+='{"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"classify_single_file","arguments":{"file_path":"'"$TEST_DIR/test_file.txt"'"}}}'$'\n'

    # 9. classify_files
    requests+='{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"classify_files","arguments":{"directory_path":"'"$TEST_DIR"'"}}}'$'\n'

    # 10. detect_duplicates
    requests+='{"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"detect_duplicates","arguments":{"directory_path":"'"$TEST_DIR"'"}}}'$'\n'

    # 11. calculate_file_hash
    requests+='{"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":"calculate_file_hash","arguments":{"file_path":"'"$TEST_DIR/test_file.txt"'"}}}'$'\n'

    # 12. create_directory (dry-run)
    requests+='{"jsonrpc":"2.0","id":12,"method":"tools/call","params":{"name":"create_directory","arguments":{"path":"'"$TEST_DIR/new_dir"'"}}}'$'\n'

    # 13. move_file (dry-run)
    requests+='{"jsonrpc":"2.0","id":13,"method":"tools/call","params":{"name":"move_file","arguments":{"source":"'"$TEST_DIR/test_file.txt"'","destination":"'"$TEST_DIR/moved_file.txt"'"}}}'$'\n'

    # 14. delete_file (dry-run)
    requests+='{"jsonrpc":"2.0","id":14,"method":"tools/call","params":{"name":"delete_file","arguments":{"path":"'"$TEST_DIR/another_file.txt"'","backup":true}}}'$'\n'

    # 15. clean_docker (dry-run)
    requests+='{"jsonrpc":"2.0","id":15,"method":"tools/call","params":{"name":"clean_docker","arguments":{"prune_all":false}}}'$'\n'

    echo -e "\n${YELLOW}Sending requests to MCP server...${NC}\n"

    # Send all requests and capture responses
    local responses=$(echo -e "$requests" | timeout 60 "$PYTHON" "$MCP_SERVER" --dry-run 2>/dev/null)

    # Tool descriptions for output
    declare -A tool_desc
    tool_desc[1]="Get MCP server status and configuration"
    tool_desc[2]="Get overall system storage information"
    tool_desc[3]="Scan directory for disk usage breakdown"
    tool_desc[4]="Find files larger than specified size"
    tool_desc[5]="Find files not modified within specified days"
    tool_desc[6]="Find developer artifacts (node_modules, .venv, etc.)"
    tool_desc[7]="Get Docker storage usage breakdown"
    tool_desc[8]="Classify a single file"
    tool_desc[9]="Classify all files in a directory"
    tool_desc[10]="Find duplicate files using content hashing"
    tool_desc[11]="Calculate file hash"
    tool_desc[12]="Create a new directory [DRY-RUN]"
    tool_desc[13]="Move file to new location [DRY-RUN]"
    tool_desc[14]="Delete file with backup [DRY-RUN]"
    tool_desc[15]="Clean Docker resources [DRY-RUN]"

    declare -A tool_name
    tool_name[1]="get_server_info"
    tool_name[2]="get_system_overview"
    tool_name[3]="scan_directory"
    tool_name[4]="find_large_files"
    tool_name[5]="find_old_files"
    tool_name[6]="find_developer_artifacts"
    tool_name[7]="get_docker_usage"
    tool_name[8]="classify_single_file"
    tool_name[9]="classify_files"
    tool_name[10]="detect_duplicates"
    tool_name[11]="calculate_file_hash"
    tool_name[12]="create_directory"
    tool_name[13]="move_file"
    tool_name[14]="delete_file"
    tool_name[15]="clean_docker"

    # Parse and display each response
    local passed=0
    local failed=0

    for i in {1..15}; do
        echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${YELLOW}[$i/15] ${tool_name[$i]}${NC}"
        echo -e "${BLUE}${tool_desc[$i]}${NC}"
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

        # Extract response for this ID
        local response=$(echo "$responses" | grep "\"id\":$i" | head -1)

        if [ -n "$response" ]; then
            # Check if it's an error response
            local error=$(echo "$response" | jq -r '.error // empty' 2>/dev/null)
            if [ -n "$error" ]; then
                echo -e "${RED}Error: $error${NC}"
                ((failed++))
            else
                # Extract and display the result
                local content=$(echo "$response" | jq -r '.result.content[0].text // .result // .' 2>/dev/null)
                if [ -n "$content" ] && [ "$content" != "null" ]; then
                    echo "$content" | jq '.' 2>/dev/null || echo "$content"
                    echo -e "${GREEN}✓ Success${NC}"
                    ((passed++))
                else
                    echo "$response" | jq '.' 2>/dev/null || echo "$response"
                    ((passed++))
                fi
            fi
        else
            echo -e "${RED}✗ No response received${NC}"
            ((failed++))
        fi
    done

    # Cleanup
    rm -rf "$TEST_DIR"

    # Summary
    echo -e "\n${GREEN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                      Test Summary                             ║"
    echo "╠═══════════════════════════════════════════════════════════════╣"
    echo -e "║  ${GREEN}Passed: $passed${NC}                                                   ${GREEN}║"
    echo -e "║  ${RED}Failed: $failed${NC}                                                   ${GREEN}║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    if [ $failed -gt 0 ]; then
        exit 1
    fi
}

# Simple direct test mode (one tool at a time)
test_single() {
    local tool_name="$1"
    shift
    local args="${*:-{}}"

    echo -e "${YELLOW}Testing $tool_name with args: $args${NC}"

    local request='{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'$'\n'
    request+='{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"'"$tool_name"'","arguments":'"$args"'}}'

    echo -e "$request" | timeout 30 "$PYTHON" "$MCP_SERVER" --dry-run 2>/dev/null | grep '"id":1' | jq '.'
}

# List available tools
list_tools() {
    local request='{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'$'\n'
    request+='{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

    echo -e "${YELLOW}Available MCP Tools:${NC}\n"
    echo -e "$request" | timeout 30 "$PYTHON" "$MCP_SERVER" --dry-run 2>/dev/null | grep '"id":1' | jq -r '.result.tools[] | "  • \(.name): \(.description)"' 2>/dev/null
}

# Main
check_deps

case "${1:-}" in
    --list|-l)
        list_tools
        ;;
    --test|-t)
        shift
        test_single "$@"
        ;;
    --help|-h)
        echo "StoragePilot MCP Tool Tester"
        echo ""
        echo "Usage:"
        echo "  $0                  Run all tool tests"
        echo "  $0 --list           List available tools"
        echo "  $0 --test <tool> [args]  Test a single tool"
        echo ""
        echo "Examples:"
        echo "  $0 --test get_server_info"
        echo "  $0 --test scan_directory '{\"path\":\"~\"}'"
        ;;
    *)
        run_tests
        ;;
esac
