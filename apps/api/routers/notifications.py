from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import load_settings
from services.notification_diagnostics import (
    fetch_notification_diagnostics_summary,
    fetch_notification_events,
    fetch_notification_job_runs,
    fetch_notification_metrics,
)
from services.notification_item_status import fetch_notification_item_status
from services.notification_mode import get_notification_mode, update_notification_mode
from services.notification_settings import (
    NotificationSettingsUpdate,
    get_notification_settings,
    update_notification_settings,
)
from services.notification_test_sender import send_test_alert, send_test_item, send_test_summary


router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class NotificationSettingsRequest(BaseModel):
    alerts_enabled: bool
    market_alerts_enabled: bool
    price_alerts_enabled: bool
    technical_alerts_enabled: bool
    ai_summary_enabled: bool
    summary_frequency: str = Field(pattern="^(off|daily|morning|evening)$")


class NotificationModeRequest(BaseModel):
    mode: str | None = Field(default=None, pattern="^(dry_run|live)$")
    dry_run: bool | None = None
    confirm: bool = False


class NotificationTestRequest(BaseModel):
    dry_run: bool = False
    force_send: bool = True


class NotificationTestItemRequest(BaseModel):
    type: str = Field(pattern="^(morning_brief|closing_brief|market_alert|price_alert|technical_alert)$")
    dry_run: bool = False


@router.get("/settings")
async def read_notification_settings() -> dict:
    settings = load_settings()
    return await get_notification_settings(settings.database_url)


@router.put("/settings")
async def write_notification_settings(payload: NotificationSettingsRequest) -> dict:
    settings = load_settings()
    try:
        update = NotificationSettingsUpdate(**payload.model_dump())
        return await update_notification_settings(settings.database_url, update)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/mode")
async def read_notification_mode() -> dict:
    settings = load_settings()
    return await get_notification_mode(settings.database_url)


@router.put("/mode")
async def write_notification_mode(payload: NotificationModeRequest) -> dict:
    settings = load_settings()
    if payload.mode is None and payload.dry_run is None:
        raise HTTPException(status_code=422, detail="mode or dry_run is required")
    dry_run = payload.dry_run if payload.dry_run is not None else payload.mode == "dry_run"
    if dry_run is False and not payload.confirm:
        raise HTTPException(status_code=422, detail="confirm=true is required when switching to live mode")
    return await update_notification_mode(settings.database_url, dry_run=dry_run)


@router.post("/test-summary")
async def create_test_summary(payload: NotificationTestRequest) -> dict:
    settings = load_settings()
    return await send_test_summary(
        settings.database_url,
        settings.telegram_bot_token,
        dry_run=payload.dry_run,
    )


@router.post("/test-alert")
async def create_test_alert(payload: NotificationTestRequest) -> dict:
    settings = load_settings()
    return await send_test_alert(
        settings.database_url,
        settings.telegram_bot_token,
        dry_run=payload.dry_run,
    )


@router.post("/test-item")
async def create_test_item(payload: NotificationTestItemRequest) -> dict:
    settings = load_settings()
    return await send_test_item(
        settings.database_url,
        settings.telegram_bot_token,
        item_type=payload.type,
        dry_run=payload.dry_run,
    )


@router.get("/item-status")
async def read_notification_item_status() -> dict:
    settings = load_settings()
    return await fetch_notification_item_status(settings.database_url)


@router.get("/events")
async def read_notification_events(limit: int = Query(default=50, ge=1, le=100)) -> list[dict]:
    settings = load_settings()
    return await fetch_notification_events(settings.database_url, limit=limit)


@router.get("/job-runs")
async def read_notification_job_runs(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    settings = load_settings()
    return await fetch_notification_job_runs(settings.database_url, limit=limit)


@router.get("/diagnostics/summary")
async def read_notification_diagnostics_summary() -> dict:
    settings = load_settings()
    return await fetch_notification_diagnostics_summary(settings.database_url)


@router.get("/metrics")
async def read_notification_metrics(days: int = Query(default=7, ge=1, le=30)) -> dict:
    settings = load_settings()
    return await fetch_notification_metrics(settings.database_url, days=days)
