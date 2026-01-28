"""
StoragePilot AI Copilot API
===========================

Provides an AI assistant that can:
- Answer questions about storage and cleanup
- Call StoragePilot tools to analyze directories
- Provide recommendations based on scan results

Supports multiple LLM providers:
- Ollama (local, default)
- OpenAI
- Anthropic
"""

import os
import json
import asyncio
from typing import Optional, List, Dict, Any, AsyncGenerator
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from tools.terminal import TerminalTools
from tools.classifier import FileClassifier

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    message: str
    scan_id: Optional[str] = None
    history: List[ChatMessage] = Field(default_factory=list)
    stream: bool = False


class ChatResponse(BaseModel):
    reply: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)


class ToolResult(BaseModel):
    tool: str
    result: Any


# -----------------------------------------------------------------------------
# Tool Definitions for the LLM
# -----------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "scan_directory",
            "description": "Scan a directory and return disk usage breakdown. Shows total size and per-item sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to scan (e.g., '~/Downloads', '/home/user')"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_large_files",
            "description": "Find files larger than a specified size in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to search"
                    },
                    "min_size": {
                        "type": "string",
                        "description": "Minimum file size (e.g., '100M', '1G'). Default: '100M'"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_old_files",
            "description": "Find files not modified within a specified number of days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to search"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days since last modification. Default: 90"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_developer_artifacts",
            "description": "Find developer artifacts like node_modules, .venv, __pycache__ that can be safely cleaned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_path": {
                        "type": "string",
                        "description": "Workspace directory to search for artifacts"
                    }
                },
                "required": ["workspace_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_overview",
            "description": "Get overall system storage information including disk usage and largest directories.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_docker_usage",
            "description": "Get Docker storage usage breakdown including images, containers, volumes.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "classify_files",
            "description": "Classify files in a directory by type (images, documents, archives, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "Directory containing files to classify"
                    }
                },
                "required": ["directory_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_duplicates",
            "description": "Find duplicate files in a directory using content hashing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "Directory to scan for duplicates"
                    }
                },
                "required": ["directory_path"]
            }
        }
    },
]

# System prompt for the copilot
SYSTEM_PROMPT = """You are StoragePilot Copilot, an AI assistant specialized in storage management and cleanup.

Your capabilities:
- Analyze disk usage and find space hogs
- Identify large, old, or duplicate files
- Find developer artifacts (node_modules, .venv, etc.) that can be cleaned
- Classify files and suggest organization
- Check Docker storage usage

Guidelines:
1. Always explain what you're doing before calling tools
2. Summarize tool results in a user-friendly way
3. Suggest safe cleanup actions but NEVER delete without explicit approval
4. When uncertain, ask clarifying questions
5. Use metric units (GB, MB) for file sizes

You have access to tools to analyze the user's storage. Use them proactively when relevant."""


# -----------------------------------------------------------------------------
# Tool Executor
# -----------------------------------------------------------------------------

class ToolExecutor:
    """Executes StoragePilot tools based on LLM function calls."""

    def __init__(self, dry_run: bool = True):
        self.terminal = TerminalTools(dry_run=dry_run)
        self.classifier = FileClassifier()

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return results."""
        try:
            if tool_name == "scan_directory":
                path = os.path.expanduser(arguments.get("path", "~"))
                return self.terminal.get_disk_usage(path)

            elif tool_name == "find_large_files":
                path = os.path.expanduser(arguments.get("path", "~"))
                min_size = arguments.get("min_size", "100M")
                files = self.terminal.find_files(path, min_size=min_size, file_type="f")
                return {
                    "path": path,
                    "min_size": min_size,
                    "count": len(files),
                    "files": files[:20]  # Limit for response size
                }

            elif tool_name == "find_old_files":
                path = os.path.expanduser(arguments.get("path", "~"))
                days = arguments.get("days", 90)
                files = self.terminal.find_files(path, modified_days=days, file_type="f")
                return {
                    "path": path,
                    "days": days,
                    "count": len(files),
                    "files": files[:20]
                }

            elif tool_name == "find_developer_artifacts":
                workspace = os.path.expanduser(arguments.get("workspace_path", "~"))
                return self._find_dev_artifacts(workspace)

            elif tool_name == "get_system_overview":
                return self.terminal.get_system_overview()

            elif tool_name == "get_docker_usage":
                return self.terminal.get_docker_usage()

            elif tool_name == "classify_files":
                dir_path = os.path.expanduser(arguments.get("directory_path", "~"))
                classifications = self.classifier.classify_directory(dir_path)
                # Summarize by category
                summary = {}
                for c in classifications:
                    cat = getattr(c, "category", "other")
                    summary[cat] = summary.get(cat, 0) + 1
                return {
                    "directory": dir_path,
                    "total_files": len(classifications),
                    "by_category": summary
                }

            elif tool_name == "detect_duplicates":
                dir_path = os.path.expanduser(arguments.get("directory_path", "~"))
                return self._detect_duplicates(dir_path)

            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            return {"error": str(e)}

    def _find_dev_artifacts(self, workspace: str) -> Dict[str, Any]:
        """Find developer artifacts that can be cleaned."""
        patterns = ["node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target"]
        results = {"workspace": workspace, "artifacts": [], "total_size": "0 B"}
        total_bytes = 0

        for pattern in patterns:
            found = self.terminal.find_files(workspace, pattern=pattern, file_type="d", max_depth=4)
            for item in found[:5]:  # Limit per pattern
                results["artifacts"].append({
                    "type": pattern,
                    "path": item.get("path", ""),
                    "size": item.get("size_human", "N/A")
                })

        return results

    def _detect_duplicates(self, directory: str) -> Dict[str, Any]:
        """Find duplicate files using MD5 hashing."""
        import hashlib
        from collections import defaultdict

        hash_map = defaultdict(list)
        path = Path(directory)

        if not path.exists():
            return {"error": f"Directory not found: {directory}"}

        for file_path in path.rglob("*"):
            if file_path.is_file():
                try:
                    hasher = hashlib.md5()
                    with open(file_path, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            hasher.update(chunk)
                    hash_map[hasher.hexdigest()].append(str(file_path))
                except (PermissionError, OSError):
                    pass

        duplicates = {h: files for h, files in hash_map.items() if len(files) > 1}

        return {
            "directory": directory,
            "duplicate_groups": len(duplicates),
            "duplicates": dict(list(duplicates.items())[:10])  # Limit output
        }


# -----------------------------------------------------------------------------
# LLM Client
# -----------------------------------------------------------------------------

async def call_llm(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict]] = None,
    stream: bool = False
) -> Dict[str, Any]:
    """Call the LLM with optional tool definitions."""
    import httpx

    # Get provider config from environment
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Choose provider
    if openai_key and openai_key != "ollama":
        base_url = "https://api.openai.com/v1"
        api_key = openai_key
        model = openai_model
    else:
        base_url = ollama_base
        api_key = "ollama"
        model = ollama_model

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "stream": stream,
    }

    # Add tools if provided (not all models support this)
    if tools and openai_key and openai_key != "ollama":
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"LLM API error: {response.text}"
            )

        return response.json()


# -----------------------------------------------------------------------------
# Chat Endpoint
# -----------------------------------------------------------------------------

@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """
    Chat with the StoragePilot Copilot.

    The copilot can call tools to analyze storage and provide recommendations.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    # Build message history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history
    for msg in req.history[-10:]:  # Keep last 10 messages for context
        messages.append({"role": msg.role, "content": msg.content})

    # Add current message
    messages.append({"role": "user", "content": req.message})

    # Initialize tool executor
    executor = ToolExecutor(dry_run=True)
    tool_calls_made = []

    # Check if we should use tools (only with OpenAI for now)
    openai_key = os.getenv("OPENAI_API_KEY")
    use_tools = openai_key and openai_key != "ollama"

    try:
        # First LLM call
        response = await call_llm(
            messages=messages,
            tools=TOOL_DEFINITIONS if use_tools else None
        )

        choice = response["choices"][0]
        message = choice["message"]

        # Handle tool calls if present
        if use_tools and message.get("tool_calls"):
            tool_results = []

            for tool_call in message["tool_calls"]:
                func = tool_call["function"]
                tool_name = func["name"]
                arguments = json.loads(func.get("arguments", "{}"))

                # Execute the tool
                result = executor.execute(tool_name, arguments)
                tool_calls_made.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "result_summary": str(result)[:200]
                })

                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result)
                })

            # Add assistant message with tool calls
            messages.append(message)
            # Add tool results
            messages.extend(tool_results)

            # Second LLM call to generate response with tool results
            response = await call_llm(messages=messages)
            message = response["choices"][0]["message"]

        reply = message.get("content", "I apologize, I couldn't generate a response.")

        return ChatResponse(reply=reply, tool_calls=tool_calls_made)

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"LLM service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """
    Stream chat responses (for real-time typing effect).
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    async def generate() -> AsyncGenerator[str, None]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        for msg in req.history[-10:]:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": req.message})

        try:
            # For streaming, we use a simpler approach without tool calling
            import httpx

            ollama_base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
            ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
            openai_key = os.getenv("OPENAI_API_KEY")

            if openai_key and openai_key != "ollama":
                base_url = "https://api.openai.com/v1"
                api_key = openai_key
                model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            else:
                base_url = ollama_base
                api_key = "ollama"
                model = ollama_model

            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.3,
                        "stream": True,
                    },
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                content = chunk["choices"][0]["delta"].get("content", "")
                                if content:
                                    yield f"data: {json.dumps({'content': content})}\n\n"
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/tools")
async def list_tools() -> List[Dict[str, Any]]:
    """List available tools the copilot can use."""
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"]["description"]
        }
        for t in TOOL_DEFINITIONS
    ]


@router.post("/execute-tool")
async def execute_tool(tool_name: str, arguments: Dict[str, Any] = {}) -> Dict[str, Any]:
    """Directly execute a tool (for testing/debugging)."""
    executor = ToolExecutor(dry_run=True)
    result = executor.execute(tool_name, arguments)
    return {"tool": tool_name, "arguments": arguments, "result": result}
