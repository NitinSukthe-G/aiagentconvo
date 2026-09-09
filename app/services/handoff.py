"""Human handoff: silence the bot for a number, page staff, and release it back."""

import logging

from app.config import settings
from app.services import sessions
from app.whatsapp import client as whatsapp

logger = logging.getLogger(__name__)


async def trigger_handoff(phone: str, reason: str) -> None:
    sessions.set_handoff(phone, True)

    session = sessions.get_session(phone)
    recent = session["history"][-5:]
    transcript = "\n".join(f"{turn['role']}: {turn['content']}" for turn in recent) or "(no prior messages)"

    if settings.staff_phone:
        alert = (
            f"🔔 Handoff requested\nCustomer: {phone}\nReason: {reason}\n\n"
            f"Last messages:\n{transcript}"
        )
        await whatsapp.send_text(settings.staff_phone, alert)
    else:
        logger.warning("STAFF_PHONE not configured — handoff alert for %s not sent", phone)


def release(phone: str) -> None:
    sessions.set_handoff(phone, False)
