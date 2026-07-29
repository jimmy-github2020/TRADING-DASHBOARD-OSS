from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
import httpx

from ai_tools import get_market_summary, get_news_headlines, get_sentiment_data, get_technical_signals
from market_quote import fetch_yahoo_fallback_quotes
from services.ai_provider import AiBriefResult, generate_brief


DISCLAIMER = "<i>⚠️ 本訊息由 AI 生成，非投資建議</i>"


@dataclass(frozen=True)
class TelegramCommandResult:
    command: str
    sent: bool
    error: str | None = None


async def handle_command(
    *,
    database_url: str,
    bot_token: str,
    chat_id: int | str,
    text: str,
) -> TelegramCommandResult:
    command, args = _parse_command(text)
    chat_id_text = str(chat_id)

    if command == "/start":
        await _ensure_notification_settings(database_url, chat_id_text)
        message = _start_message()
    elif command == "/alert" and args == "off":
        await _set_alerts_enabled(database_url, chat_id_text, False)
        message = "<b>🔕 警示已暫停</b>\n所有條件觸發警示已關閉。\n輸入 /alert on 可恢復。"
    elif command == "/alert" and args == "on":
        await _set_alerts_enabled(database_url, chat_id_text, True)
        message = "<b>🔔 警示已恢復</b>\n條件觸發警示已重新啟用。"
    elif command == "/alert":
        enabled = await _get_alerts_enabled(database_url, chat_id_text)
        message = _alert_status_message(enabled)
    elif command == "/market":
        message = await _market_message()
    elif command == "/vix":
        message = await _vix_message()
    elif command == "/watchlist":
        message = await _watchlist_message(database_url)
    elif command == "/summary":
        message = await _summary_message()
    else:
        message = "<b>❓ 未知指令</b>\n輸入 /start 查看可用指令列表。"

    sent, error = await _send_reply(bot_token, chat_id_text, message)
    return TelegramCommandResult(command=command or "unknown", sent=sent, error=error)


def _parse_command(text: str) -> tuple[str, str]:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return "", ""
    command = parts[0].split("@", 1)[0].lower()
    args = parts[1].strip().lower() if len(parts) > 1 else ""
    return command, args


async def _ensure_notification_settings(database_url: str, chat_id: str) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(
            """
            INSERT INTO notification_settings (chat_id)
            VALUES ($1)
            ON CONFLICT (chat_id) DO UPDATE
            SET updated_at = now()
            """,
            chat_id,
        )
    finally:
        await conn.close()


async def _set_alerts_enabled(database_url: str, chat_id: str, enabled: bool) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(
            """
            INSERT INTO notification_settings (chat_id, alerts_enabled)
            VALUES ($1, $2)
            ON CONFLICT (chat_id) DO UPDATE
            SET alerts_enabled = EXCLUDED.alerts_enabled,
                updated_at = now()
            """,
            chat_id,
            enabled,
        )
    finally:
        await conn.close()


async def _get_alerts_enabled(database_url: str, chat_id: str) -> bool:
    conn = await asyncpg.connect(database_url)
    try:
        row = await conn.fetchrow(
            """
            SELECT alerts_enabled
            FROM notification_settings
            WHERE chat_id = $1
            """,
            chat_id,
        )
        return True if row is None else bool(row["alerts_enabled"])
    finally:
        await conn.close()


async def _market_message() -> str:
    tw, us = await _safe_gather_market()
    lines = [
        "<b>📈 大盤即時行情</b>",
        "───────────────────",
        _market_line("🇹🇼 台灣加權", tw),
        _market_line("🇺🇸 S&amp;P 500", us),
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


async def _safe_gather_market() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        tw = await get_market_summary("tw")
    except Exception as exc:
        tw = {"error": str(exc)}
    try:
        us = await get_market_summary("us")
    except Exception as exc:
        us = {"error": str(exc)}
    return tw, us


async def _vix_message() -> str:
    try:
        sentiment = await get_sentiment_data("tw")
    except Exception as exc:
        sentiment = {"error": str(exc)}

    vix = _fmt_number(sentiment.get("vix"), 2)
    fear_greed = sentiment.get("fear_greed_score")
    fg_label = sentiment.get("fear_greed_label") or "N/A"
    pcr = _fmt_number(sentiment.get("put_call_ratio"), 2)
    lines = [
        "<b>😨 市場情緒</b>",
        "───────────────────",
        f"VIX：<code>{vix}</code>",
        f"Fear &amp; Greed：<code>{_fmt_optional(fear_greed)}</code>（{_escape(fg_label)}）",
        f"Put-Call Ratio：<code>{pcr}</code>",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


async def _watchlist_message(database_url: str) -> str:
    holdings = await _fetch_watchlist_symbols(database_url, limit=8)
    if not holdings:
        return "<b>📋 Watchlist</b>\n目前尚無觀察清單資料。"

    symbols = [item["symbol"] for item in holdings]
    quotes = await fetch_yahoo_fallback_quotes(symbols)
    quote_by_symbol = {quote["symbol"]: quote for quote in quotes}
    lines = [
        "<b>📋 Watchlist 快照</b>",
        "───────────────────",
    ]
    for item in holdings:
        symbol = item["symbol"]
        quote = quote_by_symbol.get(symbol, {})
        name = item.get("name_zh") or item.get("name_en") or symbol
        price = _fmt_number(quote.get("price"), 2)
        change = _fmt_signed_pct(quote.get("change_pct"))
        lines.append(f"{_escape(name)} <code>{_escape(symbol)}</code>：{price}（{change}）")
    lines.extend(["", DISCLAIMER])
    return "\n".join(lines)


async def _summary_message() -> str:
    context = await _build_ai_context()
    providers = ["gemini", "openai", "perplexity"]
    results: list[AiBriefResult] = []
    for provider in providers:
        result = await generate_brief(provider, context)
        results.append(result)
        if result.status == "ok" and result.summary:
            return _brief_message(result)

    not_configured = [result.provider for result in results if result.status == "not_configured"]
    if len(not_configured) == len(results):
        return "目前 AI 摘要尚未啟用，請至儀表版查看即時資料。"

    errors = "、".join(f"{result.provider}:{result.status}" for result in results)
    return f"<b>🤖 AI 摘要暫時無法產生</b>\n狀態：{_escape(errors)}"


async def _build_ai_context() -> dict[str, Any]:
    market = await get_market_summary("tw")
    technical = await get_technical_signals("tw")
    sentiment = await get_sentiment_data("tw")
    news = await get_news_headlines("tw", limit=5)
    return {
        "scope": "tw",
        "generated_at": datetime.now(UTC).isoformat(),
        "market_summary": market,
        "technical_signals": technical,
        "sentiment_data": sentiment,
        "news_headlines": news,
        "daily_notes": {"notes": [], "error": None},
    }


async def _fetch_watchlist_symbols(database_url: str, limit: int) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(database_url)
    try:
        rows = await conn.fetch(
            """
            SELECT symbol, name_zh, name_en
            FROM portfolio_holdings
            WHERE owned = TRUE
            ORDER BY
              CASE category WHEN 'ETF' THEN 1 WHEN '股票' THEN 2 ELSE 3 END,
              symbol
            LIMIT $1
            """,
            limit,
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def _send_reply(bot_token: str, chat_id: str, text: str) -> tuple[bool, str | None]:
    if not bot_token:
        return False, "TELEGRAM_BOT_TOKEN is not configured"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return False, f"Telegram API returned HTTP {exc.response.status_code}"
    except Exception as exc:
        return False, f"Telegram reply failed: {type(exc).__name__}"
    return True, None


def _start_message() -> str:
    return "\n".join(
        [
            "<b>👋 幾米投資 Bot 已啟動！</b>",
            "───────────────────",
            "您的 Chat ID 已綁定。",
            "",
            "📋 <b>可用指令</b>",
            "/market    查看大盤即時行情",
            "/vix       查看 VIX + Fear &amp; Greed",
            "/watchlist 查看觀察清單",
            "/summary   取得 AI 市場摘要",
            "/alert off 暫停所有警示",
            "/alert on  恢復所有警示",
            "",
            DISCLAIMER,
        ]
    )


def _alert_status_message(enabled: bool) -> str:
    state = "開啟" if enabled else "暫停"
    command = "/alert off" if enabled else "/alert on"
    return f"<b>🔔 警示目前：{state}</b>\n輸入 {command} 可切換狀態。"


def _brief_message(result: AiBriefResult) -> str:
    direction_map = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}
    lines = [
        f"<b>🤖 AI 市場摘要</b>（{_escape(result.provider)}）",
        "───────────────────",
        f"方向：<b>{direction_map.get(result.direction or 'neutral', '中性')}</b>",
    ]
    if result.key_points:
        lines.append("")
        lines.append("📌 <b>關鍵重點</b>")
        lines.extend(f"{index}. {_escape(point)}" for index, point in enumerate(result.key_points[:3], start=1))
    lines.append("")
    lines.append(_escape(result.summary or "目前沒有摘要內容。"))
    return "\n".join(lines)


def _market_line(label: str, payload: dict[str, Any]) -> str:
    if payload.get("error"):
        return f"{label}：資料暫缺"
    price = _fmt_number(payload.get("last_close"), 2)
    change = _fmt_signed_pct(payload.get("change_pct"))
    return f"{label}：<code>{price}</code>（{change}）"


def _fmt_number(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_signed_pct(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    prefix = "+" if numeric > 0 else ""
    return f"{prefix}{numeric:.2f}%"


def _fmt_optional(value: Any) -> str:
    return "N/A" if value is None else _escape(value)


def _escape(value: object) -> str:
    return html.escape(str(value), quote=False)
