"""Small internal endpoints for staff/ops — not exposed to WhatsApp users.

Gated by a single shared `X-Admin-Token` header rather than left open: these
return a customer's message history and let anyone flip the handoff flag, so
an unauthenticated version would be a real data leak / bot-hijack, not a
convenience worth skipping.
"""

from fastapi import APIRouter, Header, HTTPException

from app.config import settings
from app.services import bookings, costs, handoff, sessions

router = APIRouter(prefix="/admin")


def _require_admin(x_admin_token: str | None) -> None:
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Token")


@router.get("/conversations/{phone}")
def get_conversation(phone: str, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    return {
        "phone": phone,
        "session": sessions.get_session(phone),
        "appointments": bookings.get_my_appointments(phone),
        "cost": costs.get_conversation_cost(phone),
    }


@router.post("/release/{phone}")
def release_handoff(phone: str, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    handoff.release(phone)
    return {"phone": phone, "handoff": False}
