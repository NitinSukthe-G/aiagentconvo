"""The agent turn: session history in, Gemini + tool calls, final text out.

Only plain text turns (user message, final assistant reply) get persisted to
Redis session history — the back-and-forth of function calls within one turn
stays in memory for that turn only. This keeps stored history small and
avoids serializing raw SDK objects into JSON, at the cost of the model not
"remembering" exactly which tools it called on a previous turn (it does
remember the outcome, because that outcome is what got said in the text).
"""

import logging
from dataclasses import dataclass, field

from google.genai import types

from app.agent import llm
from app.agent.prompts import build_system_prompt
from app.agent.tools import PHONE_BOUND_TOOLS, TOOL_FUNCTIONS

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
HANDOFF_TOOL_NAME = "request_human_handoff"


BOOKING_TOOL_NAME = "book_appointment"


@dataclass
class AgentResult:
    text: str
    tool_calls: list[str] = field(default_factory=list)
    tool_results: dict[str, dict | list] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    handoff: bool = False
    handoff_reason: str | None = None
    # Set when the model wants to book — queue.py sends a Confirm/Cancel button
    # instead of executing the booking immediately. Holds doctor_id/date/time/patient_name.
    pending_booking: dict | None = None


def _history_to_contents(history: list[dict]) -> list[types.Content]:
    return [
        types.Content(role=turn["role"], parts=[types.Part(text=turn["content"])])
        for turn in history
    ]


def _dispatch_tool(name: str, args: dict, phone: str) -> dict | list:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        if name in PHONE_BOUND_TOOLS:
            return fn(**args, phone=phone)
        return fn(**args)
    except Exception as exc:  # a tool bug or bad Mongo state must not 500 the webhook
        logger.exception("Tool '%s' raised", name)
        return {"error": f"Tool failed: {exc}"}


def run_agent_turn(phone: str, user_text: str, history: list[dict], language: str | None) -> AgentResult:
    """`history` is the session history *before* this turn's user message."""
    system_prompt = build_system_prompt(language)
    contents = _history_to_contents(history)
    contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))

    result = AgentResult(text="")

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        response = llm.generate(contents, system_prompt)
        if response.usage_metadata:
            result.prompt_tokens += response.usage_metadata.prompt_token_count or 0
            result.completion_tokens += response.usage_metadata.candidates_token_count or 0

        calls = response.function_calls
        if not calls:
            result.text = response.text or "Sorry, I didn't understand that. Could you rephrase?"
            return result

        if response.candidates and response.candidates[0].content:
            contents.append(response.candidates[0].content)

        response_parts = []
        for call in calls:
            args = call.args or {}
            logger.info("Tool call round %d: %s(%s)", round_num, call.name, args)
            result.tool_calls.append(call.name)

            if call.name == HANDOFF_TOOL_NAME:
                result.handoff = True
                result.handoff_reason = args.get("reason", "User requested a human.")
                result.text = "Sure, connecting you with our staff — they'll message you shortly."
                return result

            if call.name == BOOKING_TOOL_NAME:
                # Don't book yet — the actual booking happens only after the user taps
                # Confirm on the button queue.py sends (see the pending_booking field).
                result.pending_booking = dict(args)
                tool_result = {"status": "awaiting_user_confirmation_via_button"}
            else:
                tool_result = _dispatch_tool(call.name, args, phone)
                result.tool_results[call.name] = tool_result

            response_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": tool_result})
            )

        contents.append(types.Content(role="user", parts=response_parts))

    result.text = "I'm having trouble completing that — could you try rephrasing, or ask to speak with staff?"
    logger.warning("Agent loop hit MAX_TOOL_ROUNDS for phone=%s", phone)
    return result
