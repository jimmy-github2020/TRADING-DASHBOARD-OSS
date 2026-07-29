from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


SUMMARY_TZ = "Asia/Taipei"


def is_notification_enabled(target: dict, category: str) -> tuple[bool, str]:
    if not target.get("alerts_enabled", True):
        return False, "alerts disabled"

    key_by_category = {
        "market": "market_alerts_enabled",
        "price": "price_alerts_enabled",
        "technical": "technical_alerts_enabled",
        "ai_summary": "ai_summary_enabled",
    }
    key = key_by_category.get(category)
    if key and not target.get(key, False):
        return False, "category disabled"
    return True, "enabled"


def should_send_summary_now(
    summary_frequency: str,
    now: datetime | None = None,
    tz: str | None = None,
) -> tuple[bool, str]:
    timezone = ZoneInfo(tz or SUMMARY_TZ)
    current = now.astimezone(timezone) if now else datetime.now(timezone)
    hour = current.hour

    if summary_frequency == "off":
        allowed = False
    elif summary_frequency == "daily":
        allowed = 7 <= hour <= 11
    elif summary_frequency == "morning":
        allowed = 7 <= hour <= 11
    elif summary_frequency == "evening":
        # Taiwan market close reports run at 13:45, so this window starts after lunch.
        allowed = 13 <= hour <= 21
    else:
        allowed = False

    print(
        "[telegram:summary-frequency] "
        f"summary_frequency={summary_frequency} now={current.isoformat()} allowed={allowed}"
    )
    return allowed, "summary frequency allowed" if allowed else "frequency not allowed"
