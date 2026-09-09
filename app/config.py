"""Central settings, loaded once from environment / .env.

Every other module imports `settings` from here instead of calling
`os.environ` directly, so there is exactly one place that knows the env var
names and exactly one place a missing value fails loudly (at import time,
not three tool calls into a conversation).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # WhatsApp Cloud API
    phone_number_id: str = ""
    waba_id: str = ""
    access_token: str = ""
    app_secret: str = ""
    verify_token: str = "change-me"
    graph_api_version: str = "v21.0"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "ai_agent_convo"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Human handoff
    staff_phone: str = ""

    # Admin endpoints
    admin_token: str = "change-me"


settings = Settings()
