from __future__ import annotations

import hashlib
from datetime import date, datetime
import re
from typing import Any

import asyncpg


TRACKING_TIERS = ("catalog", "quote", "daily", "intraday")


def slugify_watchlist(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if normalized:
        return normalized
    digest = hashlib.sha1(value.strip().encode("utf-8")).hexdigest()[:10]
    return f"list-{digest}"


class WatchlistRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def list_watchlists(self) -> list[dict[str, Any]]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT
                  w.id,
                  w.name,
                  w.slug,
                  w.description,
                  w.is_default,
                  w.created_at,
                  w.updated_at,
                  COUNT(wi.id) FILTER (WHERE wi.is_active) AS item_count
                FROM watchlists w
                LEFT JOIN watchlist_items wi ON wi.watchlist_id = w.id
                GROUP BY w.id
                ORDER BY w.is_default DESC, w.name, w.id
                """
            )
            return [_serialize(dict(row)) for row in rows]
        finally:
            await conn.close()

    async def create_watchlist(
        self,
        *,
        name: str,
        slug: str,
        description: str | None,
    ) -> dict[str, Any]:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO watchlists (name, slug, description)
                VALUES ($1, $2, $3)
                RETURNING id, name, slug, description, is_default, created_at, updated_at
                """,
                name,
                slug,
                description,
            )
            if row is None:
                raise RuntimeError("Failed to create watchlist")
            result = _serialize(dict(row))
            result["item_count"] = 0
            return result
        finally:
            await conn.close()

    async def list_items(self, watchlist_id: int) -> list[dict[str, Any]]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT
                  wi.id,
                  wi.watchlist_id,
                  wi.instrument_id,
                  wi.tracking_tier,
                  wi.sort_order,
                  wi.notes,
                  wi.is_active,
                  wi.created_at,
                  wi.updated_at,
                  i.canonical_symbol,
                  i.market,
                  i.exchange,
                  i.security_type,
                  i.name_zh,
                  i.name_en,
                  i.currency,
                  y.provider_symbol AS quote_symbol
                FROM watchlist_items wi
                JOIN instruments i ON i.id = wi.instrument_id
                LEFT JOIN LATERAL (
                  SELECT ips.provider_symbol
                  FROM instrument_provider_symbols ips
                  WHERE ips.instrument_id = i.id
                    AND ips.provider = 'yfinance'
                    AND ips.is_active = true
                  ORDER BY ips.is_primary DESC, ips.id
                  LIMIT 1
                ) y ON true
                WHERE wi.watchlist_id = $1
                  AND wi.is_active = true
                ORDER BY wi.sort_order, wi.id
                """,
                watchlist_id,
            )
            return [_serialize(dict(row)) for row in rows]
        finally:
            await conn.close()

    async def add_item(
        self,
        *,
        watchlist_id: int,
        instrument_id: int,
        tracking_tier: str,
        notes: str | None,
    ) -> dict[str, Any] | None:
        conn = await asyncpg.connect(self.database_url)
        try:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM watchlists WHERE id = $1)",
                watchlist_id,
            )
            if not exists:
                return None
            row = await conn.fetchrow(
                """
                INSERT INTO watchlist_items (
                  watchlist_id, instrument_id, tracking_tier, notes, sort_order
                )
                VALUES (
                  $1, $2, $3, $4,
                  COALESCE(
                    (SELECT MAX(sort_order) + 1 FROM watchlist_items WHERE watchlist_id = $1),
                    0
                  )
                )
                ON CONFLICT (watchlist_id, instrument_id)
                DO UPDATE SET
                  tracking_tier = EXCLUDED.tracking_tier,
                  notes = COALESCE(EXCLUDED.notes, watchlist_items.notes),
                  is_active = true,
                  updated_at = now()
                RETURNING id
                """,
                watchlist_id,
                instrument_id,
                tracking_tier,
                notes,
            )
            if row is None:
                raise RuntimeError("Failed to add watchlist item")
        finally:
            await conn.close()
        items = await self.list_items(watchlist_id)
        return next((item for item in items if item["id"] == int(row["id"])), None)

    async def update_item(
        self,
        *,
        watchlist_id: int,
        item_id: int,
        tracking_tier: str,
        notes: str | None,
    ) -> dict[str, Any] | None:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                UPDATE watchlist_items
                SET tracking_tier = $3,
                    notes = $4,
                    updated_at = now()
                WHERE watchlist_id = $1 AND id = $2 AND is_active = true
                RETURNING id
                """,
                watchlist_id,
                item_id,
                tracking_tier,
                notes,
            )
            if row is None:
                return None
        finally:
            await conn.close()
        items = await self.list_items(watchlist_id)
        return next((item for item in items if item["id"] == item_id), None)

    async def remove_item(self, *, watchlist_id: int, item_id: int) -> bool:
        conn = await asyncpg.connect(self.database_url)
        try:
            result = await conn.execute(
                """
                DELETE FROM watchlist_items
                WHERE watchlist_id = $1 AND id = $2
                """,
                watchlist_id,
                item_id,
            )
            return result == "DELETE 1"
        finally:
            await conn.close()


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    for key, value in tuple(row.items()):
        if isinstance(value, (date, datetime)):
            row[key] = value.isoformat()
    return row
