import pytest

from app.services import costs


def test_estimate_cost_uses_correct_price_table():
    cost = costs.estimate_cost_usd("gemini-2.5-flash", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == pytest.approx(0.30 + 2.50)


def test_estimate_cost_unknown_model_falls_back_to_default():
    cost = costs.estimate_cost_usd("some-future-model", prompt_tokens=1_000_000, completion_tokens=0)
    assert cost == pytest.approx(costs.DEFAULT_PRICE["input"])


def test_record_usage_accumulates_across_turns(fake_mongo):
    costs.record_usage("911234567890", "gemini-2.5-flash", 1000, 500)
    costs.record_usage("911234567890", "gemini-2.5-flash", 2000, 1000)

    doc = costs.get_conversation_cost("911234567890")
    assert doc["tokens_in"] == 3000
    assert doc["tokens_out"] == 1500
    assert doc["turns"] == 2
    assert doc["cost_usd"] > 0


def test_record_usage_skips_zero_usage(fake_mongo):
    costs.record_usage("911234567890", "gemini-2.5-flash", 0, 0)
    doc = costs.get_conversation_cost("911234567890")
    assert doc["tokens_in"] == 0
    assert doc["turns"] == 0
