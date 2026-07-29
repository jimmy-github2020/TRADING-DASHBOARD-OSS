from __future__ import annotations

from services.sentiment_fetcher import fetch_sentiment


async def get_sentiment_data(scope: str = "tw") -> dict:
    normalized_scope = "us" if scope == "us" else "tw"
    try:
        result = await fetch_sentiment(scope=normalized_scope)
        return {
            "fear_greed_score": result.get("fear_greed_score"),
            "fear_greed_label": result.get("fear_greed_label"),
            "vix": result.get("vix"),
            "put_call_ratio": result.get("put_call_ratio"),
            "error": None,
        }
    except Exception as exc:
        return {
            "fear_greed_score": None,
            "fear_greed_label": None,
            "vix": None,
            "put_call_ratio": None,
            "error": str(exc),
        }
