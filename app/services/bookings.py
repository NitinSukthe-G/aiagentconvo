"""Doctor/slot/appointment logic against MongoDB.

The one rule that matters: a slot is claimed with a single atomic
`find_one_and_update`, never a read-then-write. Two people tapping "confirm"
on the same slot within the same second must not both get a booking.
"""

import uuid
from datetime import UTC, datetime

from app.services.mongo_client import appointments_col, doctors_col, slots_col


def list_doctors() -> list[dict]:
    return list(doctors_col.find({}, {"_id": 0}))


def get_doctor(doctor_id: str) -> dict | None:
    return doctors_col.find_one({"doctor_id": doctor_id}, {"_id": 0})


def list_available_slots(doctor_id: str, date: str) -> list[dict]:
    """date: YYYY-MM-DD. Returns only unbooked slots, ascending by time."""
    slots = slots_col.find(
        {"doctor_id": doctor_id, "date": date, "booked": False}, {"_id": 0}
    )
    return sorted(slots, key=lambda s: s["time"])


def book_appointment(doctor_id: str, date: str, time: str, patient_name: str, phone: str) -> dict:
    doctor = get_doctor(doctor_id)
    if doctor is None:
        return {"ok": False, "error": "unknown_doctor"}

    # The atomic step: only succeeds if the slot exists and is still unbooked.
    claimed = slots_col.find_one_and_update(
        {"doctor_id": doctor_id, "date": date, "time": time, "booked": False},
        {"$set": {"booked": True}},
    )
    if claimed is None:
        return {"ok": False, "error": "slot_unavailable"}

    appointment_id = uuid.uuid4().hex[:10]
    appointments_col.insert_one({
        "appointment_id": appointment_id,
        "doctor_id": doctor_id,
        "doctor_name": doctor["name"],
        "date": date,
        "time": time,
        "patient_name": patient_name,
        "phone": phone,
        "status": "booked",
        "created_at": datetime.now(UTC),
    })
    return {
        "ok": True,
        "appointment_id": appointment_id,
        "doctor_name": doctor["name"],
        "fee": doctor["fee"],
        "date": date,
        "time": time,
    }


def get_my_appointments(phone: str) -> list[dict]:
    appts = appointments_col.find(
        {"phone": phone, "status": "booked"}, {"_id": 0}
    )
    return sorted(appts, key=lambda a: (a["date"], a["time"]))


def cancel_appointment(appointment_id: str, phone: str) -> dict:
    appointment = appointments_col.find_one({"appointment_id": appointment_id, "phone": phone})
    if appointment is None:
        return {"ok": False, "error": "not_found"}
    if appointment["status"] == "cancelled":
        return {"ok": False, "error": "already_cancelled"}

    appointments_col.update_one(
        {"appointment_id": appointment_id}, {"$set": {"status": "cancelled"}}
    )
    slots_col.update_one(
        {"doctor_id": appointment["doctor_id"], "date": appointment["date"], "time": appointment["time"]},
        {"$set": {"booked": False}},
    )
    return {"ok": True, "appointment_id": appointment_id}
