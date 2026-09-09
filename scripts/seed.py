"""Seed MongoDB with the 3 doctors from clinic_info.json and 7 days of slots.

Run once against a fresh database: `uv run python scripts/seed.py`
Safe to re-run: doctors are upserted, and slot generation skips any
(doctor, date, time) combination that already exists so it never resets an
already-booked slot back to open.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.mongo_client import doctors_col, slots_col  # noqa: E402

CLINIC_INFO_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "clinic_info.json"

MORNING = [f"{h:02d}:{m:02d}" for h in range(9, 13) for m in (0, 30)]
EVENING = [f"{h:02d}:{m:02d}" for h in range(17, 21) for m in (0, 30)]
SLOT_TIMES = MORNING + EVENING
WEEKDAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAYS_AHEAD = 7


def seed_doctors(clinic: dict) -> None:
    for doctor in clinic["doctors"]:
        doctors_col.update_one(
            {"doctor_id": doctor["doctor_id"]}, {"$set": doctor}, upsert=True
        )
    print(f"Seeded {len(clinic['doctors'])} doctors.")


def seed_slots(clinic: dict) -> None:
    created = 0
    today = date.today()
    for offset in range(DAYS_AHEAD):
        day = today + timedelta(days=offset)
        weekday = WEEKDAY_ABBR[day.weekday()]
        for doctor in clinic["doctors"]:
            if weekday not in doctor["available_days"]:
                continue
            for time_str in SLOT_TIMES:
                result = slots_col.update_one(
                    {"doctor_id": doctor["doctor_id"], "date": day.isoformat(), "time": time_str},
                    {"$setOnInsert": {"booked": False}},
                    upsert=True,
                )
                if result.upserted_id is not None:
                    created += 1
    print(f"Seeded {created} new slots across the next {DAYS_AHEAD} days.")


if __name__ == "__main__":
    clinic_info = json.loads(CLINIC_INFO_PATH.read_text())
    seed_doctors(clinic_info)
    seed_slots(clinic_info)
