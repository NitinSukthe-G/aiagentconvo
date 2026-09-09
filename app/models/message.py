"""Normalized shape for an inbound WhatsApp message.

The Cloud API webhook payload is deeply nested and differs by message type
(text vs. interactive button/list reply vs. status update). `parser.py` turns
all of that into this one flat shape so nothing downstream needs to know the
raw JSON layout.
"""

from typing import Literal

from pydantic import BaseModel

MessageType = Literal["text", "button_reply", "list_reply", "unknown"]


class Message(BaseModel):
    message_id: str
    from_number: str
    timestamp: int
    type: MessageType
    text: str  # for text: the body; for button/list reply: the tapped id
    title: str | None = None  # human-readable label of the tapped button/row
