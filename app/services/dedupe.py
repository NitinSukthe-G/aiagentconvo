"""Drop WhatsApp messages we've already processed.

Meta retries the webhook delivery if it doesn't get a fast 200, and it can
also occasionally redeliver. `message_id` (the wamid) is unique per message,
so `SETNX` on it is a correct dedupe key: the first writer wins, everyone
else sees the key already exists and skips.
"""

from app.services.redis_client import redis_client

SEEN_TTL_SECONDS = 24 * 60 * 60


def mark_seen_if_new(message_id: str) -> bool:
    """Returns True the first time this message_id is seen, False on a repeat."""
    return bool(redis_client.set(f"msg:{message_id}", "1", nx=True, ex=SEEN_TTL_SECONDS))
