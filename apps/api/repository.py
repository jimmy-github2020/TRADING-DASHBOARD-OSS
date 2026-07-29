from __future__ import annotations

import json
from datetime import date

import asyncpg


class MarketRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def fetch_symbols(self) -> list[dict]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT symbol, provider, name, asset_class, exchange, currency, timezone, is_active
                FROM symbols
                WHERE is_active = TRUE
                ORDER BY asset_class, provider, symbol
                """
            )
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        provider: str,
        limit: int,
    ) -> list[dict]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT time, symbol, timeframe, provider, open, high, low, close, volume
                FROM (
                  SELECT time, symbol, timeframe, provider, open, high, low, close, volume
                  FROM market_ohlcv
                  WHERE symbol = $1 AND timeframe = $2 AND provider = $3
                  ORDER BY time DESC
                  LIMIT $4
                ) candles
                ORDER BY time ASC
                """,
                symbol,
                timeframe,
                provider,
                limit,
            )
            return [_serialize_candle(dict(row)) for row in rows]
        finally:
            await conn.close()

    async def fetch_latest_snapshots(self) -> list[dict]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (symbol, timeframe, provider)
                  time, symbol, timeframe, provider, open, high, low, close, volume
                FROM market_ohlcv
                ORDER BY symbol, timeframe, provider, time DESC
                """
            )
            return [_candle_to_snapshot(dict(row), source="db") for row in rows]
        finally:
            await conn.close()

    async def fetch_market_quotes(self, symbols: list[str], timeframe: str = "1d") -> list[dict]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT time, symbol, provider, close, volume
                FROM (
                  SELECT time, symbol, provider, close, volume,
                         row_number() OVER (PARTITION BY symbol ORDER BY time DESC) AS row_number
                  FROM market_ohlcv
                  WHERE symbol = ANY($1::text[])
                    AND timeframe = $2
                ) ranked
                WHERE row_number <= 2
                ORDER BY symbol, time DESC
                """,
                symbols,
                timeframe,
            )
            grouped: dict[str, list[dict]] = {symbol: [] for symbol in symbols}
            for row in rows:
                item = dict(row)
                grouped.setdefault(item["symbol"], []).append(item)

            quotes: list[dict] = []
            for symbol in symbols:
                candles = grouped.get(symbol, [])
                latest = candles[0] if candles else None
                previous = candles[1] if len(candles) > 1 else None
                if latest is None:
                    quotes.append(
                        {
                            "symbol": symbol,
                            "provider": None,
                            "price": None,
                            "change": None,
                            "change_pct": None,
                            "volume": None,
                            "candle_time": None,
                            "source": "missing",
                        }
                    )
                    continue

                price = float(latest["close"])
                previous_price = float(previous["close"]) if previous is not None else None
                change = price - previous_price if previous_price is not None else None
                change_pct = (change / previous_price * 100) if previous_price not in (None, 0) and change is not None else None
                quotes.append(
                    {
                        "symbol": symbol,
                        "provider": latest["provider"],
                        "price": price,
                        "change": change,
                        "change_pct": change_pct,
                        "volume": float(latest["volume"]) if latest["volume"] is not None else None,
                        "candle_time": latest["time"].isoformat(),
                        "source": "db",
                    }
                )
            return quotes
        finally:
            await conn.close()

    async def fetch_portfolio_holdings(self) -> list[dict]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT id, symbol, name_zh, name_en, category, shares, cost_basis,
                       market_value, pnl, pnl_pct, owned, updated_at
                FROM portfolio_holdings
                ORDER BY
                  CASE category WHEN 'ETF' THEN 1 WHEN '股票' THEN 2 ELSE 3 END,
                  symbol
                """
            )
            return [_serialize_portfolio_holding(dict(row)) for row in rows]
        finally:
            await conn.close()

    async def fetch_daily_note(self, note_date: date) -> dict | None:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT id, note_date, content, created_at, updated_at
                FROM daily_notes
                WHERE note_date = $1
                """,
                note_date,
            )
            return _serialize_daily_note(dict(row)) if row else None
        finally:
            await conn.close()

    async def upsert_daily_note(self, note_date: date, content: str) -> dict:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO daily_notes (note_date, content)
                VALUES ($1, $2)
                ON CONFLICT (note_date) DO UPDATE
                SET content = EXCLUDED.content
                RETURNING id, note_date, content, created_at, updated_at
                """,
                note_date,
                content,
            )
            return _serialize_daily_note(dict(row))
        finally:
            await conn.close()

    async def upsert_portfolio_holding(
        self,
        symbol: str,
        name_zh: str | None = None,
        name_en: str | None = None,
        category: str = "觀察",
        owned: bool = False,
    ) -> dict:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO portfolio_holdings (symbol, name_zh, name_en, category, owned, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (symbol) DO UPDATE
                SET name_zh = COALESCE(EXCLUDED.name_zh, portfolio_holdings.name_zh),
                    name_en = COALESCE(EXCLUDED.name_en, portfolio_holdings.name_en),
                    category = EXCLUDED.category,
                    owned = EXCLUDED.owned,
                    updated_at = NOW()
                RETURNING id, symbol, name_zh, name_en, category, shares, cost_basis,
                          market_value, pnl, pnl_pct, owned, updated_at
                """,
                symbol,
                name_zh,
                name_en,
                category,
                owned,
            )
            return _serialize_portfolio_holding(dict(row))
        finally:
            await conn.close()

    async def fetch_strategies(self) -> list[dict]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT id::text, name, conditions, is_active, created_at
                FROM strategies
                ORDER BY created_at DESC
                """
            )
            return [_serialize_strategy(dict(row)) for row in rows]
        finally:
            await conn.close()

    async def create_strategy(self, name: str, conditions: dict) -> dict:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO strategies (name, conditions)
                VALUES ($1, $2::jsonb)
                RETURNING id::text, name, conditions, is_active, created_at
                """,
                name,
                json.dumps(conditions),
            )
            return _serialize_strategy(dict(row))
        finally:
            await conn.close()

    async def update_strategy_active(self, strategy_id: str, is_active: bool) -> dict:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                UPDATE strategies
                SET is_active = $2
                WHERE id = $1::uuid
                RETURNING id::text, name, conditions, is_active, created_at
                """,
                strategy_id,
                is_active,
            )
            if row is None:
                raise ValueError("Strategy not found")
            return _serialize_strategy(dict(row))
        finally:
            await conn.close()

    async def delete_strategy(self, strategy_id: str) -> None:
        conn = await asyncpg.connect(self.database_url)
        try:
            await conn.execute("DELETE FROM strategies WHERE id = $1::uuid", strategy_id)
        finally:
            await conn.close()

    async def fetch_signals(self, strategy_id: str | None = None, limit: int = 100) -> list[dict]:
        conn = await asyncpg.connect(self.database_url)
        try:
            if strategy_id:
                rows = await conn.fetch(
                    """
                    SELECT s.id::text, s.symbol, s.strategy_id::text, st.name AS strategy_name,
                           s.triggered_at, s.direction, s.price, s.metadata
                    FROM signals s
                    JOIN strategies st ON st.id = s.strategy_id
                    WHERE s.strategy_id = $1::uuid
                    ORDER BY s.triggered_at DESC
                    LIMIT $2
                    """,
                    strategy_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT s.id::text, s.symbol, s.strategy_id::text, st.name AS strategy_name,
                           s.triggered_at, s.direction, s.price, s.metadata
                    FROM signals s
                    JOIN strategies st ON st.id = s.strategy_id
                    ORDER BY s.triggered_at DESC
                    LIMIT $1
                    """,
                    limit,
                )
            return [_serialize_signal(dict(row)) for row in rows]
        finally:
            await conn.close()

    async def fetch_strategy(self, strategy_id: str) -> dict | None:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT id::text, name, conditions, is_active, created_at
                FROM strategies
                WHERE id = $1::uuid
                """,
                strategy_id,
            )
            return _serialize_strategy(dict(row)) if row else None
        finally:
            await conn.close()

    async def fetch_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        start_date: date,
        end_date: date,
        provider: str = "yfinance",
    ) -> list[dict]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT time, symbol, timeframe, provider, open, high, low, close, volume
                FROM market_ohlcv
                WHERE symbol = $1
                  AND timeframe = $2
                  AND provider = $3
                  AND time::date >= $4::date
                  AND time::date <= $5::date
                ORDER BY time ASC
                """,
                symbol,
                timeframe,
                provider,
                start_date,
                end_date,
            )
            return [_serialize_candle(dict(row)) for row in rows]
        finally:
            await conn.close()

    async def insert_backtest_result(self, result: dict) -> dict:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO backtest_results (
                  id, strategy_id, symbols, start_date, end_date, timeframe,
                  initial_capital, commission, total_return_pct, annual_return_pct,
                  sharpe_ratio, max_drawdown_pct, win_rate, total_trades,
                  avg_holding_days, profit_factor, equity_curve, trades
                )
                VALUES (
                  $1::uuid, $2, $3::text[], $4::date, $5::date, $6,
                  $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                  $17::jsonb, $18::jsonb
                )
                RETURNING *
                """,
                result["id"],
                result["strategy_id"],
                result["symbols"],
                date.fromisoformat(result["start_date"]),
                date.fromisoformat(result["end_date"]),
                result["timeframe"],
                result["initial_capital"],
                result["commission"],
                result["total_return_pct"],
                result["annual_return_pct"],
                result["sharpe_ratio"],
                result["max_drawdown_pct"],
                result["win_rate"],
                result["total_trades"],
                result["avg_holding_days"],
                result["profit_factor"],
                json.dumps(result["equity_curve"]),
                json.dumps(result["trades"]),
            )
            return _serialize_backtest(dict(row))
        finally:
            await conn.close()

    async def fetch_backtest_result(self, backtest_id: str) -> dict | None:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT br.*, st.name AS strategy_name
                FROM backtest_results br
                LEFT JOIN strategies st ON st.id::text = br.strategy_id
                WHERE br.id = $1::uuid
                """,
                backtest_id,
            )
            return _serialize_backtest(dict(row)) if row else None
        finally:
            await conn.close()

    async def fetch_backtest_results(self, limit: int = 20) -> list[dict]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT br.*, st.name AS strategy_name
                FROM backtest_results br
                LEFT JOIN strategies st ON st.id::text = br.strategy_id
                ORDER BY br.created_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [_serialize_backtest(dict(row), compact=True) for row in rows]
        finally:
            await conn.close()

    async def fetch_recent_closes_for_symbols(self, symbols: list[str], limit: int = 6) -> dict[str, list[dict]]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT time, symbol, close, volume
                FROM (
                  SELECT time, symbol, close, volume,
                         row_number() OVER (PARTITION BY symbol ORDER BY time DESC) AS row_number
                  FROM market_ohlcv
                  WHERE symbol = ANY($1::text[])
                    AND timeframe = '1d'
                    AND provider = 'yfinance'
                ) ranked
                WHERE row_number <= $2
                ORDER BY symbol, time ASC
                """,
                symbols,
                limit,
            )
            result: dict[str, list[dict]] = {symbol: [] for symbol in symbols}
            for row in rows:
                item = dict(row)
                result.setdefault(item["symbol"], []).append(
                    {
                        "time": item["time"].isoformat(),
                        "close": float(item["close"]),
                        "volume": float(item["volume"]) if item["volume"] is not None else None,
                    }
                )
            return result
        finally:
            await conn.close()

    async def insert_ai_market_brief(self, brief_text: str, data_snapshot: dict, model: str, tokens_used: int | None) -> dict:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO ai_market_briefs (brief_text, data_snapshot, model, tokens_used)
                VALUES ($1, $2::jsonb, $3, $4)
                RETURNING id::text, brief_text, data_snapshot, model, tokens_used, created_at
                """,
                brief_text,
                json.dumps(data_snapshot, ensure_ascii=False),
                model,
                tokens_used,
            )
            return _serialize_ai_market_brief(dict(row))
        finally:
            await conn.close()

    async def fetch_latest_ai_market_brief(self) -> dict | None:
        conn = await asyncpg.connect(self.database_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT id::text, brief_text, data_snapshot, model, tokens_used, created_at
                FROM ai_market_briefs
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            return _serialize_ai_market_brief(dict(row)) if row else None
        finally:
            await conn.close()

    async def fetch_ai_market_briefs(self, limit: int = 5) -> list[dict]:
        conn = await asyncpg.connect(self.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT id::text, brief_text, data_snapshot, model, tokens_used, created_at
                FROM ai_market_briefs
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [_serialize_ai_market_brief(dict(row)) for row in rows]
        finally:
            await conn.close()


def _serialize_candle(row: dict) -> dict:
    row["time"] = row["time"].isoformat()
    return row


def _serialize_portfolio_holding(row: dict) -> dict:
    row["updated_at"] = row["updated_at"].isoformat()
    for key in ("cost_basis", "market_value", "pnl", "pnl_pct"):
        if row.get(key) is not None:
            row[key] = float(row[key])
    return row


def _serialize_daily_note(row: dict) -> dict:
    row["note_date"] = row["note_date"].isoformat()
    row["created_at"] = row["created_at"].isoformat()
    row["updated_at"] = row["updated_at"].isoformat()
    return row


def _serialize_strategy(row: dict) -> dict:
    if isinstance(row.get("conditions"), str):
        row["conditions"] = json.loads(row["conditions"])
    row["created_at"] = row["created_at"].isoformat()
    return row


def _serialize_signal(row: dict) -> dict:
    if isinstance(row.get("metadata"), str):
        row["metadata"] = json.loads(row["metadata"])
    row["triggered_at"] = row["triggered_at"].isoformat()
    row["price"] = float(row["price"])
    return row


def _serialize_backtest(row: dict, compact: bool = False) -> dict:
    for key in (
        "initial_capital",
        "commission",
        "total_return_pct",
        "annual_return_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "win_rate",
        "avg_holding_days",
        "profit_factor",
    ):
        if row.get(key) is not None:
            row[key] = float(row[key])
    row["id"] = str(row["id"])
    row["start_date"] = row["start_date"].isoformat()
    row["end_date"] = row["end_date"].isoformat()
    row["created_at"] = row["created_at"].isoformat()
    if "created_at" in row and row.get("strategy_name") is None:
        row["strategy_name"] = "Unknown strategy"
    if isinstance(row.get("equity_curve"), str):
        row["equity_curve"] = json.loads(row["equity_curve"])
    if isinstance(row.get("trades"), str):
        row["trades"] = json.loads(row["trades"])
    if compact:
        row["equity_curve"] = []
        row["trades"] = []
    return row


def _serialize_ai_market_brief(row: dict) -> dict:
    if isinstance(row.get("data_snapshot"), str):
        row["data_snapshot"] = json.loads(row["data_snapshot"])
    row["created_at"] = row["created_at"].isoformat()
    return row


def _candle_to_snapshot(row: dict, source: str) -> dict:
    return {
        "symbol": row["symbol"],
        "provider": row["provider"],
        "timeframe": row["timeframe"],
        "price": row["close"],
        "change": None,
        "change_pct": None,
        "volume": row["volume"],
        "candle_time": row["time"].isoformat(),
        "cached_at": None,
        "source": source,
    }
