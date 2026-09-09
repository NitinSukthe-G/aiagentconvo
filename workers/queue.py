"""Background worker: BRPOP the incoming-message queue, run the pipeline.

Run with: `uv run python -m workers.queue`

One message at a time, synchronously per message (`asyncio.run` per pop) —
this bot's traffic is a single clinic's WhatsApp number, not a chat platform;
correctness and readability win over throughput here. A crash mid-message
loses nothing: the message that was being processed is already off the
Redis list (BRPOP is destructive), but WhatsApp will have retried the
webhook delivery already if we hadn't returned 200 in time, and dedupe.py
prevents double-processing.
"""

import asyncio
import logging

from app.agent import loop
from app.config import settings
from app.models.message import Message
from app.services import bookings, costs, dedupe, handoff, language, sessions
from app.services.redis_client import redis_client
from app.whatsapp import client as whatsapp
from app.agent.prompts import ui_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

INCOMING_QUEUE_KEY = "incoming_queue"
CONFIRM_BOOKING_ID = "confirm_booking"
CANCEL_BOOKING_ID = "cancel_booking"


async def handle_booking_decision(phone: str, confirmed: bool, session: sessions.SessionState) -> None:
    pending = session["pending_booking"]
    if pending is None:
        await whatsapp.send_text(phone, "There's nothing pending to confirm right now.")
        return

    sessions.set_pending_booking(phone, None)

    if not confirmed:
        reply = "No problem — let me know if you'd like a different time."
    else:
        outcome = bookings.book_appointment(
            pending["doctor_id"], pending["date"], pending["time"], pending["patient_name"], phone
        )
        if outcome["ok"]:
            reply = (
                f"You're booked! {outcome['doctor_name']} on {outcome['date']} at {outcome['time']}. "
                f"Consultation fee: ₹{outcome['fee']}."
            )
        else:
            reply = "Sorry, that slot was just taken. Would you like to see other available times?"

    sessions.append_turn(phone, "user", f"[tapped {'Confirm' if confirmed else 'Cancel'}]")
    sessions.append_turn(phone, "model", reply)
    await whatsapp.send_text(phone, reply)


async def send_agent_reply(phone: str, result: loop.AgentResult, language_code: str | None) -> None:
    if result.pending_booking is not None:
        sessions.set_pending_booking(phone, result.pending_booking)
        await whatsapp.send_buttons(
            phone,
            result.text,
            [
                {"id": CONFIRM_BOOKING_ID, "title": ui_text(language_code, "confirm")},
                {"id": CANCEL_BOOKING_ID, "title": ui_text(language_code, "cancel")},
            ],
        )
        return

    if "list_doctors" in result.tool_results:
        doctors = result.tool_results["list_doctors"]
        rows = [
            {"id": d["doctor_id"], "title": d["name"][:24], "description": f"{d['speciality']} — ₹{d['fee']}"}
            for d in doctors
            if isinstance(d, dict) and "doctor_id" in d
        ]
        if rows:
            await whatsapp.send_list(
                phone, result.text, ui_text(language_code, "view_doctors"),
                [{"title": ui_text(language_code, "choose_doctor"), "rows": rows}],
            )
            return

    if "list_available_slots" in result.tool_results:
        slots = result.tool_results["list_available_slots"]
        rows = [{"id": s["time"], "title": s["time"]} for s in slots if isinstance(s, dict) and "time" in s]
        if rows:
            await whatsapp.send_list(
                phone, result.text, ui_text(language_code, "view_times"),
                [{"title": ui_text(language_code, "choose_time"), "rows": rows}],
            )
            return

    await whatsapp.send_text(phone, result.text)


async def process_message(raw_json: str) -> None:
    message = Message.model_validate_json(raw_json)

    if not dedupe.mark_seen_if_new(message.message_id):
        logger.info("Skipping duplicate message_id=%s", message.message_id)
        return

    phone = message.from_number
    session = sessions.get_session(phone)

    if session["handoff"]:
        logger.info("Handoff active for %s — storing message, not replying", phone)
        sessions.append_turn(phone, "user", message.text or message.title or "")
        return

    if message.type == "unknown":
        await whatsapp.send_text(phone, "Sorry, I can only understand text messages and menu selections right now.")
        return

    if message.type == "button_reply" and message.text in (CONFIRM_BOOKING_ID, CANCEL_BOOKING_ID):
        await handle_booking_decision(phone, message.text == CONFIRM_BOOKING_ID, session)
        return

    user_text = message.text if message.type == "text" else (message.title or message.text)

    if message.type == "text":
        language_code = language.resolve_language(phone, user_text)
    else:
        language_code = session["language"]

    result = loop.run_agent_turn(phone, user_text, session["history"], language_code)

    sessions.append_turn(phone, "user", user_text)
    sessions.append_turn(phone, "model", result.text)
    costs.record_usage(phone, settings.gemini_model, result.prompt_tokens, result.completion_tokens)

    if result.handoff:
        await handoff.trigger_handoff(phone, result.handoff_reason or "No reason given.")
        await whatsapp.send_text(phone, result.text)
    else:
        await send_agent_reply(phone, result, language_code)

    await whatsapp.mark_as_read(message.message_id)


def run_forever() -> None:
    logger.info("Worker started, waiting on '%s'", INCOMING_QUEUE_KEY)
    while True:
        item = redis_client.brpop([INCOMING_QUEUE_KEY], timeout=5)
        if item is None:
            continue
        _key, raw_json = item
        try:
            asyncio.run(process_message(raw_json))
        except Exception:
            logger.exception("Failed to process message: %s", raw_json)


if __name__ == "__main__":
    run_forever()
