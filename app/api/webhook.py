"""GET verification + POST receive for the WhatsApp Cloud API webhook.

POST does the minimum possible work before returning 200: verify the
signature, parse, push each message onto the Redis queue. Everything else
(dedupe, session, the agent loop, sending the reply) happens in
`workers/queue.py` — Meta retries a slow or non-200 webhook, so this handler
must never block on Gemini, Mongo, or an outgoing WhatsApp call.
"""

import json
import logging

from fastapi import APIRouter, Query, Request, Response

from app.config import settings
from app.services.redis_client import redis_client
from app.whatsapp.client import verify_signature
from app.whatsapp.parser import parse_webhook_payload

logger = logging.getLogger(__name__)
router = APIRouter()

INCOMING_QUEUE_KEY = "incoming_queue"


@router.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_signature(settings.app_secret, raw_body, signature):
        logger.warning("Rejected webhook POST: bad signature")
        return Response(status_code=403)

    payload = json.loads(raw_body)
    messages = parse_webhook_payload(payload)

    for message in messages:
        redis_client.lpush(INCOMING_QUEUE_KEY, message.model_dump_json())

    return Response(status_code=200)
