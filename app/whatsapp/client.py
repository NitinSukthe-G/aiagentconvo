"""All outbound WhatsApp Cloud API calls, plus inbound signature verification.

Every send goes through `_post` so retry/backoff and logging live in one
place. Interactive message shapes (list / reply buttons) follow the Cloud
API's documented `interactive` object exactly:
https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-list-messages/
https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-reply-buttons-messages/
"""

import asyncio
import hashlib
import hmac
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"
MAX_SEND_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1, 2, 4)  # delay before attempt 2, 3, ...


def verify_signature(app_secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    """Check X-Hub-Signature-256. Meta signs the raw request body with the
    app secret (not the access token) using HMAC-SHA256, prefixed 'sha256='.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def _messages_url() -> str:
    return f"{GRAPH_BASE}/{settings.graph_api_version}/{settings.phone_number_id}/messages"


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.access_token}"}


async def _post(body: dict) -> httpx.Response | None:
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
            try:
                response = await client.post(_messages_url(), headers=_headers(), json=body)
                if response.status_code < 400:
                    return response
                logger.warning(
                    "WhatsApp send failed (attempt %d/%d): %s %s",
                    attempt, MAX_SEND_ATTEMPTS, response.status_code, response.text,
                )
                last_error = RuntimeError(f"{response.status_code}: {response.text}")
            except httpx.HTTPError as exc:
                logger.warning("WhatsApp send error (attempt %d/%d): %s", attempt, MAX_SEND_ATTEMPTS, exc)
                last_error = exc

            if attempt < MAX_SEND_ATTEMPTS:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt - 1])

    logger.error("WhatsApp send failed after %d attempts: %s", MAX_SEND_ATTEMPTS, last_error)
    return None


async def send_text(to: str, body: str) -> httpx.Response | None:
    return await _post({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": body},
    })


async def send_buttons(to: str, body_text: str, buttons: list[dict], footer: str | None = None) -> httpx.Response | None:
    """buttons: up to 3 of [{"id": "...", "title": "..."}] (title <= 20 chars)."""
    action = {
        "buttons": [
            {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
            for b in buttons[:3]
        ]
    }
    interactive = {"type": "button", "body": {"text": body_text}, "action": action}
    if footer:
        interactive["footer"] = {"text": footer}
    return await _post({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    })


async def send_list(
    to: str,
    body_text: str,
    button_text: str,
    sections: list[dict],
    header: str | None = None,
) -> httpx.Response | None:
    """sections: [{"title": "...", "rows": [{"id","title","description"}]}]."""
    interactive = {
        "type": "list",
        "body": {"text": body_text},
        "action": {"button": button_text, "sections": sections},
    }
    if header:
        interactive["header"] = {"type": "text", "text": header}
    return await _post({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    })


async def mark_as_read(message_id: str) -> httpx.Response | None:
    return await _post({
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    })
