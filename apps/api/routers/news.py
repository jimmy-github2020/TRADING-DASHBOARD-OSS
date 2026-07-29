from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from services.news_fetcher import NewsFetchResult, fetch_news

router = APIRouter(prefix="/api/v1", tags=["news"])


@router.get("/news")
async def get_news(
    scope: Literal["tw", "us"] = Query("tw"),
    limit: int = Query(10, ge=1, le=50),
) -> NewsFetchResult:
    return await fetch_news(scope=scope, limit=limit)
