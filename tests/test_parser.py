from app.whatsapp.parser import parse_webhook_payload


def _wrap(message: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA_ID", "changes": [{"value": {"messages": [message]}, "field": "messages"}]}],
    }


def test_parses_text_message():
    payload = _wrap({"id": "wamid.1", "from": "911234567890", "timestamp": "1000", "type": "text", "text": {"body": "hi"}})
    messages = parse_webhook_payload(payload)
    assert len(messages) == 1
    assert messages[0].type == "text"
    assert messages[0].text == "hi"
    assert messages[0].from_number == "911234567890"


def test_parses_button_reply():
    payload = _wrap({
        "id": "wamid.2", "from": "911234567890", "timestamp": "1000", "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"id": "confirm_booking", "title": "Confirm"}},
    })
    messages = parse_webhook_payload(payload)
    assert messages[0].type == "button_reply"
    assert messages[0].text == "confirm_booking"
    assert messages[0].title == "Confirm"


def test_parses_list_reply():
    payload = _wrap({
        "id": "wamid.3", "from": "911234567890", "timestamp": "1000", "type": "interactive",
        "interactive": {"type": "list_reply", "list_reply": {"id": "dr_rao", "title": "Dr. Rao", "description": "General Medicine"}},
    })
    messages = parse_webhook_payload(payload)
    assert messages[0].type == "list_reply"
    assert messages[0].text == "dr_rao"
    assert messages[0].title == "Dr. Rao"


def test_status_update_produces_no_messages():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA_ID", "changes": [{"value": {"statuses": [{"id": "wamid.4", "status": "delivered"}]}, "field": "messages"}]}],
    }
    assert parse_webhook_payload(payload) == []


def test_unsupported_type_becomes_unknown_not_dropped():
    payload = _wrap({"id": "wamid.5", "from": "911234567890", "timestamp": "1000", "type": "image", "image": {"id": "abc"}})
    messages = parse_webhook_payload(payload)
    assert len(messages) == 1
    assert messages[0].type == "unknown"
