from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cache import QuoteCache
from config import load_settings
from models import Candle
from providers import ProviderError, provider_for
from repository import MarketRepository


DEFAULT_SYMBOLS = ["5289.TW", "8299.TW", "3491.TW", "3357.TW"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill selected yfinance symbols into market_ohlcv")
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated yfinance symbols. Default: 5289.TW,8299.TW,3491.TW,3357.TW",
    )
    parser.add_argument("--daily-limit", type=int, default=240)
    parser.add_argument("--hourly-limit", type=int, default=60)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    if not symbols:
        raise SystemExit("No symbols provided")

    settings = load_settings()
    repository = MarketRepository(settings.database_url)
    cache = QuoteCache(settings.redis_url)

    print(f"[backfill:selected] symbols={','.join(symbols)}")
    for symbol in symbols:
        _backfill_one(repository, cache, symbol, "1d", period="1y", limit=args.daily_limit)
        _backfill_one(repository, cache, symbol, "1h", period="60d", limit=args.hourly_limit)


def _backfill_one(repository: MarketRepository, cache: QuoteCache, symbol: str, timeframe: str, period: str, limit: int) -> None:
    provider_name = "yfinance"
    provider = provider_for(provider_name)
    candidates = _candidate_yfinance_symbols(symbol)

    with repository.connect() as conn:
        run_id = repository.start_ingestion_run(conn, provider_name, symbol, timeframe)
        errors: list[str] = []
        try:
            for fetch_symbol in candidates:
                try:
                    fetched_candles = provider.fetch_ohlcv(fetch_symbol, timeframe, period=period, limit=limit)
                    candles = [_normalize_symbol(candle, symbol) for candle in fetched_candles]
                    rows_inserted, rows_updated = repository.upsert_candles(conn, candles)
                    cache.store_latest_snapshot(candles)
                    repository.finish_ingestion_run(
                        conn,
                        run_id,
                        "success",
                        rows_inserted=rows_inserted,
                        rows_updated=rows_updated,
                        message=f"fetch_symbol={fetch_symbol} rows_seen={len(candles)}",
                    )
                    conn.commit()
                    print(
                        "[backfill:success] "
                        f"symbol={symbol} fetch_symbol={fetch_symbol} timeframe={timeframe} "
                        f"rows_seen={len(candles)} rows_inserted={rows_inserted} rows_updated={rows_updated}"
                    )
                    return
                except Exception as exc:
                    errors.append(f"{fetch_symbol}: {type(exc).__name__}: {exc}")

            message = " | ".join(errors)
            repository.record_provider_error(conn, provider_name, symbol, timeframe, "ProviderError", message)
            repository.finish_ingestion_run(conn, run_id, "error", error_count=1, message=message[:2000])
            conn.commit()
            raise ProviderError(message)
        except Exception as exc:
            print(f"[backfill:error] symbol={symbol} timeframe={timeframe} error={type(exc).__name__}: {exc}")


def _candidate_yfinance_symbols(symbol: str) -> list[str]:
    if symbol.endswith(".TW"):
        return [symbol, f"{symbol[:-3]}.TWO"]
    return [symbol]


def _normalize_symbol(candle: Candle, symbol: str) -> Candle:
    return replace(candle, symbol=symbol)


if __name__ == "__main__":
    main()
