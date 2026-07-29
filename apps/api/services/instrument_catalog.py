from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import asyncpg


class InstrumentCatalogRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def list_instruments(
        self,
        *,
        query: str | None = None,
        market: str | None = None,
        exchange: str | None = None,
        security_type: str | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        filters, values = _build_filters(
            query=query,
            market=market,
            exchange=exchange,
            security_type=security_type,
            active_only=active_only,
        )
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        limit_position = len(values) + 1
        offset_position = len(values) + 2

        conn = await asyncpg.connect(self.database_url)
        try:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM instruments i {where_clause}",
                *values,
            )
            rows = await conn.fetch(
                f"""
                SELECT
                  i.id,
                  i.canonical_symbol,
                  i.market,
                  i.exchange,
                  i.security_type,
                  i.name_zh,
                  i.name_en,
                  i.currency,
                  i.timezone,
                  i.sector,
                  i.industry,
                  i.listing_status,
                  i.listed_at,
                  i.delisted_at,
                  i.is_active,
                  i.source,
                  i.source_updated_at,
                  i.created_at,
                  i.updated_at,
                  COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'provider', ips.provider,
                        'symbol', ips.provider_symbol,
                        'is_primary', ips.is_primary,
                        'is_active', ips.is_active
                      )
                      ORDER BY ips.provider, ips.provider_symbol
                    ) FILTER (WHERE ips.id IS NOT NULL),
                    '[]'::jsonb
                  ) AS provider_symbols
                FROM instruments i
                LEFT JOIN instrument_provider_symbols ips
                  ON ips.instrument_id = i.id
                {where_clause}
                GROUP BY i.id
                ORDER BY i.market, i.exchange, i.canonical_symbol
                LIMIT ${limit_position}
                OFFSET ${offset_position}
                """,
                *values,
                limit,
                offset,
            )
            return [_serialize_instrument(dict(row)) for row in rows], int(total or 0)
        finally:
            await conn.close()

    async def get_instrument(self, instrument_id: int) -> dict[str, Any] | None:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT
                  i.id,
                  i.canonical_symbol,
                  i.market,
                  i.exchange,
                  i.security_type,
                  i.name_zh,
                  i.name_en,
                  i.currency,
                  i.timezone,
                  i.sector,
                  i.industry,
                  i.listing_status,
                  i.listed_at,
                  i.delisted_at,
                  i.is_active,
                  i.source,
                  i.source_updated_at,
                  i.created_at,
                  i.updated_at,
                  COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'provider', ips.provider,
                        'symbol', ips.provider_symbol,
                        'is_primary', ips.is_primary,
                        'is_active', ips.is_active,
                        'valid_from', ips.valid_from,
                        'valid_to', ips.valid_to,
                        'metadata', ips.metadata
                      )
                      ORDER BY ips.provider, ips.provider_symbol
                    ) FILTER (WHERE ips.id IS NOT NULL),
                    '[]'::jsonb
                  ) AS provider_symbols
                FROM instruments i
                LEFT JOIN instrument_provider_symbols ips
                  ON ips.instrument_id = i.id
                WHERE i.id = $1
                GROUP BY i.id
                """,
                instrument_id,
            )
            return _serialize_instrument(dict(row)) if row else None
        finally:
            await conn.close()

    async def resolve_provider_symbol(
        self,
        provider: str,
        provider_symbol: str,
    ) -> dict[str, Any] | None:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT
                  i.id,
                  i.canonical_symbol,
                  i.market,
                  i.exchange,
                  i.security_type,
                  i.name_zh,
                  i.name_en,
                  i.currency,
                  i.timezone,
                  i.sector,
                  i.industry,
                  i.listing_status,
                  i.listed_at,
                  i.delisted_at,
                  i.is_active,
                  i.source,
                  i.source_updated_at,
                  i.created_at,
                  i.updated_at,
                  jsonb_build_array(
                    jsonb_build_object(
                      'provider', ips.provider,
                      'symbol', ips.provider_symbol,
                      'is_primary', ips.is_primary,
                      'is_active', ips.is_active,
                      'valid_from', ips.valid_from,
                      'valid_to', ips.valid_to,
                      'metadata', ips.metadata
                    )
                  ) AS provider_symbols
                FROM instrument_provider_symbols ips
                JOIN instruments i ON i.id = ips.instrument_id
                WHERE LOWER(ips.provider) = LOWER($1)
                  AND UPPER(ips.provider_symbol) = UPPER($2)
                  AND ips.is_active = true
                """,
                provider.strip(),
                provider_symbol.strip(),
            )
            return _serialize_instrument(dict(row)) if row else None
        finally:
            await conn.close()

    async def get_catalog_stats(self) -> dict[str, Any]:
        conn = await asyncpg.connect(self.database_url)
        try:
            catalog_rows = await conn.fetch(
                """
                SELECT market, security_type, COUNT(*) AS count
                FROM instruments
                WHERE is_active = true
                GROUP BY market, security_type
                ORDER BY market, security_type
                """
            )
            tier_rows = await conn.fetch(
                """
                WITH effective_tiers AS (
                  SELECT
                    instrument_id,
                    MAX(
                      CASE tracking_tier
                        WHEN 'intraday' THEN 4
                        WHEN 'daily' THEN 3
                        WHEN 'quote' THEN 2
                        ELSE 1
                      END
                    ) AS tier_rank
                  FROM watchlist_items
                  WHERE is_active = true
                  GROUP BY instrument_id
                )
                SELECT
                  CASE tier_rank
                    WHEN 4 THEN 'intraday'
                    WHEN 3 THEN 'daily'
                    WHEN 2 THEN 'quote'
                    ELSE 'catalog'
                  END AS tracking_tier,
                  COUNT(*) AS count
                FROM effective_tiers
                GROUP BY tier_rank
                ORDER BY tier_rank
                """
            )
            sync_rows = await conn.fetch(
                """
                SELECT source, status, rows_seen, rows_inserted, rows_updated,
                       error_count, message, started_at, finished_at
                FROM instrument_sync_runs
                ORDER BY started_at DESC
                LIMIT 8
                """
            )
            storage = await conn.fetchrow(
                """
                SELECT
                  COALESCE(pg_total_relation_size(to_regclass('instruments')), 0)
                    + COALESCE(pg_total_relation_size(to_regclass('instrument_provider_symbols')), 0)
                    + COALESCE(pg_total_relation_size(to_regclass('watchlists')), 0)
                    + COALESCE(pg_total_relation_size(to_regclass('watchlist_items')), 0)
                    AS catalog_bytes,
                  COALESCE(pg_total_relation_size(to_regclass('market_ohlcv')), 0)
                    AS ohlcv_bytes
                """
            )
        finally:
            await conn.close()

        tiers = {str(row["tracking_tier"]): int(row["count"]) for row in tier_rows}
        projected_rows = (
            tiers.get("quote", 0) * 5
            + tiers.get("daily", 0) * 260
            + tiers.get("intraday", 0) * 460
        )
        return {
            "catalog": [
                {
                    "market": str(row["market"]),
                    "security_type": str(row["security_type"]),
                    "count": int(row["count"]),
                }
                for row in catalog_rows
            ],
            "tracking_tiers": tiers,
            "storage": {
                "catalog_bytes": int(storage["catalog_bytes"] if storage else 0),
                "ohlcv_bytes": int(storage["ohlcv_bytes"] if storage else 0),
                "projected_tracked_rows": projected_rows,
                "projected_bytes_conservative": projected_rows * 768,
            },
            "recent_sync_runs": [_serialize_instrument(dict(row)) for row in sync_rows],
        }


def _build_filters(
    *,
    query: str | None,
    market: str | None,
    exchange: str | None,
    security_type: str | None,
    active_only: bool,
) -> tuple[list[str], list[Any]]:
    filters: list[str] = []
    values: list[Any] = []

    normalized_query = query.strip() if query else ""
    if normalized_query:
        values.append(normalized_query)
        position = len(values)
        filters.append(
            "("
            f"i.canonical_symbol ILIKE '%' || ${position} || '%' "
            f"OR COALESCE(i.name_zh, '') ILIKE '%' || ${position} || '%' "
            f"OR COALESCE(i.name_en, '') ILIKE '%' || ${position} || '%'"
            ")"
        )

    for column, value in (
        ("market", market),
        ("exchange", exchange),
        ("security_type", security_type),
    ):
        normalized_value = value.strip() if value else ""
        if not normalized_value:
            continue
        values.append(normalized_value)
        filters.append(f"LOWER(i.{column}) = LOWER(${len(values)})")

    if active_only:
        filters.append("i.is_active = true")

    return filters, values


def _serialize_instrument(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("listed_at", "delisted_at", "source_updated_at", "created_at", "updated_at"):
        value = row.get(key)
        if isinstance(value, (date, datetime)):
            row[key] = value.isoformat()

    provider_symbols = row.get("provider_symbols")
    if isinstance(provider_symbols, str):
        try:
            provider_symbols = json.loads(provider_symbols)
        except json.JSONDecodeError:
            provider_symbols = []
    if not isinstance(provider_symbols, list):
        provider_symbols = []
    for item in provider_symbols:
        for key in ("valid_from", "valid_to"):
            value = item.get(key)
            if isinstance(value, (date, datetime)):
                item[key] = value.isoformat()
    row["provider_symbols"] = provider_symbols
    return row
