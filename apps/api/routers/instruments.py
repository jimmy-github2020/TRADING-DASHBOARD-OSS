from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from config import load_settings
from responses import api_response
from services.instrument_catalog import InstrumentCatalogRepository


router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


def _repository() -> InstrumentCatalogRepository:
    return InstrumentCatalogRepository(load_settings().database_url)


@router.get("")
async def list_instruments(
    q: str | None = Query(default=None, max_length=120),
    market: str | None = Query(default=None, max_length=20),
    exchange: str | None = Query(default=None, max_length=40),
    security_type: str | None = Query(default=None, max_length=32),
    active_only: bool = True,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    items, total = await _repository().list_instruments(
        query=q,
        market=market,
        exchange=exchange,
        security_type=security_type,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return api_response(
        items,
        {
            "count": len(items),
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/resolve")
async def resolve_instrument(
    provider: str = Query(min_length=1, max_length=40),
    symbol: str = Query(min_length=1, max_length=64),
) -> dict:
    item = await _repository().resolve_provider_symbol(provider, symbol)
    if item is None:
        raise HTTPException(status_code=404, detail="Instrument mapping not found")
    return api_response(item, {"provider": provider, "symbol": symbol})


@router.get("/stats")
async def get_instrument_stats() -> dict:
    stats = await _repository().get_catalog_stats()
    return api_response(stats)


@router.get("/{instrument_id}")
async def get_instrument(instrument_id: int) -> dict:
    item = await _repository().get_instrument(instrument_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return api_response(item)
