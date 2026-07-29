from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path

from market_quote import fetch_yahoo_fallback_quotes

router = APIRouter(prefix="/api/v1", tags=["stocks"])


@router.get("/stocks/{symbol}/price")
async def stock_price(symbol: Annotated[str, Path(min_length=1)]) -> dict[str, Any]:
    normalized = symbol.strip().upper()
    quotes = await fetch_yahoo_fallback_quotes([normalized])
    if not quotes:
        raise HTTPException(status_code=422, detail=f"No realtime quote returned for {normalized}")
    quote = quotes[0]
    return {
        "symbol": normalized,
        "price": quote.get("price"),
        "change": quote.get("change"),
        "change_pct": quote.get("change_pct"),
        "volume": quote.get("volume"),
        "source": quote.get("source", "yahoo_fallback"),
    }
