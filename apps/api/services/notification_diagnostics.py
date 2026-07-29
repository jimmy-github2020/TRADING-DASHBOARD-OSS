from __future__ import annotations

from typing import Any

import asyncpg


async def fetch_notification_events(database_url: str, limit: int = 50) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_tables(conn)
        rows = await conn.fetch(
            """
            SELECT id, created_at, job_name, notification_type, status, skip_reason,
                   symbol, topic, message_preview, chat_id, dedup_key, metadata_json
            FROM notification_runtime_events
            ORDER BY created_at DESC
            LIMIT $1
            """,
            _clamp_limit(limit, 100),
        )
        return [_event_row(dict(row)) for row in rows]
    finally:
        await conn.close()


async def fetch_notification_job_runs(database_url: str, limit: int = 20) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_tables(conn)
        rows = await conn.fetch(
            """
            SELECT id, job_name, started_at, finished_at, duration_ms, targets_scanned,
                   disabled_skipped_count, frequency_skipped_count, triggered_count,
                   dedup_skipped_count, sent_count, error_count, final_status, metadata_json
            FROM notification_job_runs
            ORDER BY finished_at DESC
            LIMIT $1
            """,
            _clamp_limit(limit, 100),
        )
        return [_job_run_row(dict(row)) for row in rows]
    finally:
        await conn.close()


async def fetch_notification_diagnostics_summary(database_url: str) -> dict[str, Any]:
    runs = await fetch_notification_job_runs(database_url, limit=80)
    groups = {
        "latest_market_job": ["market_alert_rules", "alert_twii_move", "alert_vix", "alert_fear_greed", "midday_flash"],
        "latest_price_job": ["price_alert"],
        "latest_technical_job": ["technical_signal"],
        "latest_ai_summary_job": ["morning_brief", "closing_report"],
    }
    return {key: _summarize_latest(_latest_matching(runs, names), key) for key, names in groups.items()}


async def fetch_notification_metrics(database_url: str, days: int = 7) -> dict[str, Any]:
    days = max(1, min(int(days), 30))
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_tables(conn)
        rows = await conn.fetch(
            """
            SELECT notification_type, status, skip_reason, topic, metadata_json, job_name
            FROM notification_runtime_events
            WHERE created_at >= now() - ($1::int * interval '1 day')
            """,
            days,
        )
    finally:
        await conn.close()

    events = [dict(row) for row in rows]
    totals = {
        "events": len(events),
        "sent": 0,
        "skipped": 0,
        "dedup_skipped": 0,
        "error": 0,
        "manual_test": 0,
        "auto_trigger": 0,
    }
    type_stats: dict[str, dict[str, Any]] = {}
    rule_stats: dict[str, dict[str, Any]] = {}

    for event in events:
        notification_type = str(event.get("notification_type") or "unknown")
        status = str(event.get("status") or "unknown")
        skip_reason = event.get("skip_reason")
        metadata = event.get("metadata_json") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        source = _event_source(notification_type, str(event.get("job_name") or ""))
        rule_key = _rule_key_from_event(notification_type, event.get("topic"), metadata)

        if status == "sent":
            totals["sent"] += 1
        if status == "skipped":
            totals["skipped"] += 1
        if status == "dedup_skipped" or skip_reason == "dedup":
            totals["dedup_skipped"] += 1
        if status in {"error", "failed"}:
            totals["error"] += 1
        if source == "manual":
            totals["manual_test"] += 1
        else:
            totals["auto_trigger"] += 1

        type_bucket = type_stats.setdefault(
            notification_type,
            {"notification_type": notification_type, "count": 0, "sent": 0, "skipped": 0, "dedup_skipped": 0, "error": 0},
        )
        _bump_metric_bucket(type_bucket, status, skip_reason)

        if rule_key:
            rule_bucket = rule_stats.setdefault(
                rule_key,
                {"rule_key": rule_key, "count": 0, "sent": 0, "skipped": 0, "dedup_skipped": 0, "error": 0, "no_trigger": 0},
            )
            _bump_metric_bucket(rule_bucket, status, skip_reason)
            if skip_reason == "no_trigger":
                rule_bucket["no_trigger"] += 1

    total_events = totals["events"]
    success_rate = round(totals["sent"] / total_events, 3) if total_events else 0
    noise_rate = round((totals["skipped"] + totals["dedup_skipped"]) / total_events, 3) if total_events else 0
    return {
        "days": days,
        "totals": totals,
        "top_notification_types": _top_metric_rows(type_stats.values(), "count"),
        "top_rule_keys": _top_metric_rows(rule_stats.values(), "count"),
        "manual_vs_auto": {
            "manual_test": totals["manual_test"],
            "auto": totals["auto_trigger"],
        },
        "success_rate": success_rate,
        "noise_rate": noise_rate,
        "health_hints": _health_hints(totals, success_rate, noise_rate, rule_stats),
    }


def _latest_matching(runs: list[dict[str, Any]], names: list[str]) -> dict[str, Any] | None:
    for run in runs:
        if run["job_name"] in names:
            return run
    return None


def _summarize_latest(run: dict[str, Any] | None, key: str) -> dict[str, Any]:
    title_by_key = {
        "latest_market_job": "市場通知",
        "latest_price_job": "價格警示",
        "latest_technical_job": "技術警示",
        "latest_ai_summary_job": "AI 摘要",
    }
    if run is None:
        return {
            "job_name": None,
            "status": "empty",
            "reason": None,
            "message": f"{title_by_key[key]}尚無執行紀錄。",
            "updated_at": None,
        }

    reason = _reason_from_run(run)
    status = _status_from_run(run)
    message = _message_from_run(run, title_by_key[key], reason)
    return {
        "job_name": run["job_name"],
        "status": status,
        "reason": reason,
        "message": message,
        "updated_at": run["finished_at"],
    }


def _status_from_run(run: dict[str, Any]) -> str:
    if run["error_count"] > 0:
        return "error"
    if run["sent_count"] > 0:
        return "sent"
    if run["dedup_skipped_count"] > 0:
        return "dedup_skipped"
    if run["final_status"] == "dry_run":
        return "dry_run"
    return "skipped"


def _reason_from_run(run: dict[str, Any]) -> str | None:
    if run["disabled_skipped_count"] > 0:
        return "alerts_or_category_disabled"
    if run["frequency_skipped_count"] > 0:
        return "frequency_not_allowed"
    if run["dedup_skipped_count"] > 0:
        return "dedup"
    if run["error_count"] > 0:
        return "error"
    if run["triggered_count"] == 0 and run["sent_count"] == 0:
        return "no_trigger"
    return None


def _message_from_run(run: dict[str, Any], title: str, reason: str | None) -> str:
    if run["sent_count"] > 0:
        return f"{title}最近一次成功送出 {run['sent_count']} 筆。"
    if run["dedup_skipped_count"] > 0:
        return f"{title}最近一次有命中，但因 dedup 未重複推送 {run['dedup_skipped_count']} 筆。"
    if reason == "alerts_or_category_disabled":
        return f"{title}最近一次執行，但因總開關或分類開關關閉而跳過。"
    if reason == "frequency_not_allowed":
        return f"{title}最近一次執行，但摘要頻率設定不允許目前時段送出。"
    if reason == "error":
        return f"{title}最近一次執行發生錯誤，請查看事件列表。"
    if reason == "no_trigger":
        return f"{title}最近一次已執行，未達觸發條件。"
    return f"{title}最近一次狀態：{run['final_status']}。"


def _event_row(row: dict[str, Any]) -> dict[str, Any]:
    notification_type = row.get("notification_type") or ""
    job_name = row.get("job_name") or ""
    row["created_at"] = row["created_at"].isoformat()
    row["chat_id_masked"] = _mask_chat_id(row.pop("chat_id", None))
    row["metadata"] = row.pop("metadata_json", None) or {}
    row["category"] = _event_category(notification_type)
    row["source"] = _event_source(notification_type, job_name)
    return row


def _event_category(notification_type: str) -> str:
    if notification_type == "system_mode_change":
        return "system"
    if notification_type in {"summary_test", "manual_test_morning_brief", "manual_test_closing_brief", "morning_brief", "closing_report"}:
        return "summary"
    if notification_type.startswith("manual_test_") or notification_type.startswith("manual_rule_test:") or notification_type.startswith("alert_"):
        return "alert"
    if notification_type in {"alert_test", "price_alert", "technical_signal"}:
        return "alert"
    if (
        notification_type.startswith("price_alert:")
        or notification_type.startswith("signal_")
        or notification_type.startswith("market_alert:")
    ):
        return "alert"
    return "system" if notification_type.startswith("system_") else "alert"


def _event_source(notification_type: str, job_name: str) -> str:
    if notification_type.startswith("manual_test_") or notification_type.startswith("manual_rule_test:") or notification_type in {"summary_test", "alert_test"}:
        return "manual"
    if job_name in {"manual_test", "manual_mode_change"}:
        return "manual"
    return "background"


def _rule_key_from_event(notification_type: str, topic: Any, metadata: dict[str, Any]) -> str | None:
    if notification_type == "system_mode_change" or notification_type.startswith("manual_test_"):
        return None
    rule_key = metadata.get("rule_key")
    if rule_key:
        return str(rule_key)
    if notification_type.startswith("manual_rule_test:"):
        return notification_type.split(":", 1)[1]
    if notification_type.startswith("market_alert:"):
        return notification_type.split(":", 1)[1]
    if topic and notification_type == "market_alert" and str(topic) not in {"VIX", "Fear & Greed", "台股大盤漲跌"}:
        return str(topic)
    return None


def _bump_metric_bucket(bucket: dict[str, Any], status: str, skip_reason: Any) -> None:
    bucket["count"] += 1
    if status == "sent":
        bucket["sent"] += 1
    if status == "skipped":
        bucket["skipped"] += 1
    if status == "dedup_skipped" or skip_reason == "dedup":
        bucket["dedup_skipped"] += 1
    if status in {"error", "failed"}:
        bucket["error"] += 1


def _top_metric_rows(rows: Any, key: str, limit: int = 5) -> list[dict[str, Any]]:
    return sorted((dict(row) for row in rows), key=lambda item: item.get(key, 0), reverse=True)[:limit]


def _health_hints(
    totals: dict[str, int],
    success_rate: float,
    noise_rate: float,
    rule_stats: dict[str, dict[str, Any]],
) -> list[str]:
    hints: list[str] = []
    total_events = totals["events"]
    if total_events == 0:
        return ["近 7 天尚無通知事件，系統可能偏安靜或尚未進入排程時段。"]
    if totals["dedup_skipped"] >= max(3, totals["sent"]):
        hints.append("近期 dedup 偏高，可能有規則反覆命中；可檢查門檻或延長觀察週期。")
    if noise_rate >= 0.7:
        hints.append("跳過與去重比例偏高，建議確認通知設定、摘要頻率與規則門檻是否過密。")
    if success_rate < 0.1 and totals["skipped"] > totals["sent"]:
        hints.append("送出比例偏低且跳過偏多，建議檢查 notification settings 或目前是否仍在 Dry-run。")
    if totals["manual_test"] > totals["auto_trigger"]:
        hints.append("手動測試多於背景事件，代表系統仍在調校階段，正式觸發量可再觀察。")
    noisy_rules = [rule_key for rule_key, stat in rule_stats.items() if stat.get("dedup_skipped", 0) >= 3]
    if noisy_rules:
        hints.append(f"{', '.join(noisy_rules[:3])} 重複命中較多，可優先檢視門檻。")
    if totals["error"] > 0:
        hints.append("近期有通知錯誤事件，建議查看 recent events 的 error 訊息。")
    return hints or ["通知品質看起來健康：近期未見明顯過吵、錯誤或重複推播。"]


def _job_run_row(row: dict[str, Any]) -> dict[str, Any]:
    row["started_at"] = row["started_at"].isoformat()
    row["finished_at"] = row["finished_at"].isoformat()
    row["metadata"] = row.pop("metadata_json", None) or {}
    return row


def _mask_chat_id(chat_id: str | None) -> str | None:
    if not chat_id:
        return None
    if len(chat_id) <= 6:
        return f"{chat_id[:1]}***{chat_id[-1:]}"
    return f"{chat_id[:3]}***{chat_id[-3:]}"


def _clamp_limit(limit: int, maximum: int) -> int:
    return max(1, min(limit, maximum))


async def _ensure_tables(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_job_runs (
          id SERIAL PRIMARY KEY,
          job_name VARCHAR(80) NOT NULL,
          started_at TIMESTAMPTZ NOT NULL,
          finished_at TIMESTAMPTZ NOT NULL,
          duration_ms INTEGER NOT NULL,
          targets_scanned INTEGER NOT NULL DEFAULT 0,
          disabled_skipped_count INTEGER NOT NULL DEFAULT 0,
          frequency_skipped_count INTEGER NOT NULL DEFAULT 0,
          triggered_count INTEGER NOT NULL DEFAULT 0,
          dedup_skipped_count INTEGER NOT NULL DEFAULT 0,
          sent_count INTEGER NOT NULL DEFAULT 0,
          error_count INTEGER NOT NULL DEFAULT 0,
          final_status VARCHAR(30) NOT NULL,
          metadata_json JSONB
        )
        """
    )
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
