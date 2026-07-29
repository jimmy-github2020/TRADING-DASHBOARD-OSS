from __future__ import annotations

from typing import Any

import asyncpg


PENDING_CHAT_ID = "web_pending"
ITEMS = {
    "morning_brief": {
        "setting": "ai_summary_enabled",
        "manual_types": {"manual_test_morning_brief"},
        "background_types": {"morning_brief"},
        "background_prefixes": (),
        "empty_message": "早盤摘要尚無測試或背景執行紀錄。",
    },
    "closing_brief": {
        "setting": "ai_summary_enabled",
        "manual_types": {"manual_test_closing_brief"},
        "background_types": {"closing_report"},
        "background_prefixes": (),
        "empty_message": "晚間摘要尚無測試或背景執行紀錄。",
    },
    "market_alert": {
        "setting": "market_alerts_enabled",
        "manual_types": {"manual_test_market_alert"},
        "background_types": {"market_alert", "alert_twii_move", "alert_vix", "alert_fear_greed"},
        "background_prefixes": ("market_alert:", "alert_twii_", "alert_vix_", "alert_fear_greed_"),
        "empty_message": "市場風險警示尚無測試或背景執行紀錄。",
    },
    "price_alert": {
        "setting": "price_alerts_enabled",
        "manual_types": {"manual_test_price_alert"},
        "background_types": {"price_alert"},
        "background_prefixes": ("price_alert:",),
        "empty_message": "個股價格警示尚無測試或背景執行紀錄。",
    },
    "technical_alert": {
        "setting": "technical_alerts_enabled",
        "manual_types": {"manual_test_technical_alert"},
        "background_types": {"technical_signal"},
        "background_prefixes": ("signal_",),
        "empty_message": "技術訊號警示尚無測試或背景執行紀錄。",
    },
}


async def fetch_notification_item_status(database_url: str) -> dict[str, Any]:
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_tables(conn)
        settings = await _fetch_settings(conn)
        dry_run = await _fetch_dry_run(conn)
        events = await _fetch_recent_events(conn)
        return {
            "mode": "dry_run" if dry_run else "live",
            "items": {
                item_type: _item_response(item_type, config, settings, events)
                for item_type, config in ITEMS.items()
            },
        }
    finally:
        await conn.close()


async def _fetch_settings(conn: asyncpg.Connection) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        SELECT *
        FROM notification_settings
        WHERE chat_id <> $1
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        PENDING_CHAT_ID,
    )
    if not row:
        row = await conn.fetchrow(
            """
            SELECT *
            FROM notification_settings
            WHERE chat_id = $1
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            PENDING_CHAT_ID,
        )
    return dict(row) if row else {}


async def _fetch_dry_run(conn: asyncpg.Connection) -> bool:
    row = await conn.fetchrow("SELECT value FROM app_settings WHERE key = 'notification_dry_run'")
    if row is None:
        return True
    value = row["value"]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "dry_run", "1", "yes"}
    return bool(value)


async def _fetch_recent_events(conn: asyncpg.Connection) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT notification_type, status, skip_reason, message_preview, created_at, metadata_json
        FROM notification_runtime_events
        ORDER BY created_at DESC
        LIMIT 300
        """
    )
    return [dict(row) for row in rows]


def _item_response(
    item_type: str,
    config: dict[str, Any],
    settings: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    latest_manual = _latest_manual_event(events, config)
    latest_background = _latest_background_event(events, config)
    latest_display = _latest_display_event(latest_manual, latest_background)
    latest_source = _display_source(latest_display, latest_manual, latest_background)
    enabled = bool(settings.get("alerts_enabled", True)) and bool(settings.get(config["setting"], False))
    if latest_display is None:
        return {
            "enabled": enabled,
            "latest_manual_test_status": None,
            "latest_manual_test_at": None,
            "latest_background_status": None,
            "latest_background_at": None,
            "latest_display_status": "empty",
            "latest_display_source": None,
            "latest_message": config["empty_message"],
            "last_status": "empty",
            "last_event_at": None,
            "last_message": config["empty_message"],
        }

    display_status = _event_status(latest_display)
    display_at = _event_time(latest_display)
    display_message = latest_display.get("message_preview") or _status_message(item_type, display_status)
    return {
        "enabled": enabled,
        "latest_manual_test_status": _event_status(latest_manual) if latest_manual else None,
        "latest_manual_test_at": _event_time(latest_manual) if latest_manual else None,
        "latest_background_status": _event_status(latest_background) if latest_background else None,
        "latest_background_at": _event_time(latest_background) if latest_background else None,
        "latest_display_status": display_status,
        "latest_display_source": latest_source,
        "latest_message": display_message,
        # Backward-compatible fields for T7-9 clients.
        "last_status": display_status,
        "last_event_at": display_at,
        "last_message": display_message,
    }


def _latest_manual_event(events: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any] | None:
    exact = config["manual_types"]
    for event in events:
        if (event.get("notification_type") or "") in exact:
            return event
    return None


def _latest_background_event(events: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any] | None:
    exact = config["background_types"]
    prefixes = config["background_prefixes"]
    for event in events:
        notification_type = event.get("notification_type") or ""
        if notification_type in exact or any(notification_type.startswith(prefix) for prefix in prefixes):
            return event
    return None


def _latest_display_event(
    manual: dict[str, Any] | None,
    background: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if manual is None:
        return background
    if background is None:
        return manual
    return manual if manual["created_at"] >= background["created_at"] else background


def _display_source(
    display: dict[str, Any] | None,
    manual: dict[str, Any] | None,
    background: dict[str, Any] | None,
) -> str | None:
    if display is None:
        return None
    if manual is not None and display is manual:
        return "manual_test"
    if background is not None and display is background:
        return "background"
    return None


def _event_status(event: dict[str, Any] | None) -> str | None:
    if not event:
        return None
    return event.get("skip_reason") or event.get("status") or "unknown"


def _event_time(event: dict[str, Any] | None) -> str | None:
    if not event or not event.get("created_at"):
        return None
    return event["created_at"].isoformat()


def _status_message(item_type: str, status: str) -> str:
    title = {
        "morning_brief": "早盤摘要",
        "closing_brief": "晚間摘要",
        "market_alert": "市場警示",
        "price_alert": "價格警示",
        "technical_alert": "技術警示",
    }.get(item_type, "通知")
    return f"{title}最近狀態：{status}"


async def _ensure_tables(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        ALTER TABLE notification_settings
          ADD COLUMN IF NOT EXISTS market_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS price_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS technical_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS ai_summary_enabled BOOLEAN NOT NULL DEFAULT false,
          ADD COLUMN IF NOT EXISTS summary_frequency VARCHAR(20) NOT NULL DEFAULT 'morning'
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
          key VARCHAR(120) PRIMARY KEY,
          value JSONB NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_runtime_events (
          id SERIAL PRIMARY KEY,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          job_name VARCHAR(80),
          notification_type VARCHAR(80) NOT NULL,
          status VARCHAR(30) NOT NULL,
          skip_reason VARCHAR(80),
          symbol VARCHAR(40),
          topic VARCHAR(120),
          message_preview TEXT,
          chat_id VARCHAR(50),
          dedup_key VARCHAR(220),
          metadata_json JSONB
        )
        """
    )
