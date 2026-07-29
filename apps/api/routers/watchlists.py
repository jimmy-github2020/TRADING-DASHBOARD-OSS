from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import load_settings
from responses import api_response
from services.watchlists import WatchlistRepository, slugify_watchlist


router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])
repository = WatchlistRepository(load_settings().database_url)


class WatchlistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class WatchlistItemRequest(BaseModel):
    instrument_id: int = Field(gt=0)
    tracking_tier: Literal["catalog", "quote", "daily", "intraday"] = "quote"
    notes: str | None = Field(default=None, max_length=1000)


class WatchlistItemUpdateRequest(BaseModel):
    tracking_tier: Literal["catalog", "quote", "daily", "intraday"]
    notes: str | None = Field(default=None, max_length=1000)


@router.get("")
async def list_watchlists() -> dict:
    items = await repository.list_watchlists()
    return api_response(items, {"count": len(items)})


@router.post("")
async def create_watchlist(request: WatchlistCreateRequest) -> dict:
    slug = slugify_watchlist(request.slug or request.name)
    if not slug:
        raise HTTPException(status_code=422, detail="A valid watchlist slug is required")
    try:
        item = await repository.create_watchlist(
            name=request.name.strip(),
            slug=slug,
            description=request.description,
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Watchlist slug already exists") from exc
        raise
    return api_response(item, {"created": True})


@router.get("/{watchlist_id}/items")
async def list_watchlist_items(watchlist_id: int) -> dict:
    items = await repository.list_items(watchlist_id)
    return api_response(items, {"count": len(items), "watchlist_id": watchlist_id})


@router.post("/{watchlist_id}/items")
async def add_watchlist_item(watchlist_id: int, request: WatchlistItemRequest) -> dict:
    try:
        item = await repository.add_item(
            watchlist_id=watchlist_id,
            instrument_id=request.instrument_id,
            tracking_tier=request.tracking_tier,
            notes=request.notes,
        )
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Instrument not found") from exc
        raise
    if item is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return api_response(item, {"created": True})


@router.patch("/{watchlist_id}/items/{item_id}")
async def update_watchlist_item(
    watchlist_id: int,
    item_id: int,
    request: WatchlistItemUpdateRequest,
) -> dict:
    item = await repository.update_item(
        watchlist_id=watchlist_id,
        item_id=item_id,
        tracking_tier=request.tracking_tier,
        notes=request.notes,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return api_response(item, {"updated": True})


@router.delete("/{watchlist_id}/items/{item_id}")
async def remove_watchlist_item(watchlist_id: int, item_id: int) -> dict:
    removed = await repository.remove_item(
        watchlist_id=watchlist_id,
        item_id=item_id,
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return api_response({"id": item_id}, {"deleted": True})
