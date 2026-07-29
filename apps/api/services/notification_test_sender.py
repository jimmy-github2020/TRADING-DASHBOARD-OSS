from __future__ import annotations

from datetime import datetime
from html import escape as html_escape
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg
import httpx

from ai_tools import get_market_summary, get_sentiment_data, get_technical_signals


TAIPEI = ZoneInfo("Asia/Taipei")
DISCLAIMER = "<i>⚠️ 本訊息由 AI 生成，非投資建議</i>"
PENDING_CHAT_ID = "web_pending"
TEST_ITEM_TYPES = {
    "morning_brief": "manual_test_morning_brief",
    "closing_brief": "manual_test_closing_brief",
    "market_alert": "manual_test_market_alert",
    "price_alert": "manual_test_price_alert",
    "technical_alert": "manual_test_technical_alert",
}
TEST_THROTTLE_SECONDS = 20


async def send_test_summary(database_url: str, bot_token: str, *, dry_run: bool) -> dict[str, Any]:
    chat_id = await _fetch_chat_id(database_url)
    if not chat_id:
        await _record_runtime_event(
            database_url,
            notification_type="summary_test",
            status="no_chat_id",
            skip_reason="no_chat_id",
            topic="測試摘要",
            message_preview="Telegram 尚未綁定，測試摘要未送出。",
        )
        return {"status": "no_chat_id", "dry_run": dry_run, "message": "請先在 Telegram 對 Bot 輸入 /start 完成綁定。"}

    market, sentiment, technical = await _collect_summary_context()
    html = _build_test_summary(market, sentiment, technical)
    status, error = await _send_or_dry_run(bot_token, chat_id, html, dry_run=dry_run)
    await _record_delivery_and_event(
        database_url,
        chat_id=chat_id,
        notification_type="summary_test",
        status=status,
        error=error,
        html=html,
        topic="測試摘要",
        metadata={"manual_test": True, "dry_run": dry_run},
    )
    return {"status": status, "dry_run": dry_run, "error": error}


async def send_test_alert(database_url: str, bot_token: str, *, dry_run: bool) -> dict[str, Any]:
    chat_id = await _fetch_chat_id(database_url)
    if not chat_id:
        await _record_runtime_event(
            database_url,
            notification_type="alert_test",
            status="no_chat_id",
            skip_reason="no_chat_id",
            topic="測試警示",
            message_preview="Telegram 尚未綁定，測試警示未送出。",
        )
        return {"status": "no_chat_id", "dry_run": dry_run, "message": "請先在 Telegram 對 Bot 輸入 /start 完成綁定。"}

    html = _build_test_alert()
    status, error = await _send_or_dry_run(bot_token, chat_id, html, dry_run=dry_run)
    await _record_delivery_and_event(
        database_url,
        chat_id=chat_id,
        notification_type="alert_test",
        status=status,
        error=error,
        html=html,
        topic="測試警示",
        metadata={"manual_test": True, "dry_run": dry_run},
    )
    return {"status": status, "dry_run": dry_run, "error": error}


async def send_test_item(database_url: str, bot_token: str, *, item_type: str, dry_run: bool) -> dict[str, Any]:
    if item_type not in TEST_ITEM_TYPES:
        return {
            "ok": False,
            "status": "error",
            "item_type": item_type,
            "message": "Unsupported notification test item.",
            "last_tested_at": _now_iso(),
        }

    notification_type = TEST_ITEM_TYPES[item_type]
    topic = _test_item_topic(item_type)
    chat_id = await _fetch_chat_id(database_url)
    if not chat_id:
        await _record_runtime_event(
            database_url,
            notification_type=notification_type,
            status="no_chat_id",
            skip_reason="no_chat_id",
            topic=topic,
            message_preview="Telegram 尚未綁定，細項測試未送出。",
            metadata={"manual_test": True, "item_type": item_type},
        )
        return {
            "ok": False,
            "status": "no_chat_id",
            "item_type": item_type,
            "message": "請先在 Telegram 對 Bot 輸入 /start 完成綁定。",
            "last_tested_at": _now_iso(),
        }

    throttle = await _check_and_mark_test_throttle(database_url, item_type)
    if throttle["rate_limited"]:
        await _record_runtime_event(
            database_url,
            notification_type=notification_type,
            status="rate_limited",
            skip_reason="rate_limited",
            topic=topic,
            message_preview="測試過於頻繁，請稍後再試。",
            metadata={"manual_test": True, "item_type": item_type, "throttle_seconds": TEST_THROTTLE_SECONDS},
            chat_id=chat_id,
        )
        return {
            "ok": False,
            "status": "rate_limited",
            "item_type": item_type,
            "message": "測試過於頻繁，請稍後再試。",
            "last_tested_at": throttle["last_tested_at"],
        }

    html, data_status = await _build_test_item_message(item_type)
    status, error = await _send_or_dry_run(bot_token, chat_id, html, dry_run=dry_run)
    await _record_delivery_and_event(
        database_url,
        chat_id=chat_id,
        notification_type=notification_type,
        status=status,
        error=error,
        html=html,
        topic=topic,
        metadata={"manual_test": True, "item_type": item_type, "dry_run": dry_run, "data_source_status": data_status},
    )
    return {
        "ok": status in {"sent", "dry_run"},
        "status": status,
        "item_type": item_type,
        "message": _test_item_result_message(item_type, status),
        "last_tested_at": _now_iso(),
        "data_source_status": data_status,
        "error": error,
    }


async def _collect_summary_context() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    market = await get_market_summary("tw")
    sentiment = await get_sentiment_data("tw")
    technical = await get_technical_signals("tw")
    return market, sentiment, technical


async def _fetch_chat_id(database_url: str) -> str | None:
    conn = await asyncpg.connect(database_url)
    try:
        row = await conn.fetchrow(
            """
            SELECT chat_id
            FROM notification_settings
            WHERE chat_id <> $1
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            PENDING_CHAT_ID,
        )
        return str(row["chat_id"]) if row else None
    finally:
        await conn.close()


async def _send_or_dry_run(bot_token: str, chat_id: str, html: str, *, dry_run: bool) -> tuple[str, str | None]:
    if dry_run:
        return "dry_run", None
    if not bot_token:
        return "error", "TELEGRAM_BOT_TOKEN is missing"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": html,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        if response.is_success:
            return "sent", None
        return "error", f"HTTP {response.status_code}: {response.text[:300]}"
    except httpx.HTTPError as exc:
        return "error", f"{type(exc).__name__}: {str(exc)[:300]}"


async def _record_delivery_and_event(
    database_url: str,
    *,
    chat_id: str,
    notification_type: str,
    status: str,
    error: str | None,
    html: str,
    topic: str,
    metadata: dict[str, Any],
) -> None:
    preview = _plain_preview(html)
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_tables(conn)
        await conn.execute(
            """
            INSERT INTO notification_deliveries (
              chat_id, notification_type, message_preview, status, error_message
            )
            VALUES ($1, $2, $3, $4, $5)
            """,
            chat_id,
            notification_type,
            preview[:500],
            status,
            error,
        )
        await conn.execute(
            """
            INSERT INTO notification_runtime_events (
              job_name, notification_type, status, skip_reason, topic,
              message_preview, chat_id, metadata_json
            )
            VALUES (
              'manual_test', $1, $2, $3, $4, $5, $6, $7::jsonb
            )
            """,
            notification_type,
            "error" if status == "error" else status,
            "error" if status == "error" else None,
            topic,
            preview[:200],
            chat_id,
            _json_metadata(metadata),
        )
    finally:
        await conn.close()


async def _record_runtime_event(
    database_url: str,
    *,
    notification_type: str,
    status: str,
    skip_reason: str | None,
    topic: str,
    message_preview: str,
    metadata: dict[str, Any] | None = None,
    chat_id: str | None = None,
) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_tables(conn)
        await conn.execute(
            """
            INSERT INTO notification_runtime_events (
              job_name, notification_type, status, skip_reason, topic, message_preview, chat_id, metadata_json
            )
            VALUES ('manual_test', $1, $2, $3, $4, $5, $6, $7::jsonb)
            """,
            notification_type,
            status,
            skip_reason,
            topic,
            message_preview[:200],
            chat_id,
            _json_metadata(metadata or {"manual_test": True}),
        )
    finally:
        await conn.close()


async def _ensure_tables(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_deliveries (
          id SERIAL PRIMARY KEY,
          chat_id VARCHAR(50) NOT NULL,
          notification_type VARCHAR(50) NOT NULL,
          message_preview TEXT,
          status VARCHAR(20) NOT NULL,
          error_message TEXT,
          sent_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
          key VARCHAR(120) PRIMARY KEY,
          value JSONB NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
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


async def _check_and_mark_test_throttle(database_url: str, item_type: str) -> dict[str, Any]:
    key = f"notification_test_rate_limit:{item_type}"
    now = datetime.now(TAIPEI)
    conn = await asyncpg.connect(database_url)
    try:
        await _ensure_tables(conn)
        async with conn.transaction():
            row = await conn.fetchrow("SELECT updated_at FROM app_settings WHERE key = $1 FOR UPDATE", key)
            if row and (now - row["updated_at"].astimezone(TAIPEI)).total_seconds() < TEST_THROTTLE_SECONDS:
                return {"rate_limited": True, "last_tested_at": row["updated_at"].astimezone(TAIPEI).isoformat()}
            await conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ($1, $2::jsonb, now())
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = now()
                """,
                key,
                _json_metadata({"item_type": item_type, "manual_test": True}),
            )
            return {"rate_limited": False, "last_tested_at": now.isoformat()}
    finally:
        await conn.close()


async def _build_test_item_message(item_type: str) -> tuple[str, str]:
    if item_type in {"morning_brief", "closing_brief"}:
        market, sentiment, technical = await _collect_summary_context()
        return _build_item_summary(item_type, market, sentiment, technical), _context_status(market, sentiment, technical)
    if item_type == "market_alert":
        return _build_item_market_alert(), "static_test"
    if item_type == "price_alert":
        return _build_item_price_alert(), "static_test"
    if item_type == "technical_alert":
        return _build_item_technical_alert(), "static_test"
    return _build_test_alert(), "static_test"


def _build_item_summary(
    item_type: str,
    market: dict[str, Any],
    sentiment: dict[str, Any],
    technical: dict[str, Any],
) -> str:
    title = "測試早盤摘要" if item_type == "morning_brief" else "測試晚間摘要"
    schedule_note = "此訊息為手動測試，非正式早盤排程摘要。" if item_type == "morning_brief" else "此訊息為手動測試，非正式晚間排程摘要。"
    return "\n".join(
        [
            f"<b>🧪 {title}</b> {_now_label()}",
            "───────────────────",
            html_escape(schedule_note),
            "",
            f"🇹🇼 TWII：<code>{_fmt_number(market.get('last_close'))}</code> <code>{_fmt_pct(market.get('change_pct'))}</code>",
            f"VIX：<code>{_fmt_number(sentiment.get('vix'))}</code>｜Fear&amp;Greed：<code>{_fmt_number(sentiment.get('fear_greed_score'), 0)}</code>",
            f"RSI：<code>{_fmt_number(technical.get('rsi'))}</code>｜MACD：<code>{_fmt_number(technical.get('macd'))}</code>",
            "",
            DISCLAIMER,
        ]
    )


def _build_item_market_alert() -> str:
    return "\n".join(
        [
            f"<b>🚨 測試市場警示</b> {_now_label()}",
            "───────────────────",
            "這是一則手動測試，用於驗證市場風險警示模板與 Telegram 發送鏈路。",
            "",
            "🔍 <b>觀察重點</b>",
            "• 此訊息為 manual test，非市場條件命中",
            "• 正式市場警示仍需大盤、VIX 或 Fear &amp; Greed 達到條件才會推送",
            "",
            DISCLAIMER,
        ]
    )


def _build_item_price_alert() -> str:
    return "\n".join(
        [
            f"<b>🚨 測試價格警示</b> {_now_label()}",
            "───────────────────",
            "📌 <b>TEST</b> 現價 <code>100.00</code>",
            "設定閾值：測試門檻 <code>100.00</code>",
            "",
            "🔍 <b>觀察重點</b>",
            "• 此訊息為 price alert test，非真實觸價警示",
            "• 正式價格警示會依您設定的 symbol 與上下限觸發",
            "",
            DISCLAIMER,
        ]
    )


def _build_item_technical_alert() -> str:
    return "\n".join(
        [
            f"<b>📊 測試技術訊號警示</b> {_now_label()}",
            "───────────────────",
            "📌 <b>TEST</b> RSI <code>70.0</code>（測試訊號）",
            "",
            "🔍 <b>觀察重點</b>",
            "• 此訊息為 technical alert test，非真實技術訊號命中",
            "• 正式技術警示會依 RSI / MACD 等條件觸發",
            "",
            DISCLAIMER,
        ]
    )


def _context_status(*contexts: dict[str, Any]) -> str:
    errors = [context.get("error") for context in contexts if context.get("error")]
    return "partial_data" if errors else "ok"


def _test_item_topic(item_type: str) -> str:
    return {
        "morning_brief": "測試早盤摘要",
        "closing_brief": "測試晚間摘要",
        "market_alert": "測試市場警示",
        "price_alert": "測試價格警示",
        "technical_alert": "測試技術警示",
    }.get(item_type, "測試通知")


def _test_item_result_message(item_type: str, status: str) -> str:
    label = _test_item_topic(item_type)
    if status == "sent":
        return f"{label}已送出。"
    if status == "dry_run":
        return f"{label}已完成 Dry-run，未實際發送。"
    if status == "error":
        return f"{label}發送失敗。"
    return f"{label}狀態：{status}"
def _build_test_summary(market: dict[str, Any], sentiment: dict[str, Any], technical: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"<b>🧪 測試摘要</b> {_now_label()}",
            "───────────────────",
            "此訊息為手動測試，非正式排程摘要。",
            "",
            f"🇹🇼 TWII：<code>{_fmt_number(market.get('last_close'))}</code> <code>{_fmt_pct(market.get('change_pct'))}</code>",
            f"VIX：<code>{_fmt_number(sentiment.get('vix'))}</code>｜Fear&amp;Greed：<code>{_fmt_number(sentiment.get('fear_greed_score'), 0)}</code>",
            f"RSI：<code>{_fmt_number(technical.get('rsi'))}</code>｜MACD：<code>{_fmt_number(technical.get('macd'))}</code>",
            "",
            DISCLAIMER,
        ]
    )


def _build_test_alert() -> str:
    return "\n".join(
        [
            f"<b>🚨 測試警示</b> {_now_label()}",
            "───────────────────",
            "這是一則手動發送的測試警示，用於驗證 Telegram 發送鏈路與警示通知模板。",
            "",
            "🔍 <b>觀察重點</b>",
            "• 此訊息為手動測試，非條件命中警示",
            "• 正式警示仍需符合價格、技術或市場條件才會推送",
            "",
            DISCLAIMER,
        ]
    )


def _now_label() -> str:
    return datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")


def _now_iso() -> str:
    return datetime.now(TAIPEI).isoformat()


def _fmt_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}%"


def _plain_preview(html: str) -> str:
    return (
        html.replace("<b>", "")
        .replace("</b>", "")
        .replace("<i>", "")
        .replace("</i>", "")
        .replace("<code>", "")
        .replace("</code>", "")
        .replace("&amp;", "&")
    )


def _json_metadata(metadata: dict[str, Any]) -> str:
    import json

    return json.dumps(metadata, ensure_ascii=False)
