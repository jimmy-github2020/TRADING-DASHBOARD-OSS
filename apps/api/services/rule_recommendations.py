from __future__ import annotations

from typing import Any

import asyncpg

from services.alert_rule_service import fetch_alert_rule_quality


SETTING_KEY = "recommendation_engine_enabled"


async def get_recommendation_engine_enabled(database_url: str) -> bool:
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_app_settings(conn)
        return await _fetch_enabled(conn)
    finally:
        await conn.close()


async def update_recommendation_engine_enabled(database_url: str, enabled: bool) -> dict[str, Any]:
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_app_settings(conn)
        await conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ($1, $2::jsonb, now())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = now()
            """,
            SETTING_KEY,
            "true" if enabled else "false",
        )
        return {"enabled": enabled}
    finally:
        await conn.close()


async def fetch_rule_recommendations(database_url: str, days: int = 7) -> dict[str, Any]:
    days = max(1, min(int(days), 30))
    enabled = await get_recommendation_engine_enabled(database_url)
    if not enabled:
        return {"enabled": False, "days": days, "items": []}

    quality = await fetch_alert_rule_quality(database_url, days=days)
    items = [_recommend_from_quality(rule) for rule in quality.get("rules", [])]
    return {
        "enabled": True,
        "days": days,
        "generated_at": quality.get("generated_at"),
        "items": items,
    }


async def _fetch_enabled(conn: asyncpg.Connection) -> bool:
    row = await conn.fetchrow("SELECT value FROM app_settings WHERE key = $1", SETTING_KEY)
    if row is None:
        await conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ($1, 'false'::jsonb, now())
            ON CONFLICT (key) DO NOTHING
            """,
            SETTING_KEY,
        )
        return False
    return _jsonb_bool(row["value"])


async def _ensure_app_settings(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
          key VARCHAR(80) PRIMARY KEY,
          value JSONB NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _recommend_from_quality(rule: dict[str, Any]) -> dict[str, Any]:
    trigger_count = int(rule.get("trigger_count") or 0)
    sent_count = int(rule.get("sent_count") or 0)
    dedup_count = int(rule.get("dedup_skipped_count") or 0)
    skipped_frequency = int(rule.get("skipped_frequency_count") or 0)
    error_count = int(rule.get("error_count") or 0)
    manual_count = int(rule.get("manual_test_count") or 0)
    no_trigger_count = int(rule.get("no_trigger_count") or 0)
    dedup_rate = float(rule.get("dedup_rate") or 0)

    recommendation_type = "no_action"
    suggested_action = "keep_monitoring"
    reason = "近 7 天規則品質沒有明顯異常，暫時維持觀察。"
    confidence = "low"
    suggested_value: float | None = None

    if error_count >= 3:
        recommendation_type = "system_issue"
        suggested_action = "check_data_source_or_evaluation_flow"
        reason = "近 7 天錯誤次數偏高，應優先檢查資料來源、評估函式或通知流程。"
        confidence = "high"
    elif trigger_count >= 5 and dedup_rate >= 0.6:
        recommendation_type = "high_dedup_noise"
        suggested_action = "consider_raise_threshold_or_extend_dedup_window"
        reason = "近 7 天重複事件偏高，多次命中但實際送出比例偏低。"
        confidence = "medium"
        suggested_value = _suggest_threshold_adjustment(rule, direction="less_sensitive")
    elif trigger_count >= 5 and sent_count <= 1 and dedup_count + skipped_frequency >= 3:
        recommendation_type = "high_trigger_low_delivery"
        suggested_action = "review_threshold_and_dedup_policy"
        reason = "近期命中不少但送出很少，可能門檻偏鬆，或 dedup / 頻率限制過嚴。"
        confidence = "medium"
        suggested_value = _suggest_threshold_adjustment(rule, direction="less_sensitive")
    elif trigger_count == 0 and no_trigger_count >= 5:
        recommendation_type = "too_strict_or_quiet"
        suggested_action = "consider_loosen_threshold_or_keep_observing"
        reason = "近期多次評估都未命中，規則可能偏嚴；若希望更敏感，可考慮放寬門檻。"
        confidence = "medium"
        suggested_value = _suggest_threshold_adjustment(rule, direction="more_sensitive")
    elif manual_count >= 3 and trigger_count <= 1 and sent_count == 0:
        recommendation_type = "still_tuning"
        suggested_action = "keep_observing_before_adjusting_frequency"
        reason = "手動測試偏多但真實命中少，規則可能仍在調校階段，暫不建議提高通知頻率。"
        confidence = "low"

    return {
        "rule_key": rule.get("rule_key"),
        "recommendation_status": "active" if recommendation_type != "no_action" else "none",
        "recommendation_type": recommendation_type,
        "suggested_action": suggested_action,
        "suggested_value": suggested_value,
        "reason": reason,
        "confidence": confidence,
    }


def _suggest_threshold_adjustment(rule: dict[str, Any], direction: str) -> float | None:
    rule_key = str(rule.get("rule_key") or "")
    if rule_key == "vix_high":
        base = 20.0
        return base + 2.0 if direction == "less_sensitive" else base - 2.0
    if rule_key == "twii_pct_move":
        return 2.5 if direction == "less_sensitive" else 1.5
    if rule_key == "fear_greed_extreme":
        return 15.0 if direction == "less_sensitive" else 25.0
    if rule_key == "oil_price_pct_move":
        return 4.0 if direction == "less_sensitive" else 2.5
    return None


def _jsonb_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)
