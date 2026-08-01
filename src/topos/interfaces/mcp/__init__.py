"""MCP protocol handler — JSON-RPC 2.0 for Model Context Protocol.

Implements the MCP protocol that Grok's Remote MCP Tools feature connects to.
Supports ``initialize``, ``tools/list``, and ``tools/call`` methods.

For single-response methods (initialize, tools/list, tools/call) we return
plain JSON. For streaming responses, the client can use SSE — xAI's MCP
client supports both.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── Protocol constants ───────────────────────────────────────────────────────

MCP_VERSION = "2024-11-05"
"""MCP protocol version implemented."""

SERVER_NAME = "topos-mcp"
SERVER_VERSION = "0.1.0"


def _jsonrpc_error(id: Any, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response."""
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _jsonrpc_result(id: Any, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response."""
    return {"jsonrpc": "2.0", "id": id, "result": result}


# ── Tool registry ────────────────────────────────────────────────────────────

_registered_tools: dict[str, dict[str, Any]] = {}
_tool_handlers: dict[str, Any] = {}

ToolHandler = Callable[..., Awaitable[Any]]
"""Signature for registered MCP tool handlers."""


def register_tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
) -> Callable[[ToolHandler], ToolHandler]:
    """Decorator to register a tool handler.

    Usage::

        @register_tool("search_problems", "Search problems by text and location", {...})
        async def search_problems(args: dict) -> list[dict]: ...

    Returns a decorator that registers the function. The decorator preserves
    the function's type signature.
    """

    def decorator(func: ToolHandler) -> ToolHandler:
        _registered_tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }
        _tool_handlers[name] = func
        return func

    return decorator


async def dispatch_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Call a registered tool handler by name."""
    handler = _tool_handlers.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    return await handler(arguments)


# ── Router ───────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.post("")
async def mcp_handler(request: Request) -> JSONResponse:
    """MCP endpoint — receives JSON-RPC requests and returns JSON responses.

    xAI's Remote MCP connects to this URL with POST requests containing
    JSON-RPC messages. For single-response methods we return JSON directly;
    streaming methods use SSE (not yet implemented).
    """
    # Auth check
    auth_header = request.headers.get("authorization", "")
    expected = request.app.state.mcp_api_key if hasattr(request.app.state, "mcp_api_key") else ""

    if expected:
        token = auth_header.removeprefix("Bearer ").strip()
        if not token or token != expected:
            raise HTTPException(status_code=401, detail="Invalid MCP API key")

    body = await request.json()
    jsonrpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    # ── initialize ───────────────────────────────────────────────────────────
    if method == "initialize":
        return JSONResponse(
            content=_jsonrpc_result(
                jsonrpc_id,
                {
                    "protocolVersion": MCP_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
        )

    # ── tools/list ────────────────────────────────────────────────────────────
    if method == "tools/list":
        return JSONResponse(
            content=_jsonrpc_result(jsonrpc_id, {"tools": list(_registered_tools.values())})
        )

    # ── tools/call ────────────────────────────────────────────────────────────
    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in _registered_tools:
            return JSONResponse(
                content=_jsonrpc_error(jsonrpc_id, -32601, f"Tool not found: {tool_name}"),
                status_code=200,
            )

        try:
            output = await dispatch_tool(tool_name, arguments)
        except Exception as exc:
            logger.exception("MCP tool call failed: %s", tool_name)
            return JSONResponse(
                content=_jsonrpc_error(jsonrpc_id, -32603, str(exc)),
                status_code=200,
            )

        return JSONResponse(
            content=_jsonrpc_result(
                jsonrpc_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(output, default=str, ensure_ascii=False),
                        }
                    ],
                    "isError": False,
                },
            )
        )

    # ── Unknown method ────────────────────────────────────────────────────────
    return JSONResponse(
        content=_jsonrpc_error(jsonrpc_id, -32601, f"Method not found: {method}"),
        status_code=200,
    )
