from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from services.technical_analysis import get_technical_ranking, get_technical_summary, get_watchlist_technical_signals

router = APIRouter(prefix="/api/v1", tags=["technical"])


def _scope_symbol(scope: str | None) -> str:
    return "^GSPC" if scope == "us" else "^TWII"


@router.get("/technical/summary")
async def technical_summary(
    symbol: Annotated[str | None, Query(min_length=1)] = None,
    scope: Literal["tw", "us"] | None = Query(None),
) -> dict:
    try:
        return await get_technical_summary(symbol=symbol or _scope_symbol(scope))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/technical/ranking")
async def technical_ranking(
    market: str = Query("TAIEX"),
    limit: int = Query(10, ge=1, le=20),
) -> dict:
    try:
        return await get_technical_ranking(market=market, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/technical/signals")
async def technical_signals(
    watchlist: bool = Query(False),
    limit: int = Query(20, ge=1, le=50),
) -> list[dict]:
    if not watchlist:
        raise HTTPException(status_code=400, detail="Only watchlist=true is supported")
    try:
        return await get_watchlist_technical_signals(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
