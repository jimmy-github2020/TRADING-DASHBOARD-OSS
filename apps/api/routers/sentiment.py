from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from services.sentiment_fetcher import SentimentFetchResult, fetch_sentiment

router = APIRouter(prefix="/api/v1", tags=["sentiment"])


@router.get("/sentiment")
async def get_sentiment(scope: Literal["tw", "us"] = Query("tw")) -> SentimentFetchResult:
    return await fetch_sentiment(scope=scope)
