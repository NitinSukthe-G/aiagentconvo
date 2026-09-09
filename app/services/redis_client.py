"""One Redis connection, shared by sessions/dedupe/queue.

`redis-py`'s `Redis.from_url` returns a lazily-connecting client that's safe
to share across async request handlers, so a single module-level instance is
enough — no pool-sizing decisions to make for this traffic volume.
"""

import redis

from app.config import settings

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
