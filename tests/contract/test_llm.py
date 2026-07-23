"""Contract test: LlmClient decorator stack against OpenRouter.

Requires TOPOS_LLM_API_KEY to be set in .env.
Mark: pytest -m contract
"""

from __future__ import annotations

import pytest

from topos.adapters.llm import build_llm_client
from topos.config import get_settings

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_llm_completion_returns_structured_output() -> None:
    """Send a simple prompt and verify we get a response back."""
    settings = get_settings()
    if settings.llm_api_key == "sk-or-v1-change-me" or not settings.llm_api_key:
        pytest.skip("TOPOS_LLM_API_KEY not set")

    client = build_llm_client()

    result = await client.complete(
        prompt='Reply with only a JSON object: {"answer": "hello"}',
        model=settings.llm_model,
        response_format={"type": "json_object"},
    )

    assert isinstance(result, dict)
    assert "choices" in result
    assert len(result["choices"]) > 0
    message = result["choices"][0].get("message", {})
    content = message.get("content", "")
    assert "hello" in content
