from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    openai_api_key: str
    ai_brief_enabled: bool
    ai_brief_model: str
    telegram_bot_token: str
    telegram_webhook_secret: str


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://trading:trading_password@postgres:5432/trading_dashboard",
        ),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        ai_brief_enabled=os.getenv("AI_BRIEF_ENABLED", "true").lower() == "true",
        ai_brief_model=os.getenv("AI_BRIEF_MODEL", "gpt-4o-mini"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", "dev_webhook_secret"),
    )
