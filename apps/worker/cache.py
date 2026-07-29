from __future__ import annotations

from datetime import datetime, timezone
import json

from redis import Redis

from models import Candle


class QuoteCache:
    def __init__(self, redis_url: str) -> None:
        self.client = Redis.from_url(redis_url, decode_responses=True)

    def store_latest_snapshot(self, candles: list[Candle], ttl_seconds: int = 1800) -> None:
        if not candles:
            return

        ordered = sorted(candles, key=lambda candle: candle.time)
        latest = ordered[-1]
        previous = ordered[-2] if len(ordered) > 1 else None
        change = latest.close - previous.close if previous else None
        change_pct = (change / previous.close * 100) if previous and previous.close else None

        payload = {
            "symbol": latest.symbol,
            "provider": latest.provider,
            "timeframe": latest.timeframe,
            "price": latest.close,
            "change": change,
            "change_pct": change_pct,
            "volume": latest.volume,
            "candle_time": latest.time.isoformat(),
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }

        key = f"quotes:snapshot:{latest.provider}:{latest.symbol}:{latest.timeframe}"
        self.client.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl_seconds)
        self.client.sadd("quotes:snapshot:keys", key)

    def close(self) -> None:
        self.client.close()
