"""Webhook system: event-based HTTP callbacks.

Sends POST requests to configured webhook URLs when events occur.
Events: artifact.ingested, mention.created, recommendation.approved,
recommendation.exported.

Webhooks are stored in a simple JSON file for now (no DB table).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/webhooks")

_WEBHOOKS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "webhooks.json")


def _load_webhooks() -> list[dict[str, Any]]:
    if not os.path.exists(_WEBHOOKS_FILE):
        return []
    with open(_WEBHOOKS_FILE) as f:
        result: Any = json.load(f)
    return result if isinstance(result, list) else []


def _save_webhooks(webhooks: list[dict[str, Any]]) -> None:
    with open(_WEBHOOKS_FILE, "w") as f:
        json.dump(webhooks, f, indent=2)


@router.get("")
async def list_webhooks() -> list[dict[str, Any]]:
    """List all registered webhooks."""
    return _load_webhooks()


@router.post("")
async def register_webhook(
    url: str,
    events: list[str] | None = None,
    secret: str = "",
) -> dict[str, object]:
    """Register a new webhook.

    *url* — the callback URL
    *events* — list of event types to subscribe to (default: all)
    *secret* — HMAC secret for signature verification
    """
    webhooks = _load_webhooks()
    webhooks.append({
        "id": hashlib.sha256(url.encode()).hexdigest()[:12],
        "url": url,
        "events": events or ["*"],
        "secret": secret,
        "created_at": datetime.now(UTC).isoformat(),
    })
    _save_webhooks(webhooks)
    return {"status": "registered", "url": url}


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str) -> dict[str, object]:
    """Remove a webhook by ID."""
    webhooks = _load_webhooks()
    new_webhooks = [w for w in webhooks if w["id"] != webhook_id]
    if len(new_webhooks) == len(webhooks):
        raise HTTPException(status_code=404, detail="Webhook not found")
    _save_webhooks(new_webhooks)
    return {"status": "deleted"}


async def dispatch(event: str, payload: dict[str, Any]) -> None:
    """Dispatch an event to all matching webhooks.

    Called by services when events occur.
    """
    webhooks = _load_webhooks()
    body = json.dumps({
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": payload,
    })

    async with httpx.AsyncClient(timeout=10) as client:
        for wh in webhooks:
            if wh.get("events", ["*"])[0] != "*" and event not in wh.get("events", []):
                continue

            headers = {"Content-Type": "application/json"}
            if wh.get("secret"):
                sig = hmac.new(
                    wh["secret"].encode(),
                    body.encode(),
                    hashlib.sha256,
                ).hexdigest()
                headers["X-Webhook-Signature"] = sig

            try:
                await client.post(wh["url"], content=body, headers=headers)
            except httpx.RequestError:
                pass  # Fire and forget — webhook failures are non-fatal
