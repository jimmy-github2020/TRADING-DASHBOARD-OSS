from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from typing import Any, Iterator

import psycopg
from psycopg import Connection

from models import Candle, SignalEvent, SymbolSpec


class MarketRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @contextmanager
    def connect(self) -> Iterator[Connection[tuple]]:
        with psycopg.connect(self.database_url) as conn:
            yield conn

    def upsert_symbol(self, conn: Connection[tuple], symbol: SymbolSpec) -> None:
        conn.execute(
            """
            INSERT INTO symbols (
              symbol, provider, name, asset_class, exchange, currency, timezone, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (symbol, provider)
            DO UPDATE SET
              name = EXCLUDED.name,
              asset_class = EXCLUDED.asset_class,
              exchange = EXCLUDED.exchange,
              currency = EXCLUDED.currency,
              timezone = EXCLUDED.timezone,
              is_active = TRUE,
              updated_at = now()
            """,
            (
                symbol.symbol,
                symbol.provider,
                symbol.name,
                symbol.asset_class,
                symbol.exchange,
                symbol.currency,
                symbol.timezone,
            ),
        )

    def upsert_candles(self, conn: Connection[tuple], candles: Iterable[Candle]) -> tuple[int, int]:
        inserted = 0
        updated = 0
        for candle in candles:
            result = conn.execute(
                """
                INSERT INTO market_ohlcv (
                  time, symbol, timeframe, provider, open, high, low, close, volume
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, timeframe, provider, time)
                DO UPDATE SET
                  open = EXCLUDED.open,
                  high = EXCLUDED.high,
                  low = EXCLUDED.low,
                  close = EXCLUDED.close,
                  volume = EXCLUDED.volume
                WHERE
                  market_ohlcv.open IS DISTINCT FROM EXCLUDED.open OR
                  market_ohlcv.high IS DISTINCT FROM EXCLUDED.high OR
                  market_ohlcv.low IS DISTINCT FROM EXCLUDED.low OR
                  market_ohlcv.close IS DISTINCT FROM EXCLUDED.close OR
                  market_ohlcv.volume IS DISTINCT FROM EXCLUDED.volume
                RETURNING xmax = 0 AS inserted
                """,
                (
                    candle.time,
                    candle.symbol,
                    candle.timeframe,
                    candle.provider,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                ),
            )
            row = result.fetchone()
            if row is None:
                continue
            if bool(row[0]):
                inserted += 1
            else:
                updated += 1
        return inserted, updated

    def start_ingestion_run(
        self,
        conn: Connection[tuple],
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> int:
        row = conn.execute(
            """
            INSERT INTO data_ingestion_runs (provider, symbol, timeframe, status)
            VALUES (%s, %s, %s, 'running')
            RETURNING id
            """,
            (provider, symbol, timeframe),
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to create ingestion run")
        return int(row[0])

    def finish_ingestion_run(
        self,
        conn: Connection[tuple],
        run_id: int,
        status: str,
        rows_inserted: int = 0,
        rows_updated: int = 0,
        error_count: int = 0,
        message: str | None = None,
    ) -> None:
        conn.execute(
            """
            UPDATE data_ingestion_runs
            SET
              finished_at = %s,
              status = %s,
              rows_inserted = %s,
              rows_updated = %s,
              error_count = %s,
              message = %s
            WHERE id = %s
            """,
            (
                datetime.now(timezone.utc),
                status,
                rows_inserted,
                rows_updated,
                error_count,
                message,
                run_id,
            ),
        )

    def record_provider_error(
        self,
        conn: Connection[tuple],
        provider: str,
        symbol: str,
        timeframe: str,
        error_type: str,
        error_message: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO provider_errors (
              provider, symbol, timeframe, error_type, error_message
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (provider, symbol, timeframe, error_type, error_message[:2000]),
        )

    def fetch_recent_candles(
        self,
        conn: Connection[tuple],
        provider: str,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[Candle]:
        rows = conn.execute(
            """
            SELECT time, symbol, timeframe, provider, open, high, low, close, volume
            FROM (
              SELECT time, symbol, timeframe, provider, open, high, low, close, volume
              FROM market_ohlcv
              WHERE provider = %s AND symbol = %s AND timeframe = %s
              ORDER BY time DESC
              LIMIT %s
            ) candles
            ORDER BY time ASC
            """,
            (provider, symbol, timeframe, limit),
        ).fetchall()
        return [
            Candle(
                time=row[0],
                symbol=row[1],
                timeframe=row[2],
                provider=row[3],
                open=float(row[4]),
                high=float(row[5]),
                low=float(row[6]),
                close=float(row[7]),
                volume=float(row[8]) if row[8] is not None else None,
            )
            for row in rows
        ]

    def is_notification_in_cooldown(
        self,
        conn: Connection[tuple],
        event: SignalEvent,
        cooldown_hours: int,
    ) -> bool:
        row = conn.execute(
            """
            SELECT 1
            FROM notification_events
            WHERE event_type = %s
              AND provider = %s
              AND symbol = %s
              AND timeframe = %s
              AND created_at >= now() - (%s || ' hours')::interval
              AND status IN ('sent', 'dry_run')
            LIMIT 1
            """,
            (
                event.event_type,
                event.provider,
                event.symbol,
                event.timeframe,
                str(cooldown_hours),
            ),
        ).fetchone()
        return row is not None

    def record_notification_event(
        self,
        conn: Connection[tuple],
        event: SignalEvent,
        channel: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO notification_events (
              channel, event_type, symbol, provider, timeframe, payload, sent_at, status, error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
            (
                channel,
                event.event_type,
                event.symbol,
                event.provider,
                event.timeframe,
                json.dumps(event.payload, ensure_ascii=False),
                datetime.now(timezone.utc) if status in ("sent", "dry_run") else None,
                status,
                error_message,
            ),
        )

    def sync_instruments(
        self,
        market: str,
        source: str,
        records: Iterable[Any],
    ) -> tuple[int, int]:
        record_list = list(records)
        with self.connect() as conn:
            run_id = self._start_instrument_sync_run(conn, market, source)
            inserted = 0
            updated = 0
            for record in record_list:
                row = conn.execute(
                    """
                    INSERT INTO instruments (
                      canonical_symbol, market, exchange, security_type, name_zh, name_en,
                      currency, timezone, sector, listed_at, listing_status, is_active,
                      source, source_updated_at, updated_at
                    )
                    VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      'active', true, %s, %s, now()
                    )
                    ON CONFLICT (market, canonical_symbol)
                    DO UPDATE SET
                      exchange = EXCLUDED.exchange,
                      security_type = EXCLUDED.security_type,
                      name_zh = COALESCE(EXCLUDED.name_zh, instruments.name_zh),
                      name_en = COALESCE(EXCLUDED.name_en, instruments.name_en),
                      currency = EXCLUDED.currency,
                      timezone = EXCLUDED.timezone,
                      sector = COALESCE(EXCLUDED.sector, instruments.sector),
                      listed_at = COALESCE(EXCLUDED.listed_at, instruments.listed_at),
                      listing_status = 'active',
                      is_active = true,
                      source = EXCLUDED.source,
                      source_updated_at = EXCLUDED.source_updated_at,
                      updated_at = now()
                    RETURNING id, xmax = 0 AS inserted
                    """,
                    (
                        record.canonical_symbol,
                        record.market,
                        record.exchange,
                        record.security_type,
                        record.name_zh,
                        record.name_en,
                        record.currency,
                        record.timezone,
                        record.sector,
                        record.listed_at,
                        record.source,
                        record.source_updated_at,
                    ),
                ).fetchone()
                if row is None:
                    raise RuntimeError(
                        f"Instrument upsert returned no row: {record.canonical_symbol}"
                    )
                instrument_id = int(row[0])
                if bool(row[1]):
                    inserted += 1
                else:
                    updated += 1

                for provider, provider_symbol in record.provider_symbols:
                    conn.execute(
                        """
                        UPDATE instrument_provider_symbols
                        SET is_primary = false,
                            updated_at = now()
                        WHERE instrument_id = %s
                          AND provider = %s
                          AND provider_symbol <> %s
                          AND is_primary = true
                          AND is_active = true
                        """,
                        (instrument_id, provider, provider_symbol),
                    )
                    conn.execute(
                        """
                        INSERT INTO instrument_provider_symbols (
                          instrument_id, provider, provider_symbol, is_primary,
                          is_active, valid_from, metadata, updated_at
                        )
                        VALUES (%s, %s, %s, true, true, %s, %s::jsonb, now())
                        ON CONFLICT (provider, provider_symbol) WHERE is_active = true
                        DO UPDATE SET
                          instrument_id = EXCLUDED.instrument_id,
                          is_primary = true,
                          updated_at = now(),
                          metadata = instrument_provider_symbols.metadata || EXCLUDED.metadata
                        """,
                        (
                            instrument_id,
                            provider,
                            provider_symbol,
                            record.listed_at,
                            json.dumps({"source": source}, ensure_ascii=False),
                        ),
                    )

            self._finish_instrument_sync_run(
                conn,
                run_id,
                status="success",
                rows_seen=len(record_list),
                rows_inserted=inserted,
                rows_updated=updated,
            )
            return inserted, updated

    def record_instrument_sync_failure(
        self,
        market: str,
        source: str,
        message: str,
    ) -> None:
        with self.connect() as conn:
            run_id = self._start_instrument_sync_run(conn, market, source)
            self._finish_instrument_sync_run(
                conn,
                run_id,
                status="failed",
                error_count=1,
                message=message,
            )

    def _start_instrument_sync_run(
        self,
        conn: Connection[tuple],
        market: str,
        source: str,
    ) -> int:
        row = conn.execute(
            """
            INSERT INTO instrument_sync_runs (market, source, status)
            VALUES (%s, %s, 'running')
            RETURNING id
            """,
            (market, source),
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to create instrument sync run")
        return int(row[0])

    def _finish_instrument_sync_run(
        self,
        conn: Connection[tuple],
        run_id: int,
        status: str,
        rows_seen: int = 0,
        rows_inserted: int = 0,
        rows_updated: int = 0,
        error_count: int = 0,
        message: str | None = None,
    ) -> None:
        conn.execute(
            """
            UPDATE instrument_sync_runs
            SET status = %s,
                rows_seen = %s,
                rows_inserted = %s,
                rows_updated = %s,
                error_count = %s,
                message = %s,
                finished_at = now()
            WHERE id = %s
            """,
            (
                status,
                rows_seen,
                rows_inserted,
                rows_updated,
                error_count,
                message,
                run_id,
            ),
        )

    def record_notification_delivery(
        self,
        conn: Connection[tuple],
        chat_id: str,
        notification_type: str,
        message_preview: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO notification_deliveries (
              chat_id, notification_type, message_preview, status, error_message
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                chat_id,
                notification_type,
                message_preview[:500],
                status,
                error_message,
            ),
        )

    def record_notification_runtime_event(
        self,
        conn: Connection[tuple],
        job_name: str | None,
        notification_type: str,
        status: str,
        skip_reason: str | None = None,
        symbol: str | None = None,
        topic: str | None = None,
        message_preview: str | None = None,
        chat_id: str | None = None,
        dedup_key: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self._ensure_notification_observability_tables(conn)
        conn.execute(
            """
            INSERT INTO notification_runtime_events (
              job_name, notification_type, status, skip_reason, symbol, topic,
              message_preview, chat_id, dedup_key, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                job_name,
                notification_type,
                status,
                skip_reason,
                symbol,
                topic,
                (message_preview or "")[:200] if message_preview else None,
                chat_id,
                dedup_key,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    def record_notification_job_run(
        self,
        conn: Connection[tuple],
        job_name: str,
        started_at: datetime,
        finished_at: datetime,
        duration_ms: int,
        targets_scanned: int,
        disabled_skipped_count: int,
        frequency_skipped_count: int,
        triggered_count: int,
        dedup_skipped_count: int,
        sent_count: int,
        error_count: int,
        final_status: str,
        metadata: dict | None = None,
    ) -> None:
        self._ensure_notification_observability_tables(conn)
        conn.execute(
            """
            INSERT INTO notification_job_runs (
              job_name, started_at, finished_at, duration_ms, targets_scanned,
              disabled_skipped_count, frequency_skipped_count, triggered_count,
              dedup_skipped_count, sent_count, error_count, final_status, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                job_name,
                started_at,
                finished_at,
                duration_ms,
                targets_scanned,
                disabled_skipped_count,
                frequency_skipped_count,
                triggered_count,
                dedup_skipped_count,
                sent_count,
                error_count,
                final_status,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    def _ensure_notification_observability_tables(self, conn: Connection[tuple]) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_job_runs (
              id SERIAL PRIMARY KEY,
              job_name VARCHAR(80) NOT NULL,
              started_at TIMESTAMPTZ NOT NULL,
              finished_at TIMESTAMPTZ NOT NULL,
              duration_ms INTEGER NOT NULL,
              targets_scanned INTEGER NOT NULL DEFAULT 0,
              disabled_skipped_count INTEGER NOT NULL DEFAULT 0,
              frequency_skipped_count INTEGER NOT NULL DEFAULT 0,
              triggered_count INTEGER NOT NULL DEFAULT 0,
              dedup_skipped_count INTEGER NOT NULL DEFAULT 0,
              sent_count INTEGER NOT NULL DEFAULT 0,
              error_count INTEGER NOT NULL DEFAULT 0,
              final_status VARCHAR(30) NOT NULL,
              metadata_json JSONB
            )
            """
        )
        conn.execute(
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

    def fetch_active_price_alerts(self, conn: Connection[tuple]) -> list[dict]:
        rows = conn.execute(
            """
            SELECT id, chat_id, symbol, alert_type, threshold, is_active, triggered_at
            FROM price_alerts
            WHERE is_active = TRUE
            ORDER BY created_at ASC
            """
        ).fetchall()
        return [
            {
                "id": row[0],
                "chat_id": row[1],
                "symbol": row[2],
                "alert_type": row[3],
                "threshold": float(row[4]),
                "is_active": row[5],
                "triggered_at": row[6],
            }
            for row in rows
        ]

    def fetch_tracked_instruments(self, limit: int = 500) -> list[dict[str, str]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT ON (i.id)
                  i.canonical_symbol,
                  i.market,
                  wi.tracking_tier,
                  ips.provider,
                  ips.provider_symbol
                FROM watchlist_items wi
                JOIN instruments i
                  ON i.id = wi.instrument_id
                 AND i.is_active = true
                JOIN instrument_provider_symbols ips
                  ON ips.instrument_id = i.id
                 AND ips.provider = 'yfinance'
                 AND ips.is_active = true
                WHERE wi.is_active = true
                  AND wi.tracking_tier <> 'catalog'
                ORDER BY
                  i.id,
                  CASE wi.tracking_tier
                    WHEN 'intraday' THEN 4
                    WHEN 'daily' THEN 3
                    WHEN 'quote' THEN 2
                    ELSE 1
                  END DESC,
                  ips.is_primary DESC,
                  wi.id
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "canonical_symbol": str(row[0]),
                "market": str(row[1]),
                "tracking_tier": str(row[2]),
                "provider": str(row[3]),
                "provider_symbol": str(row[4]),
            }
            for row in rows
        ]

    def update_price_alert_triggered(self, conn: Connection[tuple], alert_id: int) -> None:
        conn.execute(
            """
            UPDATE price_alerts
            SET triggered_at = now(), is_active = FALSE
            WHERE id = %s
            """,
            (alert_id,),
        )

    def fetch_alerts_enabled(self, conn: Connection[tuple], chat_id: str) -> bool:
        self._ensure_notification_settings_columns(conn)
        row = conn.execute(
            """
            SELECT alerts_enabled
            FROM notification_settings
            WHERE chat_id = %s
            """,
            (chat_id,),
        ).fetchone()
        if row is None:
            return False
        return bool(row[0])

    def fetch_notification_dry_run(self, conn: Connection[tuple], default: bool) -> bool:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
              key VARCHAR(80) PRIMARY KEY,
              value JSONB NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'notification_dry_run'"
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('notification_dry_run', %s::jsonb, now())
                ON CONFLICT (key) DO NOTHING
                """,
                ("true" if default else "false",),
            )
            return default
        value = row[0]
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() == "true"
        return bool(value)

    def fetch_notification_settings(self, conn: Connection[tuple], chat_id: str) -> dict | None:
        self._ensure_notification_settings_columns(conn)
        row = conn.execute(
            """
            SELECT chat_id, alerts_enabled, market_alerts_enabled, price_alerts_enabled,
                   technical_alerts_enabled, ai_summary_enabled, summary_frequency, updated_at
            FROM notification_settings
            WHERE chat_id = %s
            """,
            (chat_id,),
        ).fetchone()
        return _notification_settings_row(row) if row else None

    def fetch_notification_targets(self, conn: Connection[tuple]) -> list[dict]:
        self._ensure_notification_settings_columns(conn)
        rows = conn.execute(
            """
            SELECT chat_id, alerts_enabled, market_alerts_enabled, price_alerts_enabled,
                   technical_alerts_enabled, ai_summary_enabled, summary_frequency, updated_at
            FROM notification_settings
            WHERE chat_id <> 'web_pending'
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
        return [_notification_settings_row(row) for row in rows]

    def _ensure_notification_settings_columns(self, conn: Connection[tuple]) -> None:
        conn.execute(
            """
            ALTER TABLE notification_settings
              ADD COLUMN IF NOT EXISTS market_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
              ADD COLUMN IF NOT EXISTS price_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
              ADD COLUMN IF NOT EXISTS technical_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
              ADD COLUMN IF NOT EXISTS ai_summary_enabled BOOLEAN NOT NULL DEFAULT false,
              ADD COLUMN IF NOT EXISTS summary_frequency VARCHAR(20) NOT NULL DEFAULT 'morning'
            """
        )

    def fetch_active_strategies(self, conn: Connection[tuple]) -> list[dict]:
        rows = conn.execute(
            """
            SELECT id::text, name, conditions, is_active, created_at
            FROM strategies
            WHERE is_active = TRUE
            ORDER BY created_at ASC
            """
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "conditions": row[2],
                "is_active": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]

    def fetch_active_symbols(self, conn: Connection[tuple]) -> list[SymbolSpec]:
        rows = conn.execute(
            """
            SELECT symbol, provider, name, asset_class, exchange, currency, timezone
            FROM symbols
            WHERE is_active = TRUE
            ORDER BY provider, symbol
            """
        ).fetchall()
        return [
            SymbolSpec(
                symbol=row[0],
                provider=row[1],
                name=row[2] or row[0],
                asset_class=row[3],
                exchange=row[4],
                currency=row[5],
                timezone=row[6],
            )
            for row in rows
        ]

    def insert_signal(
        self,
        conn: Connection[tuple],
        symbol: str,
        strategy_id: str,
        direction: str,
        price: float,
        metadata: dict,
    ) -> None:
        conn.execute(
            """
            INSERT INTO signals (symbol, strategy_id, direction, price, metadata)
            VALUES (%s, %s::uuid, %s, %s, %s::jsonb)
            """,
            (
                symbol,
                strategy_id,
                direction,
                price,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )


def _notification_settings_row(row: tuple) -> dict:
    return {
        "chat_id": row[0],
        "alerts_enabled": bool(row[1]),
        "market_alerts_enabled": bool(row[2]),
        "price_alerts_enabled": bool(row[3]),
        "technical_alerts_enabled": bool(row[4]),
        "ai_summary_enabled": bool(row[5]),
        "summary_frequency": row[6] or "morning",
        "updated_at": row[7],
    }
