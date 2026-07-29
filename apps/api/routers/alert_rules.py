from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import load_settings
from services.alert_rule_service import (
    evaluate_alert_rules,
    evaluate_single_alert_rule,
    fetch_alert_rule_quality,
    list_alert_rules,
    update_alert_rule,
)
from services.rule_recommendations import (
    fetch_rule_recommendations,
    update_recommendation_engine_enabled,
)


router = APIRouter(prefix="/api/v1/alert-rules", tags=["alert-rules"])


class AlertRuleUpdateRequest(BaseModel):
    enabled: bool | None = None
    notify_enabled: bool | None = None
    threshold_value: float | None = None
    threshold_min: float | None = None
    threshold_max: float | None = None
    severity: str | None = Field(default=None, pattern="^(info|warning|critical)$")
    description: str | None = None


class RecommendationEngineRequest(BaseModel):
    enabled: bool


@router.get("")
async def read_alert_rules() -> list[dict[str, Any]]:
    settings = load_settings()
    return await list_alert_rules(settings.database_url)


@router.patch("/{rule_key}")
async def patch_alert_rule(rule_key: str, payload: AlertRuleUpdateRequest) -> dict[str, Any]:
    settings = load_settings()
    try:
        return await update_alert_rule(
            settings.database_url,
            rule_key=rule_key,
            updates=payload.model_dump(exclude_unset=True),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Alert rule not found: {rule_key}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/evaluate")
async def create_alert_rule_evaluation() -> dict[str, Any]:
    settings = load_settings()
    return await evaluate_alert_rules(settings.database_url)


@router.get("/quality")
async def read_alert_rule_quality(days: int = 7) -> dict[str, Any]:
    settings = load_settings()
    return await fetch_alert_rule_quality(settings.database_url, days=days)


@router.get("/recommendations")
async def read_alert_rule_recommendations(days: int = 7) -> dict[str, Any]:
    settings = load_settings()
    return await fetch_rule_recommendations(settings.database_url, days=days)


@router.put("/recommendations/settings")
async def write_recommendation_engine_settings(payload: RecommendationEngineRequest) -> dict[str, Any]:
    settings = load_settings()
    return await update_recommendation_engine_enabled(settings.database_url, enabled=payload.enabled)


@router.post("/{rule_key}/evaluate")
async def create_single_alert_rule_evaluation(rule_key: str) -> dict[str, Any]:
    settings = load_settings()
    try:
        return await evaluate_single_alert_rule(settings.database_url, rule_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Alert rule not found: {rule_key}") from exc
