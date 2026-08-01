"""Analyst Q&A HTTP endpoint — POST /api/analyst/ask.

Accepts natural-language questions about the Topos problem database,
grounds answers in exported Grok collections.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from topos.service.analyst import AnalystService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analyst", tags=["analyst"])


class AskRequest(BaseModel):
    question: str
    """Natural-language question about Topos problems and claims."""

    collection_ids: list[str] | None = None
    """Optional override for Grok collection IDs. Defaults to configured
    TOPOS_GROK_COLLECTION_IDS or env var."""


class AskResponse(BaseModel):
    answer: str
    citations: list[dict[str, str]]


_service: AnalystService | None = None


def _get_service() -> AnalystService:
    srv = _service
    if srv is None:
        srv = AnalystService()
    return srv


@router.post("/ask")
async def ask(body: AskRequest) -> AskResponse:
    """Submit an analytical question about the problem database.

    The answer is grounded in exported Topos data uploaded to a Grok
    collection. Citations reference specific problem IDs and source URLs.
    """
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")

    service = _get_service()
    try:
        result = await service.ask(
            question=body.question,
            collection_ids=body.collection_ids,
        )
        return AskResponse(
            answer=result.get("answer", ""),
            citations=result.get("citations", []),
        )
    except Exception as exc:
        logger.exception("Analyst query failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
