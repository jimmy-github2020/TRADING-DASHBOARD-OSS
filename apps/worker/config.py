from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    api_base_url: str
    enable_live_trading: bool
    quote_refresh_minutes: int
    daily_refresh_hour_utc: int
    line_channel_access_token: str
    line_user_id: str
    telegram_bot_token: str
    telegram_chat_id: str
    notification_dry_run: bool
    notification_cooldown_hours: int
    worker_automation_enabled: bool


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://trading:trading_password@postgres:5432/trading_dashboard",
        ),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        api_base_url=os.getenv("API_BASE_URL", "http://api:8001"),
        enable_live_trading=os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true",
        quote_refresh_minutes=int(os.getenv("QUOTE_REFRESH_MINUTES", "15")),
        daily_refresh_hour_utc=int(os.getenv("DAILY_REFRESH_HOUR_UTC", "6")),
        line_channel_access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", ""),
        line_user_id=os.getenv("LINE_USER_ID", ""),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        notification_dry_run=os.getenv("NOTIFICATION_DRY_RUN", "true").lower() != "false",
        notification_cooldown_hours=int(os.getenv("NOTIFICATION_COOLDOWN_HOURS", "4")),
        worker_automation_enabled=os.getenv(
            "WORKER_AUTOMATION_ENABLED", "false"
        ).lower()
        == "true",
    )
