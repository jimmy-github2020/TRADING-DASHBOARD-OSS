from __future__ import annotations

from services.news_fetcher import fetch_news


async def get_news_headlines(scope: str = "tw", limit: int = 5) -> dict:
    normalized_scope = "us" if scope == "us" else "tw"
    safe_limit = max(1, min(limit, 20))
    try:
        result = await fetch_news(scope=normalized_scope, limit=safe_limit)
        return {
            "items": [
                {
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "sentiment": item.get("sentiment"),
                    "sentiment_score": item.get("sentiment_score"),
                }
                for item in result.get("items", [])
            ],
            "error": result.get("error_message"),
        }
    except Exception as exc:
        return {"items": [], "error": str(exc)}
