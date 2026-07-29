from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


YAHOO_SYMBOL_MAP = {
    "^SOX": "SOXX",
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "3357.TW": "3357.TWO",
    "3491.TW": "3491.TWO",
    "5289.TW": "5289.TWO",
    "8299.TW": "8299.TWO",
}


async def fetch_yahoo_fallback_quotes(symbols: list[str]) -> list[dict[str, Any]]:
    if not symbols:
        return []
    tasks = [asyncio.to_thread(_fetch_one_yahoo_quote, symbol) for symbol in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    quotes: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, Exception) or result is None:
            continue
        quotes.append(result)
    return quotes


async def fetch_yahoo_fallback_ohlcv(symbol: str, timeframe: str, limit: int, range_value: str | None = None) -> dict[str, Any]:
    return await asyncio.to_thread(_fetch_yahoo_ohlcv, symbol, timeframe, limit, range_value)


def _fetch_one_yahoo_quote(symbol: str) -> dict[str, Any] | None:
    yahoo_symbol = YAHOO_SYMBOL_MAP.get(symbol, symbol)
    encoded_symbol = urllib.parse.quote(yahoo_symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=7d&interval=1d"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "TRADING-DASHBOARD/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        return None

    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators", {}).get("quote") or [{}])[0])
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    points = [
        {
            "timestamp": timestamps[index],
            "close": close,
            "volume": volumes[index] if index < len(volumes) else None,
        }
        for index, close in enumerate(closes)
        if close is not None and index < len(timestamps)
    ]
    if not points:
        return None

    latest = points[-1]
    previous = points[-2] if len(points) >= 2 else None
    price = float(latest["close"])
    previous_price = float(previous["close"]) if previous is not None else None
    change = price - previous_price if previous_price is not None else None
    change_pct = (change / previous_price * 100) if previous_price not in (None, 0) and change is not None else None
    return {
        "symbol": symbol,
        "provider": "yahoo",
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "volume": float(latest["volume"]) if latest["volume"] is not None else None,
        "candle_time": None,
        "source": "yahoo_fallback",
    }


def _normalize_ohlcv_range(timeframe: str, range_value: str | None) -> tuple[str, str | None]:
    requested = (range_value or "").lower()
    defaults = {"5m": "1d", "1h": "60d", "1d": "1y"}
    allowed = {
        "5m": {"1d": "1d", "3d": "5d", "1w": "7d", "2w": "14d", "1m": "1mo"},
        "1h": {"1w": "7d", "1m": "1mo", "3m": "3mo", "6m": "6mo", "1y": "1y", "2y": "2y"},
        "1d": {"1m": "1mo", "3m": "3mo", "6m": "6mo", "1y": "1y", "3y": "3y", "5y": "5y", "10y": "10y"},
    }
    if requested not in allowed.get(timeframe, {}):
        return defaults.get(timeframe, "1y"), None
    yahoo_range = allowed[timeframe][requested]
    warning = None
    if timeframe == "5m" and requested == "1m":
        warning = "5m data is limited by Yahoo Finance availability and may be truncated to about 30-60 days."
    if timeframe == "1h" and requested == "2y":
        warning = "1h data is clamped to the Yahoo Finance 730 day limit."
    return yahoo_range, warning


def _fetch_yahoo_ohlcv(symbol: str, timeframe: str, limit: int, range_value: str | None = None) -> dict[str, Any]:
    yahoo_symbol = YAHOO_SYMBOL_MAP.get(symbol, symbol)
    encoded_symbol = urllib.parse.quote(yahoo_symbol, safe="")
    interval = "5m" if timeframe == "5m" else "1h" if timeframe == "1h" else "1d"
    yahoo_range, warning = _normalize_ohlcv_range(timeframe, range_value)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range={yahoo_range}&interval={interval}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "TRADING-DASHBOARD/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {"candles": [], "warning": warning, "range": yahoo_range}

    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        return {"candles": [], "warning": warning, "range": yahoo_range}

    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators", {}).get("quote") or [{}])[0])
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    candles: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        if index >= len(closes) or closes[index] is None:
            continue
        open_value = opens[index] if index < len(opens) else closes[index]
        high_value = highs[index] if index < len(highs) else closes[index]
        low_value = lows[index] if index < len(lows) else closes[index]
        if open_value is None or high_value is None or low_value is None:
            continue
        candles.append(
            {
                "time": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
                "symbol": symbol,
                "timeframe": timeframe,
                "provider": "yahoo_fallback",
                "open": float(open_value),
                "high": float(high_value),
                "low": float(low_value),
                "close": float(closes[index]),
                "volume": float(volumes[index]) if index < len(volumes) and volumes[index] is not None else None,
            }
        )
    return {"candles": candles[-limit:], "warning": warning, "range": yahoo_range}
