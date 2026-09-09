"""Webhook POST: signature gate + push-to-queue behaviour.

Dedupe deliberately does NOT happen here — the webhook must return fast, so
every valid, well-signed delivery gets queued regardless of whether it's a
Meta retry. `workers/queue.py` is where duplicates get dropped
(see test_worker.py).
"""

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)

TEXT_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [{
        "id": "WABA_ID",
        "changes": [{
            "value": {"messages": [{"id": "wamid.1", "from": "911234567890", "timestamp": "1000", "type": "text", "text": {"body": "hi"}}]},
            "field": "messages",
        }],
    }],
}


def _signed_post(payload: dict):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(settings.app_secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=body, headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"})


def test_valid_signature_queues_message(fake_redis):
    response = _signed_post(TEXT_PAYLOAD)
    assert response.status_code == 200
    assert fake_redis.llen("incoming_queue") == 1


def test_invalid_signature_is_rejected_and_nothing_queued(fake_redis):
    body = json.dumps(TEXT_PAYLOAD).encode()
    response = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"})
    assert response.status_code == 403
    assert fake_redis.llen("incoming_queue") == 0


def test_duplicate_delivery_is_queued_twice_here_but_worker_drops_the_repeat(fake_redis):
    """Confirms the boundary: webhook always queues; the repeat is only ever
    caught downstream. See test_worker.test_duplicate_message_is_processed_once.
    """
    _signed_post(TEXT_PAYLOAD)
    _signed_post(TEXT_PAYLOAD)
    assert fake_redis.llen("incoming_queue") == 2
