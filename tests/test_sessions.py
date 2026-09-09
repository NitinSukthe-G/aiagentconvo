from app.services import sessions


def test_history_caps_at_max_turns(fake_redis):
    phone = "911234567890"
    for i in range(sessions.MAX_HISTORY_TURNS + 5):
        sessions.append_turn(phone, "user", f"message {i}")

    session = sessions.get_session(phone)
    assert len(session["history"]) == sessions.MAX_HISTORY_TURNS
    assert session["history"][0]["content"] == "message 5"  # oldest 5 fell off
    assert session["history"][-1]["content"] == f"message {sessions.MAX_HISTORY_TURNS + 4}"


def test_language_cache_counts_down_then_expires(fake_redis):
    phone = "911234567890"
    sessions.set_language(phone, "hinglish")
    session = sessions.get_session(phone)
    assert session["language"] == "hinglish"
    assert session["language_cache_remaining"] == sessions.LANGUAGE_CACHE_TURNS

    for _ in range(sessions.LANGUAGE_CACHE_TURNS):
        session = sessions.tick_language_cache(phone)
    assert session["language_cache_remaining"] == 0  # caller should now re-detect


def test_handoff_flag_round_trips(fake_redis):
    phone = "911234567890"
    assert sessions.get_session(phone)["handoff"] is False
    sessions.set_handoff(phone, True)
    assert sessions.get_session(phone)["handoff"] is True
    sessions.set_handoff(phone, False)
    assert sessions.get_session(phone)["handoff"] is False


def test_pending_booking_round_trips(fake_redis):
    phone = "911234567890"
    booking = {"doctor_id": "dr_rao", "date": "2026-09-10", "time": "09:00", "patient_name": "Asha"}
    sessions.set_pending_booking(phone, booking)
    assert sessions.get_session(phone)["pending_booking"] == booking
    sessions.set_pending_booking(phone, None)
    assert sessions.get_session(phone)["pending_booking"] is None
