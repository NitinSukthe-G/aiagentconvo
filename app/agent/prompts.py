"""System prompt and small language-aware UI text.

The system prompt is rebuilt per request (not cached) because it embeds
today's date — the model has no other way to resolve "tomorrow" or "this
Saturday" into a YYYY-MM-DD it can pass to `list_available_slots`.
"""

from datetime import date

CLINIC_NAME = "Amrutha Multispeciality Clinic"

LANGUAGE_NAMES = {"en": "English", "hinglish": "Hinglish (Hindi mixed with English, Roman script)", "te": "Telugu"}


def build_system_prompt(language: str | None) -> str:
    today = date.today().isoformat()
    weekday = date.today().strftime("%A")

    language_rule = (
        "Detect the user's language from their message and reply in the same language and "
        "script. If they write Hinglish, reply in Hinglish using Roman (English) script — never "
        "Devanagari. If they write Telugu, reply in Telugu script. If they write English, reply "
        "in English."
        if language is None
        else f"The user has been writing in {LANGUAGE_NAMES.get(language, language)}. "
        f"Keep replying in that same language and script unless they switch."
    )

    return f"""You are the WhatsApp assistant for {CLINIC_NAME}. Today's date is {today} ({weekday}).

Rules:
- Answer questions only using the provided tools. Never invent clinic details, doctors, fees, or appointment slots.
- {language_rule}
- When booking, collect doctor, date, time, and patient name. Ask for missing details one at a time — do not ask for everything in one message.
- Once you have all four booking details, call book_appointment right away — you do not need to ask the user to confirm in text first. The system will automatically show them a Confirm/Cancel button before anything is actually booked, so just briefly say the booking is ready to confirm.
- When list_doctors or list_available_slots returns results, the system automatically shows them as a tappable list — keep your own text brief (e.g. "Here are our doctors:") instead of repeating every item as a wall of text.
- If a slot turns out to be unavailable (someone else booked it first), say so plainly and offer to show other times — never claim it succeeded.
- If the user asks to talk to a human/agent/staff, or you cannot help after two attempts, call request_human_handoff.
- Keep replies short — this is WhatsApp, not email.
"""


LANGUAGE_DETECTION_PROMPT = """Classify the language and script of this message as exactly one \
of: en, hinglish, te. "hinglish" means Hindi words written in Roman/English script (possibly \
mixed with English words). "te" means Telugu script or clearly Telugu words (even if in Roman \
script). "en" means plain English. Reply with only the single code, nothing else.

Message: {message}"""


# Button/list labels shown in interactive WhatsApp messages, per language.
UI_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "choose_doctor": "Choose a doctor",
        "choose_time": "Choose a time",
        "confirm_booking": "Confirm booking?",
        "confirm": "Confirm",
        "cancel": "Cancel",
        "view_doctors": "View doctors",
        "view_times": "View times",
    },
    "hinglish": {
        "choose_doctor": "Doctor chuniye",
        "choose_time": "Time chuniye",
        "confirm_booking": "Booking confirm karein?",
        "confirm": "Confirm",
        "cancel": "Cancel",
        "view_doctors": "Doctors dekhein",
        "view_times": "Times dekhein",
    },
    "te": {
        "choose_doctor": "డాక్టర్‌ను ఎంచుకోండి",
        "choose_time": "సమయాన్ని ఎంచుకోండి",
        "confirm_booking": "బుకింగ్ నిర్ధారించాలా?",
        "confirm": "నిర్ధారించండి",
        "cancel": "రద్దు చేయండి",
        "view_doctors": "డాక్టర్లను చూడండి",
        "view_times": "సమయాలు చూడండి",
    },
}


def ui_text(language: str | None, key: str) -> str:
    return UI_TEXT.get(language or "en", UI_TEXT["en"]).get(key, UI_TEXT["en"][key])
