"""Shared test fixtures: fake Redis and fake Mongo, swapped in via monkeypatch
so unit tests never need a real Redis server or MongoDB cluster.
"""

import fakeredis
import mongomock
import pytest


@pytest.fixture
def fake_redis(monkeypatch):
    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr("app.services.redis_client.redis_client", fake)
    monkeypatch.setattr("app.services.dedupe.redis_client", fake)
    monkeypatch.setattr("app.services.sessions.redis_client", fake)
    monkeypatch.setattr("app.api.webhook.redis_client", fake)
    return fake


@pytest.fixture
def fake_mongo(monkeypatch):
    client = mongomock.MongoClient()
    db = client["ai_agent_convo_test"]
    monkeypatch.setattr("app.services.mongo_client.doctors_col", db["doctors"])
    monkeypatch.setattr("app.services.mongo_client.slots_col", db["slots"])
    monkeypatch.setattr("app.services.mongo_client.appointments_col", db["appointments"])
    monkeypatch.setattr("app.services.mongo_client.conversations_col", db["conversations"])
    monkeypatch.setattr("app.services.bookings.doctors_col", db["doctors"])
    monkeypatch.setattr("app.services.bookings.slots_col", db["slots"])
    monkeypatch.setattr("app.services.bookings.appointments_col", db["appointments"])
    monkeypatch.setattr("app.services.costs.conversations_col", db["conversations"])
    return db
