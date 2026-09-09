"""Tool declarations (JSON schema, for Gemini) and their Python implementations.

Two tools carry an implicit `phone` that the model never sees or supplies —
it comes from the WhatsApp session, not from anything the user typed, so it
is bound at dispatch time in `loop.py` rather than being a declared
parameter. This also means the model cannot be talked into booking or
cancelling on someone else's behalf.

`request_human_handoff` doesn't touch the database: it just returns a
sentinel the agent loop recognizes to stop the conversation and page staff
(see `services/handoff.py`).
"""

import json
from pathlib import Path
from typing import Any, Callable

from app.services import bookings

CLINIC_INFO_PATH = Path(__file__).resolve().parent.parent / "data" / "clinic_info.json"
CLINIC_INFO: dict = json.loads(CLINIC_INFO_PATH.read_text())

# Tools whose Python function needs `phone` injected — the model never sees this parameter.
PHONE_BOUND_TOOLS = {"book_appointment", "get_my_appointments", "cancel_appointment"}


def get_clinic_info(topic: str) -> dict:
    """topic: one of timings, doctors, services, location, parking, insurance,
    payment_methods, or 'all'. Unknown topics fall back to the full info so
    the model can still answer instead of getting stuck on a bad topic guess.
    """
    topic_map = {
        "timings": {"timings": CLINIC_INFO["timings"]},
        "location": {"address": CLINIC_INFO["address"], "phone": CLINIC_INFO["phone"]},
        "doctors": {"doctors": CLINIC_INFO["doctors"]},
        "services": {"services": CLINIC_INFO["services"]},
        "parking": {"parking": CLINIC_INFO["parking"]},
        "insurance": {"insurance": CLINIC_INFO["insurance"]},
        "payment_methods": {"payment_methods": CLINIC_INFO["payment_methods"]},
        "fees": {"doctors": [{"name": d["name"], "speciality": d["speciality"], "fee": d["fee"]} for d in CLINIC_INFO["doctors"]]},
    }
    return topic_map.get(topic, CLINIC_INFO)


def list_doctors() -> list[dict]:
    return bookings.list_doctors()


def list_available_slots(doctor_id: str, date: str) -> list[dict]:
    slots = bookings.list_available_slots(doctor_id, date)
    if not slots:
        return [{"message": "No open slots for this doctor on this date."}]
    return slots


def book_appointment(doctor_id: str, date: str, time: str, patient_name: str, phone: str) -> dict:
    return bookings.book_appointment(doctor_id, date, time, patient_name, phone)


def get_my_appointments(phone: str) -> list[dict]:
    appts = bookings.get_my_appointments(phone)
    return appts or [{"message": "No upcoming appointments found."}]


def cancel_appointment(appointment_id: str, phone: str) -> dict:
    return bookings.cancel_appointment(appointment_id, phone)


def request_human_handoff(reason: str) -> dict:
    return {"handoff_requested": True, "reason": reason}


TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "get_clinic_info": get_clinic_info,
    "list_doctors": list_doctors,
    "list_available_slots": list_available_slots,
    "book_appointment": book_appointment,
    "get_my_appointments": get_my_appointments,
    "cancel_appointment": cancel_appointment,
    "request_human_handoff": request_human_handoff,
}

TOOL_DECLARATIONS: list[dict] = [
    {
        "name": "get_clinic_info",
        "description": "Get clinic information such as timings, location, services, parking, insurance, or payment methods.",
        "parameters_json_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": ["timings", "location", "doctors", "services", "parking", "insurance", "payment_methods", "fees", "all"],
                }
            },
            "required": ["topic"],
        },
    },
    {
        "name": "list_doctors",
        "description": "List all doctors at the clinic with their speciality and fee.",
        "parameters_json_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_available_slots",
        "description": "List open (unbooked) appointment slot times for a doctor on a given date.",
        "parameters_json_schema": {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "string", "description": "e.g. dr_rao, dr_kavitha, dr_imran"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            },
            "required": ["doctor_id", "date"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Book an appointment. Only call this after the user has confirmed the doctor, date, time, and their name.",
        "parameters_json_schema": {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM, 24-hour"},
                "patient_name": {"type": "string"},
            },
            "required": ["doctor_id", "date", "time", "patient_name"],
        },
    },
    {
        "name": "get_my_appointments",
        "description": "Get the upcoming appointments booked by this user.",
        "parameters_json_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel an existing appointment by its appointment_id.",
        "parameters_json_schema": {
            "type": "object",
            "properties": {"appointment_id": {"type": "string"}},
            "required": ["appointment_id"],
        },
    },
    {
        "name": "request_human_handoff",
        "description": "Call this when the user explicitly asks for a human/staff member, or when you cannot help after a couple of tries.",
        "parameters_json_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Short reason for the handoff"}},
            "required": ["reason"],
        },
    },
]
