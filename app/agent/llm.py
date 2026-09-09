"""Thin wrapper around the google-genai client.

Function calling is done manually (automatic_function_calling disabled)
because the agent loop needs to persist history to Redis between webhook
calls and log every tool call — the SDK's automatic-calling mode hides both
of those inside one `generate_content` call.
"""

import logging

from google import genai
from google.genai import types

from app.agent.prompts import LANGUAGE_DETECTION_PROMPT
from app.agent.tools import TOOL_DECLARATIONS
from app.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _tools() -> list[types.Tool]:
    return [types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in TOOL_DECLARATIONS])]


def generate(contents: list[types.Content], system_prompt: str) -> types.GenerateContentResponse:
    return get_client().models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=_tools(),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.3,
        ),
    )


VALID_LANGUAGE_CODES = {"en", "hinglish", "te"}


def detect_language(message: str) -> str:
    """Best-effort classification; defaults to English on any ambiguity or error
    so a language-detection hiccup never blocks the actual reply.
    """
    try:
        response = get_client().models.generate_content(
            model=settings.gemini_model,
            contents=LANGUAGE_DETECTION_PROMPT.format(message=message),
            config=types.GenerateContentConfig(temperature=0.0),
        )
        code = (response.text or "").strip().lower()
        return code if code in VALID_LANGUAGE_CODES else "en"
    except Exception:
        logger.exception("Language detection failed, defaulting to English")
        return "en"
