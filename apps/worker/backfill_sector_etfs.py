from __future__ import annotations

import time
from collections.abc import Iterable

import psycopg
from psycopg import Connection

from config import load_settings
from models import Candle
from providers import YFinanceProvider


SYMBOLS = [
    "XLK",
    "XLF",
    "XLV",
    "XLE",
    "XLY",
    "XLP",
    "XLI",
    "XLB",
    "XLU",
    "XLRE",
    "XLC",
    "SPY",
    "2330.TW",
    "2882.TW",
]

TIMEFRAME = "1d"
PROVIDER = "yfinance"
PERIOD = "180d"
LIMIT = 180
MAX_ATTEMPTS = 3


def main() -> None:
    settings = load_settings()
    provider = YFinanceProvider()

    with psycopg.connect(settings.database_url) as conn:
        for symbol in SYMBOLS:
            try:
                candles = fetch_with_retry(provider, symbol)
                inserted = insert_candles(conn, candles)
                conn.commit()
                print(
                    f"[backfill:success] symbol={symbol} rows_seen={len(candles)} "
                    f"rows_inserted={inserted}"
                )
            except Exception as exc:
                conn.rollback()
                print(f"[backfill:error] symbol={symbol} error={type(exc).__name__}: {exc}")


def fetch_with_retry(provider: YFinanceProvider, symbol: str) -> list[Candle]:
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return provider.fetch_ohlcv(symbol=symbol, timeframe=TIMEFRAME, period=PERIOD, limit=LIMIT)
        except Exception as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                delay = 2 ** (attempt - 1)
                print(f"[backfill:retry] symbol={symbol} attempt={attempt} delay_seconds={delay}")
                time.sleep(delay)
    raise RuntimeError(f"Failed to fetch {symbol} after {MAX_ATTEMPTS} attempts") from last_error


def insert_candles(conn: Connection[tuple], candles: Iterable[Candle]) -> int:
    inserted = 0
    for candle in candles:
        result = conn.execute(
            """
            INSERT INTO market_ohlcv (
              time, symbol, open, high, low, close, volume, timeframe, provider
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, timeframe, provider, time)
            DO NOTHING
            RETURNING 1
            """,
            (
                candle.time,
                candle.symbol,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                TIMEFRAME,
                PROVIDER,
            ),
        )
        if result.fetchone() is not None:
            inserted += 1
    return inserted


if __name__ == "__main__":
    main()
