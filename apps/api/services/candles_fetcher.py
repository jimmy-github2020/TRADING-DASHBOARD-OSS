from __future__ import annotations

import asyncio
from time import monotonic
from typing import Literal, TypedDict

import pandas as pd
import yfinance as yf

MarketCandleInterval = Literal["1d", "1wk", "1mo"]
MarketCandleRange = Literal["1mo", "3mo", "6mo", "1y", "2y", "5y", "1m", "1w", "1d"]
CACHE_TTL_SECONDS = 300

INTERVAL_MAP: dict[MarketCandleInterval, str] = {
    "1d": "1d",
    "1wk": "1wk",
    "1mo": "1mo",
}

RANGE_MAP: dict[MarketCandleRange, str] = {
    "1mo": "1mo",
    "2y": "2y",
    "5y": "5y",
    "1y": "1y",
    "6mo": "6mo",
    "3mo": "3mo",
    "1m": "1mo",
    "1w": "5d",
    "1d": "1d",
}

_CACHE: dict[tuple[str, MarketCandleInterval, MarketCandleRange], tuple[float, "MarketCandlesResult"]] = {}


class Candle(TypedDict):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float | int | None


class MarketCandlesResult(TypedDict):
    symbol: str
    interval: str
    candles: list[Candle]
    data: list[Candle]
    error_message: str | None


def _to_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_volume(value: object) -> float | int | None:
    numeric = _to_float(value)
    if numeric is None:
        return None
    if numeric.is_integer():
        return int(numeric)
    return numeric


def _normalize_history(history: pd.DataFrame) -> list[Candle]:
    if history.empty:
        return []

    required_columns = {"Open", "High", "Low", "Close"}
    if not required_columns.issubset(set(history.columns)):
        return []

    candles: list[Candle] = []
    for index, row in history.iterrows():
        open_value = _to_float(row.get("Open"))
        high_value = _to_float(row.get("High"))
        low_value = _to_float(row.get("Low"))
        close_value = _to_float(row.get("Close"))

        if open_value is None or high_value is None or low_value is None or close_value is None:
            continue

        timestamp = pd.Timestamp(index)
        candles.append(
            {
                "time": timestamp.date().isoformat(),
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
                "volume": _to_volume(row.get("Volume")),
            }
        )
    return candles


def _fetch_market_candles_sync(
    symbol: str,
    interval: MarketCandleInterval,
    range_value: MarketCandleRange,
) -> MarketCandlesResult:
    normalized_symbol = symbol.strip()
    history = yf.Ticker(normalized_symbol).history(
        period=RANGE_MAP[range_value],
        interval=INTERVAL_MAP[interval],
        auto_adjust=False,
        timeout=10,
    )
    candles = _normalize_history(history)
    error_message = None if candles else "No candle data returned from yfinance"
    return {
        "symbol": normalized_symbol,
        "interval": interval,
        "candles": candles,
        "data": candles,
        "error_message": error_message,
    }


async def fetch_market_candles(
    symbol: str,
    interval: MarketCandleInterval,
    range_value: MarketCandleRange,
) -> MarketCandlesResult:
    normalized_symbol = symbol.strip()
    cache_key = (normalized_symbol, interval, range_value)
    cached = _CACHE.get(cache_key)
    now = monotonic()
    if cached and cached[0] > now:
        return cached[1]

    try:
        result = await asyncio.to_thread(_fetch_market_candles_sync, normalized_symbol, interval, range_value)
        if result["candles"]:
            _CACHE[cache_key] = (now + CACHE_TTL_SECONDS, result)
        return result
    except Exception as exc:
        return {
            "symbol": normalized_symbol,
            "interval": interval,
            "candles": [],
            "data": [],
            "error_message": str(exc),
        }
