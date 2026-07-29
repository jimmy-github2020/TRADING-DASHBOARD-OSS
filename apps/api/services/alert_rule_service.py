from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import json
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from services.candles_fetcher import fetch_market_candles
from services.sentiment_fetcher import fetch_sentiment


TAIPEI = ZoneInfo("Asia/Taipei")

DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "rule_key": "twii_pct_move",
        "name": "TWII 漲跌幅警示",
        "category": "market",
        "metric_source": "twii",
        "operator": "outside_range",
        "threshold_value": None,
        "threshold_min": -2.0,
        "threshold_max": 2.0,
        "comparison_window": "1d",
        "enabled": True,
        "severity": "warning",
        "notify_enabled": True,
        "description": "台灣加權指數單日漲跌幅超出設定區間時提醒。",
    },
    {
        "rule_key": "vix_high",
        "name": "VIX 高波動警示",
        "category": "macro",
        "metric_source": "vix",
        "operator": "gte",
        "threshold_value": 25.0,
        "threshold_min": None,
        "threshold_max": None,
        "comparison_window": "latest",
        "enabled": True,
        "severity": "warning",
        "notify_enabled": True,
        "description": "VIX 高於設定門檻時提醒市場波動升溫。",
    },
    {
        "rule_key": "fear_greed_extreme",
        "name": "Fear & Greed 極端警示",
        "category": "macro",
        "metric_source": "fear_greed",
        "operator": "outside_range",
        "threshold_value": None,
        "threshold_min": 20.0,
        "threshold_max": 80.0,
        "comparison_window": "latest",
        "enabled": True,
        "severity": "warning",
        "notify_enabled": True,
        "description": "Fear & Greed 指數進入極端恐懼或極端貪婪區間時提醒。",
    },
    {
        "rule_key": "oil_price_pct_move",
        "name": "油價單日波動警示",
        "category": "macro",
        "metric_source": "oil",
        "operator": "outside_range",
        "threshold_value": None,
        "threshold_min": -3.0,
        "threshold_max": 3.0,
        "comparison_window": "1d",
        "enabled": False,
        "severity": "info",
        "notify_enabled": True,
        "description": "Brent 原油期貨單日波動超出設定區間時提醒，預設停用。",
    },
]

PATCH_FIELDS = {
    "enabled",
    "notify_enabled",
    "threshold_value",
    "threshold_min",
    "threshold_max",
    "severity",
    "description",
}


async def list_alert_rules(database_url: str) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(database_url)
    try:
        await ensure_alert_rules(conn)
        rows = await conn.fetch(
            """
            SELECT *
            FROM alert_rules
            WHERE category IN ('market', 'macro')
            ORDER BY id ASC
            """
        )
        return [_row_to_dict(row) for row in rows]
    finally:
        await conn.close()


async def update_alert_rule(database_url: str, rule_key: str, updates: dict[str, Any]) -> dict[str, Any]:
    allowed_updates = {key: value for key, value in updates.items() if key in PATCH_FIELDS and value is not None}
    if not allowed_updates:
        raise ValueError("No supported fields to update")

    conn = await asyncpg.connect(database_url)
    try:
        await ensure_alert_rules(conn)
        assignments: list[str] = []
        values: list[Any] = []
        for index, (key, value) in enumerate(allowed_updates.items(), start=1):
            assignments.append(f"{key} = ${index}")
            values.append(value)
        values.append(rule_key)
        query = f"""
            UPDATE alert_rules
            SET {", ".join(assignments)}, updated_at = now()
            WHERE rule_key = ${len(values)}
            RETURNING *
        """
        row = await conn.fetchrow(query, *values)
        if row is None:
            raise KeyError(rule_key)
        return _row_to_dict(row)
    finally:
        await conn.close()


async def evaluate_alert_rules(database_url: str) -> dict[str, Any]:
    conn = await asyncpg.connect(database_url)
    try:
        await ensure_alert_rules(conn)
        rows = await conn.fetch(
            """
            SELECT *
            FROM alert_rules
            WHERE category IN ('market', 'macro')
            ORDER BY id ASC
            """
        )
    finally:
        await conn.close()

    metrics = await _fetch_metric_values()
    results = [_evaluate_rule(_row_to_dict(row), metrics.get(str(row["metric_source"]))) for row in rows]
    return {
        "evaluated_at": datetime.now(TAIPEI).isoformat(),
        "results": results,
    }


async def evaluate_single_alert_rule(database_url: str, rule_key: str) -> dict[str, Any]:
    evaluation = await evaluate_alert_rules(database_url)
    result = next((item for item in evaluation["results"] if item["rule_key"] == rule_key), None)
    if result is None:
        raise KeyError(rule_key)

    payload = {
        "evaluated_at": evaluation["evaluated_at"],
        **result,
        "data_available": result.get("current_value") is not None,
    }
    await record_manual_rule_test(database_url, payload)
    return payload


async def fetch_alert_rule_quality(database_url: str, days: int = 7) -> dict[str, Any]:
    window_days = max(1, min(days, 30))
    since = datetime.now(TAIPEI) - timedelta(days=window_days)
    conn = await asyncpg.connect(database_url)
    try:
        await ensure_alert_rules(conn)
        await _ensure_notification_runtime_events(conn)
        rule_rows = await conn.fetch(
            """
            SELECT rule_key, name, enabled, notify_enabled
            FROM alert_rules
            WHERE category IN ('market', 'macro')
            ORDER BY id ASC
            """
        )
        events = await conn.fetch(
            """
            SELECT notification_type, status, skip_reason, topic, metadata_json, created_at
            FROM notification_runtime_events
            WHERE created_at >= $1
              AND (
                notification_type = 'market_alert'
                OR notification_type LIKE 'market_alert:%'
                OR notification_type LIKE 'manual_rule_test:%'
              )
            ORDER BY created_at DESC
            """,
            since,
        )
    finally:
        await conn.close()

    buckets: dict[str, dict[str, Any]] = {
        str(row["rule_key"]): _empty_quality_bucket(row, window_days) for row in rule_rows
    }
    for row in events:
        event = dict(row)
        rule_key = _event_rule_key(event)
        if not rule_key or rule_key not in buckets:
            continue
        _apply_quality_event(buckets[rule_key], event)

    rules = []
    for rule_key, bucket in buckets.items():
        trigger_count = bucket["trigger_count"]
        bucket["delivery_rate"] = _ratio(bucket["sent_count"], trigger_count)
        bucket["dedup_rate"] = _ratio(bucket["dedup_skipped_count"], trigger_count)
        bucket["actionability_hint"] = _quality_hint(bucket)
        rules.append(bucket)

    return {
        "days": window_days,
        "generated_at": datetime.now(TAIPEI).isoformat(),
        "rules": rules,
    }


async def record_manual_rule_test(database_url: str, result: dict[str, Any]) -> None:
    status = "matched" if result.get("matched") else "no_trigger"
    if result.get("current_value") is None:
        status = "data_unavailable"
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_notification_runtime_events(conn)
        await conn.execute(
            """
            INSERT INTO notification_runtime_events (
              job_name, notification_type, status, skip_reason, topic,
              message_preview, metadata_json
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            """,
            "manual_rule_test",
            f"manual_rule_test:{result.get('rule_key')}",
            status,
            None if status == "matched" else status,
            result.get("rule_key"),
            result.get("reason"),
            _json_dumps(
                {
                    "rule_key": result.get("rule_key"),
                    "current_value": result.get("current_value"),
                    "matched": result.get("matched"),
                    "notify_candidate": result.get("notify_candidate"),
                    "reason": result.get("reason"),
                    "data_available": result.get("data_available"),
                }
            ),
        )
    finally:
        await conn.close()


async def ensure_alert_rules(conn: asyncpg.Connection) -> None:
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('alert_rules_schema'))")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_rules (
          id SERIAL PRIMARY KEY,
          rule_key VARCHAR(80) UNIQUE NOT NULL,
          name VARCHAR(120) NOT NULL,
          category VARCHAR(30) NOT NULL,
          metric_source VARCHAR(40) NOT NULL,
          operator VARCHAR(30) NOT NULL,
          threshold_value NUMERIC(14,4),
          threshold_min NUMERIC(14,4),
          threshold_max NUMERIC(14,4),
          comparison_window VARCHAR(30) NOT NULL DEFAULT 'latest',
          enabled BOOLEAN NOT NULL DEFAULT true,
          severity VARCHAR(20) NOT NULL DEFAULT 'warning',
          notify_enabled BOOLEAN NOT NULL DEFAULT true,
          description TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    for rule in DEFAULT_RULES:
        await conn.execute(
            """
            INSERT INTO alert_rules (
              rule_key, name, category, metric_source, operator, threshold_value,
              threshold_min, threshold_max, comparison_window, enabled, severity,
              notify_enabled, description
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (rule_key) DO NOTHING
            """,
            rule["rule_key"],
            rule["name"],
            rule["category"],
            rule["metric_source"],
            rule["operator"],
            rule["threshold_value"],
            rule["threshold_min"],
            rule["threshold_max"],
            rule["comparison_window"],
            rule["enabled"],
            rule["severity"],
            rule["notify_enabled"],
            rule["description"],
        )


async def _ensure_notification_runtime_events(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_runtime_events (
          id SERIAL PRIMARY KEY,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          job_name VARCHAR(80),
          notification_type VARCHAR(80) NOT NULL,
          status VARCHAR(30) NOT NULL,
          skip_reason VARCHAR(80),
          symbol VARCHAR(40),
          topic VARCHAR(120),
          message_preview TEXT,
          chat_id VARCHAR(50),
          dedup_key VARCHAR(220),
          metadata_json JSONB
        )
        """
    )


async def _fetch_metric_values() -> dict[str, dict[str, Any]]:
    sentiment = await fetch_sentiment("tw")
    twii = await _latest_change_pct("^TWII")
    oil = await _latest_change_pct("BZ=F")
    return {
        "twii": {
            "value": twii.get("change_pct"),
            "label": "TWII 日變動",
            "unit": "%",
            "error": twii.get("error"),
            "metadata": twii,
        },
        "vix": {
            "value": sentiment.get("vix"),
            "label": "VIX",
            "unit": "",
            "error": None if sentiment.get("vix") is not None else "VIX data unavailable",
            "metadata": {"vix": sentiment.get("vix")},
        },
        "fear_greed": {
            "value": sentiment.get("fear_greed_score"),
            "label": "Fear & Greed",
            "unit": "",
            "error": None if sentiment.get("fear_greed_score") is not None else "Fear & Greed data unavailable",
            "metadata": {
                "fear_greed_score": sentiment.get("fear_greed_score"),
                "fear_greed_label": sentiment.get("fear_greed_label"),
            },
        },
        "oil": {
            "value": oil.get("change_pct"),
            "label": "Brent 原油日變動",
            "unit": "%",
            "error": oil.get("error"),
            "metadata": oil,
        },
    }


async def _latest_change_pct(symbol: str) -> dict[str, Any]:
    result = await fetch_market_candles(symbol=symbol, interval="1d", range_value="1mo")
    candles = result.get("candles") or []
    if len(candles) < 2:
        return {"symbol": symbol, "change_pct": None, "error": result.get("error_message") or "Not enough candle data"}
    latest = candles[-1]
    previous = candles[-2]
    close = _safe_float(latest.get("close"))
    prev_close = _safe_float(previous.get("close"))
    if close is None or prev_close in (None, 0):
        return {"symbol": symbol, "change_pct": None, "error": "Close price unavailable"}
    return {
        "symbol": symbol,
        "last_close": close,
        "previous_close": prev_close,
        "change_pct": ((close - prev_close) / prev_close) * 100,
        "latest_time": latest.get("time"),
        "previous_time": previous.get("time"),
        "error": None,
    }


def _evaluate_rule(rule: dict[str, Any], metric: dict[str, Any] | None) -> dict[str, Any]:
    if metric is None:
        return _result(rule, None, False, f"{rule['metric_source']} data unavailable", False, {"error": "metric unavailable"})
    current_value = _safe_float(metric.get("value"))
    metadata = metric.get("metadata") or {}
    if current_value is None:
        reason = metric.get("error") or f"{rule['metric_source']} data unavailable"
        return _result(rule, None, False, reason, False, metadata)
    if not rule["enabled"]:
        return _result(rule, current_value, False, "規則已停用", False, metadata)

    matched, reason = _match_rule(rule, current_value, metric.get("label") or rule["metric_source"], metric.get("unit") or "")
    return _result(rule, current_value, matched, reason, bool(matched and rule["notify_enabled"]), metadata)


def _match_rule(rule: dict[str, Any], value: float, label: str, unit: str) -> tuple[bool, str]:
    operator = rule["operator"]
    threshold_value = _safe_float(rule.get("threshold_value"))
    threshold_min = _safe_float(rule.get("threshold_min"))
    threshold_max = _safe_float(rule.get("threshold_max"))
    value_text = _format_value(value, unit)

    if operator == "gt" and threshold_value is not None:
        return value > threshold_value, f"{label} {value_text} {'>' if value > threshold_value else '<='} {_format_value(threshold_value, unit)}"
    if operator == "gte" and threshold_value is not None:
        return value >= threshold_value, f"{label} {value_text} {'>=' if value >= threshold_value else '<'} {_format_value(threshold_value, unit)}"
    if operator == "lt" and threshold_value is not None:
        return value < threshold_value, f"{label} {value_text} {'<' if value < threshold_value else '>='} {_format_value(threshold_value, unit)}"
    if operator == "lte" and threshold_value is not None:
        return value <= threshold_value, f"{label} {value_text} {'<=' if value <= threshold_value else '>'} {_format_value(threshold_value, unit)}"
    if operator == "between" and threshold_min is not None and threshold_max is not None:
        matched = threshold_min <= value <= threshold_max
        state = "位於" if matched else "未位於"
        return matched, f"{label} {value_text} {state} [{_format_value(threshold_min, unit)}, {_format_value(threshold_max, unit)}]"
    if operator == "outside_range" and threshold_min is not None and threshold_max is not None:
        matched = value <= threshold_min or value >= threshold_max
        state = "超出" if matched else "未超出"
        return matched, f"{label} {value_text} {state} [{_format_value(threshold_min, unit)}, {_format_value(threshold_max, unit)}]"
    return False, f"{label} {value_text} 無法以 operator={operator} 評估"


def _result(
    rule: dict[str, Any],
    current_value: float | None,
    matched: bool,
    reason: str,
    notify_candidate: bool,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "rule_key": rule["rule_key"],
        "name": rule["name"],
        "category": rule["category"],
        "metric_source": rule["metric_source"],
        "operator": rule["operator"],
        "threshold_value": rule.get("threshold_value"),
        "threshold_min": rule.get("threshold_min"),
        "threshold_max": rule.get("threshold_max"),
        "comparison_window": rule.get("comparison_window"),
        "enabled": rule["enabled"],
        "severity": rule["severity"],
        "notify_enabled": rule["notify_enabled"],
        "current_value": current_value,
        "matched": matched,
        "reason": reason,
        "notify_candidate": notify_candidate,
        "notification_type": "market_alert",
        "metadata": metadata,
    }


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    payload = dict(row)
    for key in ("threshold_value", "threshold_min", "threshold_max"):
        payload[key] = _decimal_to_float(payload.get(key))
    for key in ("created_at", "updated_at"):
        value = payload.get(key)
        payload[key] = value.isoformat() if value else None
    return payload


def _empty_quality_bucket(row: asyncpg.Record, days: int) -> dict[str, Any]:
    return {
        "rule_key": str(row["rule_key"]),
        "name": row["name"],
        "enabled": row["enabled"],
        "notify_enabled": row["notify_enabled"],
        "days": days,
        "trigger_count": 0,
        "sent_count": 0,
        "dedup_skipped_count": 0,
        "skipped_disabled_count": 0,
        "skipped_frequency_count": 0,
        "error_count": 0,
        "manual_test_count": 0,
        "no_trigger_count": 0,
        "data_unavailable_count": 0,
        "delivery_rate": 0.0,
        "dedup_rate": 0.0,
        "actionability_hint": "近期資料偏少，先持續觀察。",
    }


def _event_rule_key(event: dict[str, Any]) -> str | None:
    metadata = event.get("metadata_json") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    rule_key = metadata.get("rule_key") if isinstance(metadata, dict) else None
    if rule_key:
        return str(rule_key)
    topic = event.get("topic")
    if topic:
        return str(topic)
    notification_type = str(event.get("notification_type") or "")
    for prefix in ("manual_rule_test:", "market_alert:"):
        if notification_type.startswith(prefix):
            return notification_type[len(prefix):]
    return None


def _apply_quality_event(bucket: dict[str, Any], event: dict[str, Any]) -> None:
    notification_type = str(event.get("notification_type") or "")
    status = str(event.get("status") or "")
    skip_reason = str(event.get("skip_reason") or "")
    message_preview = str(event.get("message_preview") or "")
    is_manual = notification_type.startswith("manual_rule_test:")

    if is_manual:
        bucket["manual_test_count"] += 1

    if skip_reason == "no_trigger" or status == "no_trigger":
        bucket["no_trigger_count"] += 1
    if skip_reason in {"category_disabled", "alerts_or_category_disabled", "disabled"} or "停用" in message_preview or "disabled" in message_preview.lower():
        bucket["skipped_disabled_count"] += 1
    if skip_reason == "frequency_not_allowed":
        bucket["skipped_frequency_count"] += 1
    if skip_reason == "data_unavailable" or status == "data_unavailable":
        bucket["data_unavailable_count"] += 1
    if status in {"error", "failed"} or skip_reason == "error":
        bucket["error_count"] += 1
    if status == "dedup_skipped" or skip_reason == "dedup":
        bucket["dedup_skipped_count"] += 1

    if not is_manual and status in {"sent", "dry_run", "dedup_skipped", "error", "failed"}:
        bucket["trigger_count"] += 1
    if not is_manual and status == "sent":
        bucket["sent_count"] += 1


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def _quality_hint(bucket: dict[str, Any]) -> str:
    if not bucket.get("enabled") or not bucket.get("notify_enabled"):
        return "規則或推播目前關閉，若要納入背景通知請先確認啟用狀態。"
    if bucket["error_count"] > 0 or bucket["data_unavailable_count"] >= 3:
        return "資料異常偏多，請先確認資料來源是否穩定。"
    if bucket["skipped_disabled_count"] >= 3:
        return "規則或通知長期關閉，若不再使用可考慮停用推播或調整規則。"
    if bucket["trigger_count"] >= 3 and bucket["dedup_rate"] >= 0.5:
        return "近期重複命中偏多，可考慮調高門檻或拉長觀察週期。"
    if bucket["trigger_count"] >= 5 and bucket["delivery_rate"] < 0.35:
        return "命中不少但送出比例偏低，請檢查去重與通知開關設定。"
    if bucket["manual_test_count"] >= 3 and bucket["trigger_count"] == 0 and bucket["no_trigger_count"] >= bucket["manual_test_count"]:
        return "手動測試多但幾乎未命中，門檻可能偏嚴。"
    if bucket["trigger_count"] == 0 and bucket["no_trigger_count"] >= 5:
        return "近期多次未命中，若想更敏感可考慮降低門檻。"
    if bucket["sent_count"] > 0:
        return "近期已有實際送出，請觀察是否符合你的通知頻率期待。"
    return "近期狀態正常，暫無需要調整。"


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return _safe_float(value)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_value(value: float, unit: str) -> str:
    suffix = unit if unit else ""
    return f"{value:.2f}{suffix}"


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)
