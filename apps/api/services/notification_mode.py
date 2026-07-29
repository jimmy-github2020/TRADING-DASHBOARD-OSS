from __future__ import annotations

from typing import Any

import asyncpg


SETTING_KEY = "notification_dry_run"


async def get_notification_mode(database_url: str) -> dict[str, Any]:
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_table(conn)
        dry_run = await _fetch_dry_run(conn)
        return _mode_response(dry_run)
    finally:
        await conn.close()


async def update_notification_mode(database_url: str, *, dry_run: bool) -> dict[str, Any]:
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_table(conn)
        old_dry_run = await _fetch_dry_run(conn)
        await conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ($1, $2::jsonb, now())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = now()
            """,
            SETTING_KEY,
            "true" if dry_run else "false",
        )
        await _record_mode_change(conn, old_dry_run=old_dry_run, new_dry_run=dry_run)
        return _mode_response(dry_run)
    finally:
        await conn.close()


async def _fetch_dry_run(conn: asyncpg.Connection) -> bool:
    row = await conn.fetchrow("SELECT value FROM app_settings WHERE key = $1", SETTING_KEY)
    if row is None:
        await conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ($1, 'true'::jsonb, now())
            ON CONFLICT (key) DO NOTHING
            """,
            SETTING_KEY,
        )
        return True
    return _jsonb_bool(row["value"])


async def _record_mode_change(conn: asyncpg.Connection, *, old_dry_run: bool, new_dry_run: bool) -> None:
    await _ensure_runtime_events(conn)
    await conn.execute(
        """
        INSERT INTO notification_runtime_events (
          job_name, notification_type, status, skip_reason, topic, message_preview, metadata_json
        )
        VALUES (
          'manual_mode_change', 'system_mode_change', 'updated', NULL, '系統模式',
          $1, jsonb_build_object('old_mode', $2::text, 'new_mode', $3::text)
        )
        """,
        f"系統模式已切換為 {_mode_name(new_dry_run)}",
        _mode_name(old_dry_run),
        _mode_name(new_dry_run),
    )


async def _ensure_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
          key VARCHAR(80) PRIMARY KEY,
          value JSONB NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


async def _ensure_runtime_events(conn: asyncpg.Connection) -> None:
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


def _jsonb_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _mode_response(dry_run: bool) -> dict[str, Any]:
    return {"mode": _mode_name(dry_run), "dry_run": dry_run}


def _mode_name(dry_run: bool) -> str:
    return "dry_run" if dry_run else "live"
