from app.services import bookings


def _seed_one_slot(fake_mongo):
    fake_mongo["doctors"].insert_one({"doctor_id": "dr_rao", "name": "Dr. Rao", "speciality": "General Medicine", "fee": 500})
    fake_mongo["slots"].insert_one({"doctor_id": "dr_rao", "date": "2026-09-10", "time": "09:00", "booked": False})


def test_book_available_slot_succeeds(fake_mongo):
    _seed_one_slot(fake_mongo)
    result = bookings.book_appointment("dr_rao", "2026-09-10", "09:00", "Asha", "911234567890")
    assert result["ok"] is True
    assert result["doctor_name"] == "Dr. Rao"

    slot = fake_mongo["slots"].find_one({"doctor_id": "dr_rao", "date": "2026-09-10", "time": "09:00"})
    assert slot["booked"] is True


def test_double_booking_the_same_slot_is_rejected(fake_mongo):
    """The core guard: second caller must fail, not silently overwrite the first."""
    _seed_one_slot(fake_mongo)

    first = bookings.book_appointment("dr_rao", "2026-09-10", "09:00", "Asha", "911111111111")
    second = bookings.book_appointment("dr_rao", "2026-09-10", "09:00", "Ravi", "922222222222")

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["error"] == "slot_unavailable"

    appointments = list(fake_mongo["appointments"].find({}))
    assert len(appointments) == 1  # only Asha's booking exists


def test_booking_unknown_doctor_fails_cleanly(fake_mongo):
    result = bookings.book_appointment("dr_nobody", "2026-09-10", "09:00", "Asha", "911234567890")
    assert result == {"ok": False, "error": "unknown_doctor"}


def test_cancel_frees_the_slot(fake_mongo):
    _seed_one_slot(fake_mongo)
    booked = bookings.book_appointment("dr_rao", "2026-09-10", "09:00", "Asha", "911234567890")

    cancel_result = bookings.cancel_appointment(booked["appointment_id"], "911234567890")
    assert cancel_result["ok"] is True

    slot = fake_mongo["slots"].find_one({"doctor_id": "dr_rao", "date": "2026-09-10", "time": "09:00"})
    assert slot["booked"] is False

    # And the freed slot can be booked again by someone else.
    rebooked = bookings.book_appointment("dr_rao", "2026-09-10", "09:00", "Ravi", "922222222222")
    assert rebooked["ok"] is True


def test_cancel_by_wrong_phone_fails(fake_mongo):
    _seed_one_slot(fake_mongo)
    booked = bookings.book_appointment("dr_rao", "2026-09-10", "09:00", "Asha", "911234567890")
    result = bookings.cancel_appointment(booked["appointment_id"], "999999999999")
    assert result == {"ok": False, "error": "not_found"}


def test_list_available_slots_excludes_booked(fake_mongo):
    fake_mongo["doctors"].insert_one({"doctor_id": "dr_rao", "name": "Dr. Rao", "speciality": "General Medicine", "fee": 500})
    fake_mongo["slots"].insert_many([
        {"doctor_id": "dr_rao", "date": "2026-09-10", "time": "09:00", "booked": False},
        {"doctor_id": "dr_rao", "date": "2026-09-10", "time": "09:30", "booked": True},
    ])
    available = bookings.list_available_slots("dr_rao", "2026-09-10")
    assert [s["time"] for s in available] == ["09:00"]
