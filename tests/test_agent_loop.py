"""Agent loop tests against a mocked Gemini client — no real API key needed.

`llm.generate` is monkeypatched directly rather than mocking the whole
google-genai client, since `loop.py` only ever calls that one function.
"""

from types import SimpleNamespace

import pytest

from app.agent import loop


def make_response(calls=None, text="", prompt_tokens=0, completion_tokens=0):
    function_calls = None
    if calls:
        function_calls = [SimpleNamespace(name=name, args=args) for name, args in calls]
    return SimpleNamespace(
        function_calls=function_calls,
        text=text,
        usage_metadata=SimpleNamespace(prompt_token_count=prompt_tokens, candidates_token_count=completion_tokens),
        candidates=[SimpleNamespace(content=SimpleNamespace())],
    )


def test_tool_call_then_final_answer(monkeypatch):
    fake_doctors = [{"doctor_id": "dr_rao", "name": "Dr. Rao", "speciality": "General Medicine", "fee": 500}]
    monkeypatch.setattr(loop, "TOOL_FUNCTIONS", {**loop.TOOL_FUNCTIONS, "list_doctors": lambda: fake_doctors})

    responses = [
        make_response(calls=[("list_doctors", {})], prompt_tokens=10, completion_tokens=5),
        make_response(text="Here are our doctors.", prompt_tokens=20, completion_tokens=8),
    ]
    monkeypatch.setattr(loop.llm, "generate", lambda *a, **kw: responses.pop(0))

    result = loop.run_agent_turn("911234567890", "who are the doctors?", [], "en")

    assert result.text == "Here are our doctors."
    assert result.tool_calls == ["list_doctors"]
    assert result.tool_results["list_doctors"] == fake_doctors
    assert result.prompt_tokens == 30
    assert result.completion_tokens == 13
    assert result.handoff is False
    assert result.pending_booking is None


def test_handoff_short_circuits_after_one_round(monkeypatch):
    call_count = {"n": 0}

    def fake_generate(*a, **kw):
        call_count["n"] += 1
        return make_response(calls=[("request_human_handoff", {"reason": "angry customer"})])

    monkeypatch.setattr(loop.llm, "generate", fake_generate)

    result = loop.run_agent_turn("911234567890", "let me talk to a person", [], "en")

    assert result.handoff is True
    assert result.handoff_reason == "angry customer"
    assert "connecting you" in result.text.lower()
    assert call_count["n"] == 1  # no second round needed


def test_booking_is_intercepted_not_executed_directly(monkeypatch):
    args = {"doctor_id": "dr_rao", "date": "2026-09-10", "time": "09:00", "patient_name": "Asha"}
    responses = [
        make_response(calls=[("book_appointment", args)]),
        make_response(text="Please confirm below."),
    ]
    monkeypatch.setattr(loop.llm, "generate", lambda *a, **kw: responses.pop(0))

    # No Mongo fixture used here on purpose: if the loop tried to actually book,
    # this would raise (no DB connection) instead of quietly succeeding.
    result = loop.run_agent_turn("911234567890", "book dr rao tomorrow 9am for Asha", [], "en")

    assert result.pending_booking == args
    assert result.text == "Please confirm below."
    assert "book_appointment" not in result.tool_results


def test_hitting_max_rounds_returns_fallback_text(monkeypatch):
    monkeypatch.setattr(loop.llm, "generate", lambda *a, **kw: make_response(calls=[("get_clinic_info", {"topic": "timings"})]))

    result = loop.run_agent_turn("911234567890", "what are your timings?", [], "en")

    assert result.tool_calls == ["get_clinic_info"] * loop.MAX_TOOL_ROUNDS
    assert "trouble" in result.text.lower()
