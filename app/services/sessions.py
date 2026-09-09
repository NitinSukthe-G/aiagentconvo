"""Per-phone-number conversation state in Redis.

One JSON blob per phone under `session:{phone}`, TTL refreshed on every
write. A JSON blob (rather than a Redis hash) is the boring choice here
because `history` is a list of dicts and everything else is scalar — hashes
buy nothing extra for a value this small and this short-lived.
"""

import json
from typing import Literal, TypedDict

from app.services.redis_client import redis_client

SESSION_TTL_SECONDS = 24 * 60 * 60
MAX_HISTORY_TURNS = 20
LANGUAGE_CACHE_TURNS = 10  # re-run language detection after this many user turns

Role = Literal["user", "model"]


class HistoryTurn(TypedDict):
    role: Role
    content: str


class SessionState(TypedDict):
    history: list[HistoryTurn]
    language: str | None  # "en" | "hinglish" | "te"
    language_cache_remaining: int
    handoff: bool
    pending_booking: dict | None  # {doctor_id, date, time, patient_name} awaiting a button tap


def _key(phone: str) -> str:
    return f"session:{phone}"


def _default() -> SessionState:
    return {
        "history": [],
        "language": None,
        "language_cache_remaining": 0,
        "handoff": False,
        "pending_booking": None,
    }


def get_session(phone: str) -> SessionState:
    raw = redis_client.get(_key(phone))
    if raw is None:
        return _default()
    data = json.loads(raw)
    return {**_default(), **data}  # tolerate old sessions missing newer fields


def save_session(phone: str, session: SessionState) -> None:
    redis_client.set(_key(phone), json.dumps(session), ex=SESSION_TTL_SECONDS)


def append_turn(phone: str, role: Role, content: str) -> SessionState:
    session = get_session(phone)
    session["history"].append({"role": role, "content": content})
    session["history"] = session["history"][-MAX_HISTORY_TURNS:]
    save_session(phone, session)
    return session


def set_language(phone: str, language: str) -> None:
    session = get_session(phone)
    session["language"] = language
    session["language_cache_remaining"] = LANGUAGE_CACHE_TURNS
    save_session(phone, session)


def tick_language_cache(phone: str) -> SessionState:
    """Call once per incoming user turn. Returns the session; `language` is
    None (or `language_cache_remaining` hits 0) when detection should re-run.
    """
    session = get_session(phone)
    if session["language_cache_remaining"] > 0:
        session["language_cache_remaining"] -= 1
        save_session(phone, session)
    return session


def set_handoff(phone: str, handoff: bool) -> None:
    session = get_session(phone)
    session["handoff"] = handoff
    save_session(phone, session)


def set_pending_booking(phone: str, booking: dict | None) -> None:
    session = get_session(phone)
    session["pending_booking"] = booking
    save_session(phone, session)
