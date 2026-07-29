from __future__ import annotations

import asyncio
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from quant import SectorRotationAnalyzer, SectorRotationInputError, StockRankingAnalyzer, StockRankingInputError
from repository import MarketRepository


DISCLAIMER = "⚠️ 本摘要由 AI 自動生成，僅供參考，不構成任何投資建議。"
WATCHLIST_SYMBOLS = ["0050.TW", "006208.TW", "2330.TW", "2317.TW", "2882.TW", "^GSPC", "^VIX", "GC=F"]
SYMBOL_NAMES = {
    "0050.TW": "台灣50",
    "006208.TW": "富邦台50",
    "2330.TW": "台積電",
    "2317.TW": "鴻海",
    "2882.TW": "國泰金",
    "^GSPC": "S&P 500",
    "^VIX": "VIX 恐慌指數",
    "GC=F": "黃金",
}


class MarketBriefDisabledError(RuntimeError):
    pass


class MarketBriefProviderError(RuntimeError):
    pass


class MarketBriefService:
    def __init__(
        self,
        repository: MarketRepository,
        sector_rotation_analyzer: SectorRotationAnalyzer,
        stock_ranking_analyzer: StockRankingAnalyzer,
        redis_url: str,
        openai_api_key: str,
        enabled: bool,
        model: str,
    ) -> None:
        self.repository = repository
        self.sector_rotation_analyzer = sector_rotation_analyzer
        self.stock_ranking_analyzer = stock_ranking_analyzer
        self.redis_url = redis_url
        self.openai_api_key = openai_api_key
        self.enabled = enabled
        self.model = model

    async def generate(self) -> dict[str, Any]:
        if not self.enabled or not self.openai_api_key:
            raise MarketBriefDisabledError("AI Market Brief is not enabled or OPENAI_API_KEY is missing")

        snapshot = await self.build_snapshot()
        context_hash = _hash_snapshot(snapshot)
        cache_key = f"ai_market_brief:{context_hash}"
        client = Redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        try:
            cached = await client.get(cache_key)
            if cached:
                result = json.loads(cached)
                result["cache"] = "hit"
                return result

            brief_text, tokens_used = await self._call_openai(snapshot)
            brief_text = ensure_disclaimer(brief_text)
            saved = await self.repository.insert_ai_market_brief(
                brief_text=brief_text,
                data_snapshot=snapshot,
                model=self.model,
                tokens_used=tokens_used,
            )
            saved["generated_at"] = saved["created_at"]
            saved["cache"] = "miss"
            await client.setex(cache_key, 1800, json.dumps(saved, ensure_ascii=False))
            return saved
        finally:
            await client.aclose()

    async def build_snapshot(self) -> dict[str, Any]:
        recent_closes = await self.repository.fetch_recent_closes_for_symbols(WATCHLIST_SYMBOLS, limit=6)
        symbol_summaries = [_summarize_symbol(symbol, recent_closes.get(symbol, [])) for symbol in WATCHLIST_SYMBOLS]
        vix_summary = _summarize_vix(recent_closes.get("^VIX", []))

        try:
            sector_rotation = await self.sector_rotation_analyzer.calculate(period="30", benchmark="SPY")
        except SectorRotationInputError as exc:
            sector_rotation = {"error": str(exc), "items": []}

        try:
            stock_ranking = await self.stock_ranking_analyzer.calculate(period="30", benchmark="^GSPC")
        except StockRankingInputError as exc:
            stock_ranking = {"error": str(exc), "items": []}

        return {
            "generated_context_at": datetime.now(timezone.utc).isoformat(),
            "watchlist": symbol_summaries,
            "sector_rotation": {
                "benchmark": sector_rotation.get("benchmark", "SPY"),
                "benchmark_return_pct": sector_rotation.get("benchmark_return_pct"),
                "top": sector_rotation.get("items", [])[:5],
            },
            "stock_ranking_top3": stock_ranking.get("items", [])[:3],
            "vix": vix_summary,
            "disclaimer": DISCLAIMER,
        }

    async def _call_openai(self, snapshot: dict[str, Any]) -> tuple[str, int | None]:
        payload = {
            "model": self.model,
            "temperature": 0.35,
            "max_tokens": 900,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是專業市場資料摘要助手。只能描述盤面、技術面觀察、波動、板塊輪動與資料限制。"
                        "禁止輸出任何買入、賣出、加碼、減碼、持有、目標價或投資建議。"
                        "請使用繁體中文，摘要長度 300 到 500 字，語氣精準克制。"
                        f"結尾必須包含免責聲明：{DISCLAIMER}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(snapshot, ensure_ascii=False),
                },
            ],
        }
        return await asyncio.to_thread(_post_openai_chat_completion, self.openai_api_key, payload)


def _post_openai_chat_completion(api_key: str, payload: dict[str, Any]) -> tuple[str, int | None]:
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise MarketBriefProviderError(f"OpenAI API error: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise MarketBriefProviderError(f"OpenAI API connection failed: {exc}") from exc

    choices = body.get("choices", [])
    content = choices[0].get("message", {}).get("content", "").strip() if choices else ""
    if not content:
        raise MarketBriefProviderError("OpenAI API returned an empty brief")
    usage = body.get("usage", {})
    tokens = usage.get("total_tokens")
    return content, int(tokens) if isinstance(tokens, int) else None


def _summarize_symbol(symbol: str, candles: list[dict]) -> dict[str, Any]:
    closes = [float(item["close"]) for item in candles]
    latest = closes[-1] if closes else None
    previous = closes[-2] if len(closes) >= 2 else None
    first = closes[0] if closes else None
    one_day_change = _pct_change(latest, previous)
    five_day_change = _pct_change(latest, first)
    return {
        "symbol": symbol,
        "name": SYMBOL_NAMES.get(symbol, symbol),
        "latest_close": round(latest, 4) if latest is not None else None,
        "one_day_change_pct": round(one_day_change, 4) if one_day_change is not None else None,
        "five_day_change_pct": round(five_day_change, 4) if five_day_change is not None else None,
        "closes": [
            {
                "time": item["time"],
                "close": round(float(item["close"]), 4),
            }
            for item in candles[-5:]
        ],
    }


def _summarize_vix(candles: list[dict]) -> dict[str, Any]:
    closes = [float(item["close"]) for item in candles[-5:]]
    latest = closes[-1] if closes else None
    average = sum(closes) / len(closes) if closes else None
    return {
        "latest": round(latest, 4) if latest is not None else None,
        "five_day_average": round(average, 4) if average is not None else None,
    }


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current / previous - 1.0) * 100


def _hash_snapshot(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def ensure_disclaimer(text: str) -> str:
    clean = text.strip()
    if DISCLAIMER in clean:
        return clean
    return f"{clean}\n\n{DISCLAIMER}"
