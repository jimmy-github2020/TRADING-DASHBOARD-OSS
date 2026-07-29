from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from services.elliott_wave import analyze_elliott_wave

router = APIRouter(prefix="/api/v1", tags=["elliott-wave"])


def _symbol_for_scope(scope: str, symbol: str | None = None) -> str:
    if symbol:
        return symbol.strip() or "^TWII"
    return "^GSPC" if scope.strip().lower() == "us" else "^TWII"


@router.get("/elliott-wave")
async def get_elliott_wave(
    scope: Annotated[str, Query(pattern="^(tw|us)$")] = "tw",
    symbol: str | None = Query(None, min_length=1),
) -> dict:
    return await analyze_elliott_wave(symbol=_symbol_for_scope(scope, symbol))


@router.get("/market/elliott-wave")
async def get_market_elliott_wave_alias(
    symbol: Annotated[str, Query(min_length=1)] = "^TWII",
) -> dict:
    return await analyze_elliott_wave(symbol=symbol)
