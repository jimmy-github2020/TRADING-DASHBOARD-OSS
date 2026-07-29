from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from services.candles_fetcher import (
    MarketCandleInterval,
    MarketCandleRange,
    MarketCandlesResult,
    fetch_market_candles,
)

router = APIRouter(prefix="/api/v1", tags=["market"])


@router.get("/market/candles")
async def get_market_candles(
    symbol: Annotated[str, Query(min_length=1)] = "^TWII",
    interval: MarketCandleInterval = Query("1d"),
    range_value: Annotated[MarketCandleRange, Query(alias="range")] = "1y",
) -> MarketCandlesResult:
    result = await fetch_market_candles(symbol=symbol, interval=interval, range_value=range_value)
    if result["error_message"] or not result["candles"]:
        detail = result["error_message"] or f"No candle data returned for {symbol}"
        raise HTTPException(status_code=422, detail=detail)
    return result

