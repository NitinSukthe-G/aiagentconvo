"""Turn a raw WhatsApp Cloud API webhook payload into a list of `Message`.

One POST to /webhook can carry multiple entries/changes, each with its own
`messages` array (usually one message, but the API allows a batch). A
`changes[].value` with no `messages` key is a delivery/read status update
(sent, delivered, read, failed) — those get skipped, not turned into an
(empty) Message.
"""

from app.models.message import Message


def parse_webhook_payload(payload: dict) -> list[Message]:
    messages: list[Message] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for raw in value.get("messages", []):
                message = _parse_single_message(raw)
                if message is not None:
                    messages.append(message)
            # value.get("statuses", []) -> delivery/read receipts, ignored.

    return messages


def _parse_single_message(raw: dict) -> Message | None:
    message_id = raw.get("id", "")
    from_number = raw.get("from", "")
    timestamp = int(raw.get("timestamp", 0))
    msg_type = raw.get("type")

    if msg_type == "text":
        return Message(
            message_id=message_id,
            from_number=from_number,
            timestamp=timestamp,
            type="text",
            text=raw.get("text", {}).get("body", ""),
        )

    if msg_type == "interactive":
        interactive = raw.get("interactive", {})
        interactive_type = interactive.get("type")

        if interactive_type == "button_reply":
            reply = interactive["button_reply"]
            return Message(
                message_id=message_id,
                from_number=from_number,
                timestamp=timestamp,
                type="button_reply",
                text=reply["id"],
                title=reply.get("title"),
            )

        if interactive_type == "list_reply":
            reply = interactive["list_reply"]
            return Message(
                message_id=message_id,
                from_number=from_number,
                timestamp=timestamp,
                type="list_reply",
                text=reply["id"],
                title=reply.get("title"),
            )

    # Anything else (image, audio, location, unsupported...) — acknowledge
    # that a message arrived so it doesn't silently vanish, but the agent
    # loop treats "unknown" as "I can't handle this type" rather than
    # crashing the parser.
    return Message(
        message_id=message_id,
        from_number=from_number,
        timestamp=timestamp,
        type="unknown",
        text="",
    )
