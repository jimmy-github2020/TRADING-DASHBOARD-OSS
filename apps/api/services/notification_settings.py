from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg


PENDING_CHAT_ID = "web_pending"
VALID_FREQUENCIES = {"off", "daily", "morning", "evening"}


@dataclass(frozen=True)
class NotificationSettingsUpdate:
    alerts_enabled: bool
    market_alerts_enabled: bool
    price_alerts_enabled: bool
    technical_alerts_enabled: bool
    ai_summary_enabled: bool
    summary_frequency: str


async def get_notification_settings(database_url: str) -> dict[str, Any]:
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_columns(conn)
        row = await _fetch_current_settings_row(conn)
        delivery = await _fetch_latest_delivery(conn)
        return _to_response(dict(row) if row else None, delivery)
    finally:
        await conn.close()


async def update_notification_settings(database_url: str, update: NotificationSettingsUpdate) -> dict[str, Any]:
    if update.summary_frequency not in VALID_FREQUENCIES:
        raise ValueError("Invalid summary_frequency")

    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_columns(conn)
        row = await _fetch_current_settings_row(conn)
        chat_id = row["chat_id"] if row else PENDING_CHAT_ID
        updated = await conn.fetchrow(
            """
            INSERT INTO notification_settings (
              chat_id, alerts_enabled, market_alerts_enabled, price_alerts_enabled,
              technical_alerts_enabled, ai_summary_enabled, summary_frequency, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, now())
            ON CONFLICT (chat_id) DO UPDATE
            SET alerts_enabled = EXCLUDED.alerts_enabled,
                market_alerts_enabled = EXCLUDED.market_alerts_enabled,
                price_alerts_enabled = EXCLUDED.price_alerts_enabled,
                technical_alerts_enabled = EXCLUDED.technical_alerts_enabled,
                ai_summary_enabled = EXCLUDED.ai_summary_enabled,
                summary_frequency = EXCLUDED.summary_frequency,
                updated_at = now()
            RETURNING *
            """,
            chat_id,
            update.alerts_enabled,
            update.market_alerts_enabled,
            update.price_alerts_enabled,
            update.technical_alerts_enabled,
            update.ai_summary_enabled,
            update.summary_frequency,
        )
        delivery = await _fetch_latest_delivery(conn)
        return _to_response(dict(updated), delivery)
    finally:
        await conn.close()


async def _fetch_current_settings_row(conn: asyncpg.Connection) -> asyncpg.Record | None:
    real = await conn.fetchrow(
        """
        SELECT *
        FROM notification_settings
        WHERE chat_id <> $1
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        PENDING_CHAT_ID,
    )
    if real:
        return real
    return await conn.fetchrow(
        """
        SELECT *
        FROM notification_settings
        WHERE chat_id = $1
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        PENDING_CHAT_ID,
    )


async def _fetch_latest_delivery(conn: asyncpg.Connection) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT status, sent_at
        FROM notification_deliveries
        ORDER BY sent_at DESC
        LIMIT 1
        """
    )
    return dict(row) if row else None


async def _ensure_columns(conn: asyncpg.Connection) -> None:
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


def _to_response(row: dict[str, Any] | None, delivery: dict[str, Any] | None) -> dict[str, Any]:
    telegram_bound = bool(row and row.get("chat_id") != PENDING_CHAT_ID)
    return {
        "telegram_bound": telegram_bound,
        "chat_id_masked": _mask_chat_id(row.get("chat_id")) if telegram_bound and row else None,
        "alerts_enabled": bool(row.get("alerts_enabled")) if row else True,
        "market_alerts_enabled": bool(row.get("market_alerts_enabled")) if row else True,
        "price_alerts_enabled": bool(row.get("price_alerts_enabled")) if row else True,
        "technical_alerts_enabled": bool(row.get("technical_alerts_enabled")) if row else True,
        "ai_summary_enabled": bool(row.get("ai_summary_enabled")) if row else False,
        "summary_frequency": row.get("summary_frequency") if row else "morning",
        "last_notification_at": delivery["sent_at"].isoformat() if delivery and delivery.get("sent_at") else None,
        "last_notification_status": delivery.get("status") if delivery else None,
    }


def _mask_chat_id(chat_id: str | None) -> str | None:
    if not chat_id:
        return None
    if len(chat_id) <= 6:
        return f"{chat_id[:1]}***{chat_id[-1:]}"
    return f"{chat_id[:3]}***{chat_id[-3:]}"
