def test_parse_callback_extracts_fields():
    from app.telegram_bot import parse_callback
    payload = {
        "callback_query": {
            "id": "cb1",
            "data": "approve:42",
            "message": {"message_id": 99, "chat": {"id": 1000}},
        }
    }
    out = parse_callback(payload)
    assert out == {
        "action": "approve",
        "outreach_id": 42,
        "callback_id": "cb1",
        "chat_id": 1000,
        "message_id": 99,
    }


def test_parse_callback_returns_none_for_non_callback():
    from app.telegram_bot import parse_callback
    assert parse_callback({"message": {"text": "hi"}}) is None
    assert parse_callback({"callback_query": {"data": "malformed"}}) is None
