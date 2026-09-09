"""Worker pipeline: dedupe, handoff silence, and the plain-text happy path.

Gemini and the real WhatsApp send are mocked out — this tests the
orchestration in workers/queue.py, not the model or the network.
"""

from unittest.mock import AsyncMock

import pytest

from app.agent.loop import AgentResult
from app.services import sessions
from workers import queue as worker


@pytest.fixture(autouse=True)
def mock_whatsapp_and_llm(monkeypatch):
    monkeypatch.setattr(worker.whatsapp, "send_text", AsyncMock(return_value=None))
    monkeypatch.setattr(worker.whatsapp, "send_buttons", AsyncMock(return_value=None))
    monkeypatch.setattr(worker.whatsapp, "send_list", AsyncMock(return_value=None))
    monkeypatch.setattr(worker.whatsapp, "mark_as_read", AsyncMock(return_value=None))
    monkeypatch.setattr(worker.language, "resolve_language", lambda phone, text: "en")


def _text_message_json(message_id="wamid.1", text="hi"):
    return f'{{"message_id": "{message_id}", "from_number": "911234567890", "timestamp": 1000, "type": "text", "text": "{text}"}}'


async def test_happy_path_sends_one_reply(fake_redis, fake_mongo, monkeypatch):
    monkeypatch.setattr(
        worker.loop, "run_agent_turn",
        lambda phone, text, history, lang: AgentResult(text="Our timings are 9-1 and 5-9.", prompt_tokens=10, completion_tokens=5),
    )

    await worker.process_message(_text_message_json())

    worker.whatsapp.send_text.assert_awaited_once_with("911234567890", "Our timings are 9-1 and 5-9.")
    worker.whatsapp.mark_as_read.assert_awaited_once()


async def test_duplicate_message_is_processed_once(fake_redis, fake_mongo, monkeypatch):
    monkeypatch.setattr(worker.loop, "run_agent_turn", lambda *a, **kw: AgentResult(text="reply"))

    raw = _text_message_json(message_id="wamid.dup")
    await worker.process_message(raw)
    await worker.process_message(raw)  # simulates Meta redelivering the same webhook

    assert worker.whatsapp.send_text.await_count == 1


async def test_handoff_silences_further_replies(fake_redis, fake_mongo):
    phone = "911234567890"
    sessions.set_handoff(phone, True)

    await worker.process_message(_text_message_json())

    worker.whatsapp.send_text.assert_not_awaited()
    session = sessions.get_session(phone)
    assert session["history"][-1]["content"] == "hi"  # message stored for staff to review


async def test_unknown_message_type_gets_canned_reply(fake_redis, fake_mongo):
    raw = '{"message_id": "wamid.2", "from_number": "911234567890", "timestamp": 1000, "type": "unknown", "text": ""}'
    await worker.process_message(raw)
    worker.whatsapp.send_text.assert_awaited_once()
    assert "menu selections" in worker.whatsapp.send_text.await_args.args[1]


async def test_booking_pending_sends_confirm_buttons(fake_redis, fake_mongo, monkeypatch):
    booking_args = {"doctor_id": "dr_rao", "date": "2026-09-10", "time": "09:00", "patient_name": "Asha"}
    monkeypatch.setattr(
        worker.loop, "run_agent_turn",
        lambda *a, **kw: AgentResult(text="Ready to confirm?", pending_booking=booking_args),
    )

    await worker.process_message(_text_message_json(text="book dr rao tomorrow 9am for asha"))

    worker.whatsapp.send_buttons.assert_awaited_once()
    assert sessions.get_session("911234567890")["pending_booking"] == booking_args
    worker.whatsapp.send_text.assert_not_awaited()  # buttons sent instead of plain text


async def test_confirm_button_books_the_pending_slot(fake_redis, fake_mongo):
    from app.services import bookings

    phone = "911234567890"
    fake_mongo["doctors"].insert_one({"doctor_id": "dr_rao", "name": "Dr. Rao", "speciality": "General Medicine", "fee": 500})
    fake_mongo["slots"].insert_one({"doctor_id": "dr_rao", "date": "2026-09-10", "time": "09:00", "booked": False})
    sessions.set_pending_booking(phone, {"doctor_id": "dr_rao", "date": "2026-09-10", "time": "09:00", "patient_name": "Asha"})

    raw = '{"message_id": "wamid.confirm", "from_number": "911234567890", "timestamp": 1000, "type": "button_reply", "text": "confirm_booking", "title": "Confirm"}'
    await worker.process_message(raw)

    worker.whatsapp.send_text.assert_awaited_once()
    assert "booked" in worker.whatsapp.send_text.await_args.args[1].lower()
    assert sessions.get_session(phone)["pending_booking"] is None
    assert len(bookings.get_my_appointments(phone)) == 1


async def test_handoff_notifies_staff_and_sets_flag(fake_redis, fake_mongo, monkeypatch):
    monkeypatch.setattr(worker.handoff.settings, "staff_phone", "919999999999")
    monkeypatch.setattr(
        worker.loop, "run_agent_turn",
        lambda *a, **kw: AgentResult(text="Connecting you to staff.", handoff=True, handoff_reason="wants a human"),
    )

    await worker.process_message(_text_message_json(text="get me a human"))

    assert sessions.get_session("911234567890")["handoff"] is True
    # send_text is called both for the staff alert (handoff.trigger_handoff) and the user reply.
    assert worker.whatsapp.send_text.await_count == 2
