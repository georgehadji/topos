"""MCP server entry point. Run with: uv run python -m topos.adapters.mcp

Implements the Model Context Protocol stdio transport.
"""

from __future__ import annotations

import json
import sys

from topos.mcp.server import handle_tool

# Minimal MCP stdio protocol implementation.
# Reads JSON-RPC requests from stdin, dispatches tool calls, writes responses.


def _respond(response: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def main() -> None:
    import asyncio

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _respond(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}
            )
            continue

        req_id = request.get("id", None)
        method = request.get("method", "")

        if method == "tools/list":
            _respond(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "search_problems",
                                "description": "Search mentions/problems with FTS and optional filters",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "text": {"type": "string"},
                                        "predicates": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "lat": {"type": "number"},
                                        "lon": {"type": "number"},
                                        "radius_km": {"type": "number"},
                                        "limit": {"type": "integer"},
                                    },
                                },
                            },
                            {
                                "name": "get_artifact",
                                "description": "Get artifact details with claims",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"id": {"type": "string"}},
                                    "required": ["id"],
                                },
                            },
                            {
                                "name": "approve_recommendation",
                                "description": "Approve a recommendation (human sign-off)",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "problem_id": {"type": "string"},
                                        "actor": {"type": "string"},
                                    },
                                    "required": ["problem_id"],
                                },
                            },
                        ]
                    },
                }
            )

        elif method == "tools/call":
            arguments = request.get("params", {}).get("arguments", {})
            tool_name = request.get("params", {}).get("name", "")
            result = asyncio.run(handle_tool(tool_name, arguments))
            _respond(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": result}]},
                }
            )

        elif method == "initialize":
            _respond(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "topos-mcp", "version": "0.1.0"},
                    },
                }
            )

        else:
            _respond({"jsonrpc": "2.0", "id": req_id, "result": None})


if __name__ == "__main__":
    main()
