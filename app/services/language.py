"""Language detection with a per-session cache.

Re-classifying on every single message would double the Gemini calls per
turn for no real benefit — people don't switch language mid-conversation
often. Detection re-runs after `LANGUAGE_CACHE_TURNS` user messages, or
immediately for a brand new session.
"""

from app.agent import llm
from app.services import sessions


def resolve_language(phone: str, message_text: str) -> str:
    session = sessions.get_session(phone)
    if session["language"] is None or session["language_cache_remaining"] <= 0:
        language = llm.detect_language(message_text)
        sessions.set_language(phone, language)
        return language
    sessions.tick_language_cache(phone)
    return session["language"]
