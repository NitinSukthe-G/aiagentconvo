"""Token usage -> USD, accumulated per conversation (phone number) in Mongo.

Price table is USD per 1M tokens. Verify against Gemini's current pricing
page before trusting these numbers for anything beyond relative comparison —
list prices change and this is not fetched live.
"""

from app.services.mongo_client import conversations_col

PRICE_PER_MILLION_TOKENS_USD = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
}
DEFAULT_PRICE = {"input": 0.30, "output": 2.50}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICE_PER_MILLION_TOKENS_USD.get(model, DEFAULT_PRICE)
    return (prompt_tokens / 1_000_000) * price["input"] + (completion_tokens / 1_000_000) * price["output"]


def record_usage(phone: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    if prompt_tokens == 0 and completion_tokens == 0:
        return
    cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)
    conversations_col.update_one(
        {"phone": phone},
        {
            "$inc": {
                "tokens_in": prompt_tokens,
                "tokens_out": completion_tokens,
                "cost_usd": cost,
                "turns": 1,
            }
        },
        upsert=True,
    )


def get_conversation_cost(phone: str) -> dict:
    doc = conversations_col.find_one({"phone": phone}, {"_id": 0})
    return doc or {"phone": phone, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "turns": 0}
