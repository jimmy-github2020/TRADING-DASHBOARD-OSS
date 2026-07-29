from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

import requests

from config import Settings, load_settings
from repository import MarketRepository
from telegram.preferences import is_notification_enabled, should_send_summary_now
from telegram.sender import send_message
from telegram.templates import (
    build_closing_report,
    build_fallback_message,
    build_fear_greed_alert,
    build_market_rule_alert,
    build_midday_flash,
    build_morning_brief,
    build_price_alert,
    build_summary_metadata,
    build_technical_alert,
    build_twii_move_alert,
    build_vix_alert,
)


@dataclass(frozen=True)
class JobResult:
    notification_type: str
    status: str
    error: str | None = None
    scanned_count: int = 0
    targets_scanned: int = 0
    disabled_skipped_count: int = 0
    frequency_skipped_count: int = 0
    triggered_count: int = 0
    sent_count: int = 0
    dedup_skipped_count: int = 0
    error_count: int = 0
    metadata: dict[str, Any] | None = None


def morning_brief_job(settings: Settings | None = None) -> JobResult:
    settings = _resolve_settings(settings)
    started_at = _job_started("morning_brief", settings)
    try:
        market = {"tw": _latest_market(settings, "^TWII"), "us": _latest_market(settings, "SPY")}
        sentiment = _get_json(settings, "/api/v1/sentiment?scope=tw")
        news = (_get_json(settings, "/api/v1/news?scope=tw&limit=3").get("items") or [])
        message = build_morning_brief(market, sentiment, news)
    except Exception as exc:
        print(f"[telegram:morning_brief:fallback] {exc}")
        message = build_fallback_message("📊 幾米投資晨報")
    result = _send_to_enabled_targets(settings, "morning_brief", message, "ai_summary", check_frequency=True)
    result = replace(result, metadata=build_summary_metadata(message))
    return _job_finished("morning_brief", started_at, settings, result)


def midday_flash_job(settings: Settings | None = None) -> JobResult:
    settings = _resolve_settings(settings)
    started_at = _job_started("midday_flash", settings)
    try:
        sentiment = _get_json(settings, "/api/v1/sentiment?scope=tw")
        message = build_midday_flash(sentiment)
    except Exception as exc:
        print(f"[telegram:midday_flash:fallback] {exc}")
        message = build_fallback_message("⚡ 幾米午間快訊")
    result = _send_to_enabled_targets(settings, "midday_flash", message, "market")
    result = replace(result, metadata=build_summary_metadata(message))
    return _job_finished("midday_flash", started_at, settings, result)


def closing_report_job(settings: Settings | None = None) -> JobResult:
    settings = _resolve_settings(settings)
    started_at = _job_started("closing_report", settings)
    try:
        market = {"tw": _latest_market(settings, "^TWII")}
        institutions = _get_json(settings, "/api/v1/institutional/flow?market=TAIEX")
        watchlist = _get_json(settings, "/api/v1/technical/ranking?market=TAIEX&limit=5").get("rankings") or []
        message = build_closing_report(market, institutions, watchlist)
    except Exception as exc:
        print(f"[telegram:closing_report:fallback] {exc}")
        message = build_fallback_message("📌 幾米收盤報告")
    result = _send_to_enabled_targets(settings, "closing_report", message, "ai_summary", check_frequency=True)
    result = replace(result, metadata=build_summary_metadata(message))
    return _job_finished("closing_report", started_at, settings, result)


def twii_alert_job(settings: Settings | None = None) -> JobResult:
    settings = _resolve_settings(settings)
    started_at = _job_started("alert_twii_move", settings)
    preflight = _preflight_targets(settings, "alert_twii_move", "market")
    if preflight:
        return _job_finished("alert_twii_move", started_at, settings, preflight)
    try:
        market = _latest_market(settings, "^TWII")
        change_pct = _to_float(market.get("change_pct"))
        if change_pct is None or abs(change_pct) < 2:
            result = _skipped("alert_twii_move", f"TWII change_pct={change_pct}")
            _record_runtime_event(
                settings,
                job_name="alert_twii_move",
                notification_type="alert_twii_move",
                status="skipped",
                skip_reason="no_trigger",
                symbol="^TWII",
                metadata={"change_pct": change_pct},
            )
            return _job_finished("alert_twii_move", started_at, settings, result)
        direction = "up" if change_pct > 0 else "down"
        result = _send_to_enabled_targets(
            settings,
            f"alert_twii_{direction}",
            build_twii_move_alert(market),
            "market",
            job_name="alert_twii_move",
            topic="台股大盤漲跌",
        )
        return _job_finished("alert_twii_move", started_at, settings, result)
    except Exception as exc:
        print(f"[telegram:alert_twii:error] {exc}")
        result = JobResult(notification_type="alert_twii_move", status="skipped", error=str(exc), error_count=1)
        return _job_finished("alert_twii_move", started_at, settings, result)


def vix_alert_job(settings: Settings | None = None) -> JobResult:
    settings = _resolve_settings(settings)
    started_at = _job_started("alert_vix", settings)
    preflight = _preflight_targets(settings, "alert_vix", "market")
    if preflight:
        return _job_finished("alert_vix", started_at, settings, preflight)
    try:
        sentiment = _get_json(settings, "/api/v1/sentiment?scope=tw")
        vix = _to_float(sentiment.get("vix"))
        if vix is None or 12 <= vix <= 25:
            result = _skipped("alert_vix", f"vix={vix}")
            _record_runtime_event(
                settings,
                job_name="alert_vix",
                notification_type="alert_vix",
                status="skipped",
                skip_reason="no_trigger",
                topic="VIX",
                metadata={"vix": vix},
            )
            return _job_finished("alert_vix", started_at, settings, result)
        state = "high" if vix > 25 else "low"
        result = _send_to_enabled_targets(
            settings,
            f"alert_vix_{state}",
            build_vix_alert(sentiment),
            "market",
            job_name="alert_vix",
            topic="VIX",
        )
        return _job_finished("alert_vix", started_at, settings, result)
    except Exception as exc:
        print(f"[telegram:alert_vix:error] {exc}")
        result = JobResult(notification_type="alert_vix", status="skipped", error=str(exc), error_count=1)
        return _job_finished("alert_vix", started_at, settings, result)


def fear_greed_alert_job(settings: Settings | None = None) -> JobResult:
    settings = _resolve_settings(settings)
    started_at = _job_started("alert_fear_greed", settings)
    preflight = _preflight_targets(settings, "alert_fear_greed", "market")
    if preflight:
        return _job_finished("alert_fear_greed", started_at, settings, preflight)
    try:
        sentiment = _get_json(settings, "/api/v1/sentiment?scope=tw")
        score = _to_float(sentiment.get("fear_greed_score"))
        if score is None or 20 <= score <= 80:
            result = _skipped("alert_fear_greed", f"fear_greed_score={score}")
            _record_runtime_event(
                settings,
                job_name="alert_fear_greed",
                notification_type="alert_fear_greed",
                status="skipped",
                skip_reason="no_trigger",
                topic="Fear & Greed",
                metadata={"fear_greed_score": score},
            )
            return _job_finished("alert_fear_greed", started_at, settings, result)
        state = "fear" if score < 20 else "greed"
        result = _send_to_enabled_targets(
            settings,
            f"alert_fear_greed_{state}",
            build_fear_greed_alert(sentiment),
            "market",
            job_name="alert_fear_greed",
            topic="Fear & Greed",
        )
        return _job_finished("alert_fear_greed", started_at, settings, result)
    except Exception as exc:
        print(f"[telegram:alert_fear_greed:error] {exc}")
        result = JobResult(notification_type="alert_fear_greed", status="skipped", error=str(exc), error_count=1)
        return _job_finished("alert_fear_greed", started_at, settings, result)


def market_alert_rules_job(settings: Settings | None = None) -> JobResult:
    settings = _resolve_settings(settings)
    started_at = _job_started("market_alert_rules", settings)
    try:
        payload = _post_json(settings, "/api/v1/alert-rules/evaluate")
        results = [item for item in (payload.get("results") or []) if isinstance(item, dict)]
    except Exception as exc:
        print(f"[telegram:market_alert_rules:error] {exc}")
        result = JobResult(notification_type="market_alert", status="skipped", error=str(exc), error_count=1)
        return _job_finished("market_alert_rules", started_at, settings, result)

    targets = _notification_targets(settings)
    eligible_targets, disabled_skipped_count = _eligible_targets(settings, targets, "market", "market_alert")
    triggered_count = 0
    sent_count = 0
    dedup_skipped_count = 0
    error_count = 0
    last_result = JobResult(notification_type="market_alert", status="skipped")

    if not eligible_targets:
        result = JobResult(
            notification_type="market_alert",
            status="skipped",
            scanned_count=len(results),
            targets_scanned=len(targets),
            disabled_skipped_count=disabled_skipped_count,
        )
        return _job_finished("market_alert_rules", started_at, settings, result)

    for item in results:
        rule_key = str(item.get("rule_key") or "unknown_rule")
        reason = str(item.get("reason") or "")
        metadata = {
            "rule_key": rule_key,
            "metric_source": item.get("metric_source"),
            "current_value": item.get("current_value"),
            "matched": item.get("matched"),
            "notify_candidate": item.get("notify_candidate"),
            "reason": reason,
            "severity": item.get("severity"),
        }
        if not item.get("matched"):
            skip_reason = "data_unavailable" if item.get("current_value") is None else "no_trigger"
            _record_runtime_event(
                settings,
                job_name="market_alert_rules",
                notification_type="market_alert",
                status="skipped",
                skip_reason=skip_reason,
                topic=rule_key,
                message_preview=reason,
                metadata=metadata,
            )
            last_result = _skipped("market_alert", f"{rule_key} {reason}")
            continue
        if not item.get("notify_candidate"):
            _record_runtime_event(
                settings,
                job_name="market_alert_rules",
                notification_type="market_alert",
                status="skipped",
                skip_reason="category_disabled",
                topic=rule_key,
                message_preview=reason,
                metadata=metadata,
            )
            last_result = _skipped("market_alert", f"{rule_key} notify disabled")
            continue

        triggered_count += 1
        message = build_market_rule_alert(item)
        for target in eligible_targets:
            try:
                result = _send_and_record(
                    settings,
                    f"market_alert:{rule_key}",
                    message,
                    chat_id_override=str(target["chat_id"]),
                    job_name="market_alert_rules",
                    topic=rule_key,
                    metadata=metadata,
                )
                last_result = result
                if result.status == "sent":
                    sent_count += 1
                if result.status == "skipped":
                    dedup_skipped_count += result.dedup_skipped_count or 1
                if result.status == "failed":
                    error_count += 1
            except Exception as exc:
                error_count += 1
                print(f"[telegram:market_alert_rules:item_error] rule_key={rule_key} error={exc}")

    status = "dry_run" if settings.notification_dry_run and triggered_count else "sent" if sent_count else last_result.status
    result = JobResult(
        notification_type="market_alert",
        status=status,
        error=last_result.error,
        scanned_count=len(results),
        targets_scanned=len(targets),
        disabled_skipped_count=disabled_skipped_count,
        triggered_count=triggered_count,
        sent_count=sent_count,
        dedup_skipped_count=dedup_skipped_count,
        error_count=error_count,
    )
    return _job_finished("market_alert_rules", started_at, settings, result)


def price_alert_job(settings: Settings | None = None) -> JobResult:
    settings = _resolve_settings(settings)
    started_at = _job_started("price_alert", settings)
    repository = MarketRepository(settings.database_url)
    with repository.connect() as conn:
        alerts = repository.fetch_active_price_alerts(conn)

    scanned_count = len(alerts)
    targets_scanned = 0
    disabled_skipped_count = 0
    triggered_count = 0
    sent_count = 0
    dedup_skipped_count = 0
    error_count = 0
    last_result = JobResult(notification_type="price_alert", status="skipped")

    for alert in alerts:
        symbol = str(alert["symbol"]).strip().upper()
        alert_type = str(alert["alert_type"])
        chat_id = str(alert["chat_id"])
        threshold = float(alert["threshold"])
        targets_scanned += 1
        try:
            target = _notification_target(settings, chat_id)
            if not target:
                disabled_skipped_count += 1
                last_result = _skipped("price_alert", f"chat_id={chat_id} settings missing")
                _record_runtime_skip(
                    settings,
                    "price_alert",
                    "price_alert",
                    "settings missing",
                    chat_id=chat_id,
                    symbol=symbol,
                    metadata={"alert_type": alert_type, "threshold": threshold},
                )
                continue
            allowed, reason = is_notification_enabled(target, "price")
            if not allowed:
                disabled_skipped_count += 1
                last_result = _skipped("price_alert", f"chat_id={chat_id} {reason}")
                _record_runtime_skip(
                    settings,
                    "price_alert",
                    "price_alert",
                    reason,
                    chat_id=chat_id,
                    symbol=symbol,
                    metadata={"alert_type": alert_type, "threshold": threshold},
                )
                continue

            price = _to_float(_get_json(settings, f"/api/v1/stocks/{symbol}/price").get("price"))
            if price is None:
                last_result = _skipped("price_alert", f"{symbol} price missing")
                _record_runtime_skip(
                    settings,
                    "price_alert",
                    "price_alert",
                    "price missing",
                    chat_id=chat_id,
                    symbol=symbol,
                    metadata={"alert_type": alert_type, "threshold": threshold},
                )
                continue

            should_trigger = (alert_type == "above" and price >= threshold) or (
                alert_type == "below" and price <= threshold
            )
            if not should_trigger:
                last_result = _skipped("price_alert", f"{symbol} price={price} threshold={threshold} type={alert_type}")
                _record_runtime_skip(
                    settings,
                    "price_alert",
                    "price_alert",
                    "no trigger",
                    chat_id=chat_id,
                    symbol=symbol,
                    metadata={"alert_type": alert_type, "threshold": threshold, "price": price},
                )
                continue

            triggered_count += 1
            result = _send_and_record(
                settings,
                f"price_alert:{symbol}:{alert_type}",
                build_price_alert(symbol, price, threshold, alert_type),
                chat_id_override=chat_id,
                job_name="price_alert",
                symbol=symbol,
                metadata={"alert_type": alert_type, "threshold": threshold, "price": price},
            )
            last_result = result
            if result.status == "sent":
                sent_count += 1
                with repository.connect() as conn:
                    repository.update_price_alert_triggered(conn, int(alert["id"]))
                    conn.commit()
            if result.status == "skipped":
                dedup_skipped_count += result.dedup_skipped_count or 1
            if result.status == "failed":
                error_count += 1
        except Exception as exc:
            error_count += 1
            print(f"[telegram:price_alert:error] symbol={symbol} error={exc}")
            last_result = JobResult(notification_type="price_alert", status="skipped", error=str(exc))

    status = "dry_run" if settings.notification_dry_run and triggered_count else "sent" if sent_count else last_result.status
    result = JobResult(
        notification_type="price_alert",
        status=status,
        error=last_result.error,
        scanned_count=scanned_count,
        targets_scanned=targets_scanned,
        disabled_skipped_count=disabled_skipped_count,
        triggered_count=triggered_count,
        sent_count=sent_count,
        dedup_skipped_count=dedup_skipped_count,
        error_count=error_count,
    )
    return _job_finished("price_alert", started_at, settings, result)


def technical_signal_job(settings: Settings | None = None) -> JobResult:
    settings = _resolve_settings(settings)
    started_at = _job_started("technical_signal", settings)
    try:
        signals = _get_json_list(settings, "/api/v1/technical/signals?watchlist=true")
    except Exception as exc:
        print(f"[telegram:technical_signal:error] {exc}")
        result = JobResult(notification_type="technical_signal", status="skipped", error=str(exc), error_count=1)
        return _job_finished("technical_signal", started_at, settings, result)

    targets = _notification_targets(settings)
    eligible_targets, disabled_skipped_count = _eligible_targets(settings, targets, "technical", "technical_signal")

    triggered_count = 0
    sent_count = 0
    dedup_skipped_count = 0
    error_count = 0
    last_result = JobResult(notification_type="technical_signal", status="skipped")

    if not eligible_targets:
        result = JobResult(
            notification_type="technical_signal",
            status="skipped",
            scanned_count=len(signals),
            targets_scanned=len(targets),
            disabled_skipped_count=disabled_skipped_count,
        )
        return _job_finished("technical_signal", started_at, settings, result)

    for item in signals:
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        candidates: list[tuple[str, Any]] = []
        rsi = _to_float(item.get("rsi"))
        if rsi is not None and rsi > 70:
            candidates.append(("rsi_overbought", rsi))
        if rsi is not None and rsi < 30:
            candidates.append(("rsi_oversold", rsi))
        if item.get("macd_cross") == "golden":
            candidates.append(("macd_golden", item.get("macd")))
        if item.get("macd_cross") == "death":
            candidates.append(("macd_death", item.get("macd")))

        for signal_type, value in candidates:
            for target in eligible_targets:
                try:
                    triggered_count += 1
                    result = _send_and_record(
                        settings,
                        f"signal_{signal_type}:{symbol}",
                        build_technical_alert(symbol, signal_type, value),
                        chat_id_override=str(target["chat_id"]),
                        job_name="technical_signal",
                        symbol=symbol,
                        metadata={"signal_type": signal_type, "value": value},
                    )
                    last_result = result
                    if result.status == "sent":
                        sent_count += 1
                    if result.status == "skipped":
                        dedup_skipped_count += result.dedup_skipped_count or 1
                    if result.status == "failed":
                        error_count += 1
                except Exception as exc:
                    error_count += 1
                    print(f"[telegram:technical_signal:item_error] symbol={symbol} signal={signal_type} error={exc}")

    status = "dry_run" if settings.notification_dry_run and triggered_count else "sent" if sent_count else last_result.status
    result = JobResult(
        notification_type="technical_signal",
        status=status,
        error=last_result.error,
        scanned_count=len(signals),
        targets_scanned=len(targets),
        disabled_skipped_count=disabled_skipped_count,
        triggered_count=triggered_count,
        sent_count=sent_count,
        dedup_skipped_count=dedup_skipped_count,
        error_count=error_count,
    )
    return _job_finished("technical_signal", started_at, settings, result)


def _send_to_enabled_targets(
    settings: Settings,
    notification_type: str,
    message: str,
    category: str,
    check_frequency: bool = False,
    job_name: str | None = None,
    symbol: str | None = None,
    topic: str | None = None,
) -> JobResult:
    job_name = job_name or notification_type
    targets = _notification_targets(settings)
    targets_scanned = len(targets)
    disabled_skipped_count = 0
    frequency_skipped_count = 0
    triggered_count = 0
    sent_count = 0
    dedup_skipped_count = 0
    error_count = 0
    last_result = JobResult(notification_type=notification_type, status="skipped")

    for target in targets:
        chat_id = str(target["chat_id"])
        try:
            allowed, reason = is_notification_enabled(target, category)
            if not allowed:
                disabled_skipped_count += 1
                last_result = _skipped(notification_type, f"chat_id={chat_id} {reason}")
                _record_runtime_skip(
                    settings,
                    job_name,
                    notification_type,
                    reason,
                    chat_id=chat_id,
                    symbol=symbol,
                    topic=topic,
                    metadata={"category": category},
                )
                continue

            if check_frequency:
                frequency_allowed, frequency_reason = should_send_summary_now(str(target.get("summary_frequency") or "off"))
                if not frequency_allowed:
                    frequency_skipped_count += 1
                    last_result = _skipped(notification_type, f"chat_id={chat_id} {frequency_reason}")
                    _record_runtime_skip(
                        settings,
                        job_name,
                        notification_type,
                        frequency_reason,
                        chat_id=chat_id,
                        symbol=symbol,
                        topic=topic,
                        metadata={
                            "category": category,
                            "summary_frequency": target.get("summary_frequency"),
                        },
                    )
                    continue

            triggered_count += 1
            result = _send_and_record(
                settings,
                notification_type,
                message,
                chat_id_override=chat_id,
                job_name=job_name,
                symbol=symbol,
                topic=topic,
                metadata={"category": category},
            )
            last_result = result
            if result.status == "sent":
                sent_count += 1
            if result.status == "skipped":
                dedup_skipped_count += result.dedup_skipped_count or 1
            if result.status == "failed":
                error_count += 1
        except Exception as exc:
            error_count += 1
            print(f"[telegram:{notification_type}:target_error] chat_id={chat_id} error={exc}")

    status = "dry_run" if settings.notification_dry_run and triggered_count else "sent" if sent_count else last_result.status
    return JobResult(
        notification_type=notification_type,
        status=status,
        error=last_result.error,
        targets_scanned=targets_scanned,
        disabled_skipped_count=disabled_skipped_count,
        frequency_skipped_count=frequency_skipped_count,
        triggered_count=triggered_count,
        sent_count=sent_count,
        dedup_skipped_count=dedup_skipped_count,
        error_count=error_count,
    )


def _resolve_settings(settings: Settings | None) -> Settings:
    if settings is not None:
        return settings

    loaded = load_settings()
    try:
        repository = MarketRepository(loaded.database_url)
        with repository.connect() as conn:
            dry_run = repository.fetch_notification_dry_run(conn, loaded.notification_dry_run)
            conn.commit()
        if dry_run != loaded.notification_dry_run:
            print(f"[telegram:runtime-mode] db_notification_dry_run={dry_run}")
        return replace(loaded, notification_dry_run=dry_run)
    except Exception as exc:
        print(f"[telegram:runtime-mode-warning] fallback_to_env error={exc}")
        return loaded


def _preflight_targets(
    settings: Settings,
    notification_type: str,
    category: str,
    check_frequency: bool = False,
) -> JobResult | None:
    targets = _notification_targets(settings)
    disabled_skipped_count = 0
    frequency_skipped_count = 0
    eligible_count = 0
    for target in targets:
        chat_id = str(target["chat_id"])
        allowed, reason = is_notification_enabled(target, category)
        if not allowed:
            disabled_skipped_count += 1
            _skipped(notification_type, f"chat_id={chat_id} {reason}")
            _record_runtime_skip(
                settings,
                notification_type,
                notification_type,
                reason,
                chat_id=chat_id,
                metadata={"category": category},
            )
            continue
        if check_frequency:
            frequency_allowed, frequency_reason = should_send_summary_now(str(target.get("summary_frequency") or "off"))
            if not frequency_allowed:
                frequency_skipped_count += 1
                _skipped(notification_type, f"chat_id={chat_id} {frequency_reason}")
                _record_runtime_skip(
                    settings,
                    notification_type,
                    notification_type,
                    frequency_reason,
                    chat_id=chat_id,
                    metadata={
                        "category": category,
                        "summary_frequency": target.get("summary_frequency"),
                    },
                )
                continue
        eligible_count += 1

    if eligible_count:
        return None
    return JobResult(
        notification_type=notification_type,
        status="skipped",
        targets_scanned=len(targets),
        disabled_skipped_count=disabled_skipped_count,
        frequency_skipped_count=frequency_skipped_count,
    )


def _notification_targets(settings: Settings) -> list[dict]:
    repository = MarketRepository(settings.database_url)
    with repository.connect() as conn:
        return repository.fetch_notification_targets(conn)


def _notification_target(settings: Settings, chat_id: str) -> dict | None:
    repository = MarketRepository(settings.database_url)
    with repository.connect() as conn:
        return repository.fetch_notification_settings(conn, chat_id)


def _eligible_targets(
    settings: Settings,
    targets: list[dict],
    category: str,
    notification_type: str,
) -> tuple[list[dict], int]:
    eligible: list[dict] = []
    disabled_skipped_count = 0
    for target in targets:
        allowed, reason = is_notification_enabled(target, category)
        if allowed:
            eligible.append(target)
        else:
            disabled_skipped_count += 1
            _skipped(category, f"chat_id={target.get('chat_id')} {reason}")
            _record_runtime_skip(
                settings,
                notification_type,
                notification_type,
                reason,
                chat_id=str(target.get("chat_id") or ""),
                metadata={"category": category},
            )
    return eligible, disabled_skipped_count


def _get_json(settings: Settings, path: str) -> dict[str, Any]:
    url = f"{settings.api_base_url.rstrip('/')}{path}"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected API response for {path}")
    return data


def _post_json(settings: Settings, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{settings.api_base_url.rstrip('/')}{path}"
    response = requests.post(url, json=payload or {}, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected API response for {path}")
    return data


def _get_json_list(settings: Settings, path: str) -> list[dict[str, Any]]:
    url = f"{settings.api_base_url.rstrip('/')}{path}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError(f"Unexpected API response for {path}")
    return [item for item in data if isinstance(item, dict)]


def _latest_market(settings: Settings, symbol: str) -> dict[str, Any]:
    payload = _get_json(settings, f"/api/v1/market/candles?symbol={symbol}&interval=1d&range=1mo")
    candles = payload.get("candles") or []
    if not candles:
        raise ValueError(f"No candles returned for {symbol}")
    latest = candles[-1]
    previous = candles[-2] if len(candles) >= 2 else None
    price = _to_float(latest.get("close"))
    previous_price = _to_float(previous.get("close")) if previous else None
    change_pct = None
    if price is not None and previous_price:
        change_pct = ((price - previous_price) / previous_price) * 100
    return {
        "symbol": symbol,
        "price": price,
        "change_pct": change_pct,
        "volume": latest.get("volume"),
    }


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _skipped(notification_type: str, reason: str) -> JobResult:
    print(f"[telegram:{notification_type}] status=skipped reason={reason}")
    return JobResult(notification_type=notification_type, status="skipped")


def _job_started(job_name: str, settings: Settings) -> datetime:
    started_at = datetime.now()
    mode = "dry-run" if settings.notification_dry_run else "send"
    print(f"[telegram:job:start] job_name={job_name} started_at={started_at.isoformat()} mode={mode}")
    return started_at


def _job_finished(job_name: str, started_at: datetime, settings: Settings, result: JobResult) -> JobResult:
    finished_at = datetime.now()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    mode = "dry-run" if settings.notification_dry_run else "send"
    print(
        "[telegram:job:finish] "
        f"job_name={job_name} started_at={started_at.isoformat()} finished_at={finished_at.isoformat()} "
        f"mode={mode} status={result.status} alerts_scanned={result.scanned_count} "
        f"targets_scanned={result.targets_scanned} disabled_skipped_count={result.disabled_skipped_count} "
        f"frequency_skipped_count={result.frequency_skipped_count} triggered_count={result.triggered_count} "
        f"sent_count={result.sent_count} dedup_skipped_count={result.dedup_skipped_count} "
        f"error_count={result.error_count}"
    )
    try:
        repository = MarketRepository(settings.database_url)
        with repository.connect() as conn:
            repository.record_notification_job_run(
                conn,
                job_name=job_name,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                targets_scanned=result.targets_scanned,
                disabled_skipped_count=result.disabled_skipped_count,
                frequency_skipped_count=result.frequency_skipped_count,
                triggered_count=result.triggered_count,
                dedup_skipped_count=result.dedup_skipped_count,
                sent_count=result.sent_count,
                error_count=result.error_count,
                final_status=result.status,
                metadata={
                    "mode": mode,
                    "scanned_count": result.scanned_count,
                    "notification_type": result.notification_type,
                    "error": result.error,
                    **(result.metadata or {}),
                },
            )
            conn.commit()
    except Exception as exc:
        print(f"[telegram:diagnostics-warning] job_run_write_failed job_name={job_name} error={exc}")
    return result


def _send_and_record(
    settings: Settings,
    notification_type: str,
    message: str,
    chat_id_override: str | None = None,
    job_name: str | None = None,
    symbol: str | None = None,
    topic: str | None = None,
    metadata: dict | None = None,
) -> JobResult:
    job_name = job_name or notification_type
    chat_id = chat_id_override or settings.telegram_chat_id
    result = send_message(
        bot_token=settings.telegram_bot_token,
        chat_id=chat_id,
        html=message,
        dry_run=settings.notification_dry_run,
        notification_type=notification_type,
        redis_url=settings.redis_url,
    )
    if result.skipped:
        _record_runtime_event(
            settings,
            job_name=job_name,
            notification_type=notification_type,
            status="dedup_skipped",
            skip_reason="dedup",
            symbol=symbol,
            topic=topic,
            message_preview=_plain_preview(message),
            chat_id=chat_id,
            metadata=metadata,
        )
        return JobResult(notification_type=notification_type, status="skipped", error=result.error, dedup_skipped_count=1)

    repository = MarketRepository(settings.database_url)
    chat_id = chat_id or "unconfigured"
    status = result.status if result.status != "failed" else "failed"
    preview = _plain_preview(message)
    with repository.connect() as conn:
        repository.record_notification_delivery(
            conn,
            chat_id=chat_id,
            notification_type=notification_type,
            message_preview=preview,
            status=status,
            error_message=result.error,
        )
        conn.commit()
    _record_runtime_event(
        settings,
        job_name=job_name,
        notification_type=notification_type,
        status="error" if result.status == "failed" else result.status,
        skip_reason="error" if result.status == "failed" else None,
        symbol=symbol,
        topic=topic,
        message_preview=preview,
        chat_id=chat_id,
        metadata=metadata,
    )
    print(f"[telegram:{notification_type}] status={result.status} error={result.error or ''}")
    return JobResult(notification_type=notification_type, status=result.status, error=result.error)


def _record_runtime_skip(
    settings: Settings,
    job_name: str,
    notification_type: str,
    reason: str,
    chat_id: str | None = None,
    symbol: str | None = None,
    topic: str | None = None,
    metadata: dict | None = None,
) -> None:
    _record_runtime_event(
        settings,
        job_name=job_name,
        notification_type=notification_type,
        status="skipped",
        skip_reason=_skip_reason_code(reason),
        chat_id=chat_id,
        symbol=symbol,
        topic=topic,
        metadata={**(metadata or {}), "reason": reason},
    )


def _record_runtime_event(
    settings: Settings,
    job_name: str | None,
    notification_type: str,
    status: str,
    skip_reason: str | None = None,
    symbol: str | None = None,
    topic: str | None = None,
    message_preview: str | None = None,
    chat_id: str | None = None,
    dedup_key: str | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        repository = MarketRepository(settings.database_url)
        with repository.connect() as conn:
            repository.record_notification_runtime_event(
                conn,
                job_name=job_name,
                notification_type=notification_type,
                status=status,
                skip_reason=skip_reason,
                symbol=symbol,
                topic=topic,
                message_preview=message_preview,
                chat_id=chat_id,
                dedup_key=dedup_key,
                metadata=metadata,
            )
            conn.commit()
    except Exception as exc:
        print(
            "[telegram:diagnostics-warning] "
            f"runtime_event_write_failed job_name={job_name} type={notification_type} status={status} error={exc}"
        )


def _skip_reason_code(reason: str | None) -> str:
    value = (reason or "").lower()
    if "alerts disabled" in value:
        return "alerts_disabled"
    if "category disabled" in value:
        return "category_disabled"
    if "frequency not allowed" in value:
        return "frequency_not_allowed"
    if "settings missing" in value:
        return "no_chat_id"
    if "dedup" in value:
        return "dedup"
    if "price missing" in value:
        return "data_missing"
    if "error" in value:
        return "error"
    return "no_trigger"


def _plain_preview(message: str) -> str:
    return (
        message.replace("<b>", "")
        .replace("</b>", "")
        .replace("<i>", "")
        .replace("</i>", "")
        .replace("<code>", "")
        .replace("</code>", "")
    )
