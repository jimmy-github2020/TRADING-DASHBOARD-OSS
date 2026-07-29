from __future__ import annotations

from services.candles_fetcher import fetch_market_candles


def _index_for_scope(scope: str) -> str:
    return "^GSPC" if scope == "us" else "^TWII"


async def get_market_summary(scope: str = "tw") -> dict:
    normalized_scope = "us" if scope == "us" else "tw"
    symbol = _index_for_scope(normalized_scope)
    try:
        result = await fetch_market_candles(symbol=symbol, interval="1d", range_value="3mo")
        candles = result.get("candles", [])
        latest = candles[-1] if candles else None
        previous = candles[-2] if len(candles) >= 2 else None
        last_close = float(latest["close"]) if latest else None
        previous_close = float(previous["close"]) if previous else None
        change_pct = None
        if last_close is not None and previous_close not in (None, 0):
            change_pct = round(((last_close - previous_close) / previous_close) * 100, 4)
        volume = latest.get("volume") if latest else None
        return {
            "scope": normalized_scope,
            "index": symbol,
            "last_close": last_close,
            "change_pct": change_pct,
            "volume": volume,
            "error": result.get("error_message"),
        }
    except Exception as exc:
        return {
            "scope": normalized_scope,
            "index": symbol,
            "last_close": None,
            "change_pct": None,
            "volume": None,
            "error": str(exc),
        }
