from __future__ import annotations

import json

from redis.asyncio import Redis


class QuoteCache:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url

    async def fetch_snapshots(self) -> list[dict]:
        client = Redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        try:
            keys = sorted(await client.smembers("quotes:snapshot:keys"))
            snapshots: list[dict] = []
            for key in keys:
                payload = await client.get(key)
                if not payload:
                    continue
                item = json.loads(payload)
                item["source"] = "redis"
                snapshots.append(item)
            return snapshots
        finally:
            await client.aclose()
