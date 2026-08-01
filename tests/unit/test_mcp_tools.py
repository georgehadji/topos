"""Unit tests for MCP protocol handler and tool dispatch."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from topos.interfaces.http.app import app


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client with MCP key set."""
    app.state.mcp_api_key = "test-mcp-key"
    return TestClient(app)


def test_mcp_initialize(client: TestClient) -> None:
    """POST /mcp with initialize returns server capabilities."""
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers={"Authorization": "Bearer test-mcp-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    result = data["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "topos-mcp"


def test_mcp_tools_list(client: TestClient) -> None:
    """POST /mcp with tools/list returns registered tool definitions."""
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={"Authorization": "Bearer test-mcp-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    tools = data["result"]["tools"]
    # Should have at least the 5 registered tools
    tool_names = {t["name"] for t in tools}
    assert "search_problems" in tool_names
    assert "get_problem_detail" in tool_names
    assert "get_pipeline_status" in tool_names
    assert "list_sources" in tool_names
    assert "get_scoring_breakdown" in tool_names


def test_mcp_unknown_method(client: TestClient) -> None:
    """Unknown method returns JSON-RPC error."""
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "bogus", "params": {}},
        headers={"Authorization": "Bearer test-mcp-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == -32601


def test_mcp_unknown_tool(client: TestClient) -> None:
    """Calling an unknown tool returns a tool-not-found error."""
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        },
        headers={"Authorization": "Bearer test-mcp-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert "Tool not found" in data["error"]["message"]


def test_mcp_auth_required(client: TestClient) -> None:
    """Missing or invalid auth header returns 401."""
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 5, "method": "initialize", "params": {}},
    )
    assert resp.status_code == 401

    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 5, "method": "initialize", "params": {}},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_mcp_no_auth_when_key_empty(client: TestClient) -> None:
    """When MCP API key is empty, auth is not required."""
    app.state.mcp_api_key = ""
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 6, "method": "initialize", "params": {}},
    )
    assert resp.status_code == 200
    app.state.mcp_api_key = "test-mcp-key"  # reset
