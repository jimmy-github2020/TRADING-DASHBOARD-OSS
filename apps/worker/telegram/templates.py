from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
DISCLAIMER = "<i>⚠️ 本訊息由 AI 生成，非投資建議</i>"
DIVIDER = "───────────────────"


def build_market_summary(market: dict[str, Any]) -> str:
    tw = market.get("tw") or {}
    us = market.get("us") or {}
    return "\n".join(
        [
            f"<b>📈 市場摘要</b> {_today_label()}",
            DIVIDER,
            f"🇹🇼 台股：<code>{_fmt_number(tw.get('price'))}</code> <code>{_fmt_pct(tw.get('change_pct'))}</code>",
            f"🇺🇸 美股：<code>{_fmt_number(us.get('price'))}</code> <code>{_fmt_pct(us.get('change_pct'))}</code>",
            "",
            DISCLAIMER,
        ]
    )


def build_watchlist_snapshot(watchlist: list[dict[str, Any]]) -> str:
    items = list(watchlist[:5])
    lines = [f"<b>📋 Watchlist 快照</b> {_today_label()}", DIVIDER]
    if not items:
        lines.append("目前沒有可顯示的觀察標的。")
    for item in items:
        name = escape(str(item.get("name") or item.get("name_zh") or item.get("symbol") or "-"))
        symbol = escape(str(item.get("symbol") or "-"))
        price = _fmt_number(item.get("price"))
        change_pct = _fmt_pct(item.get("change_pct"))
        lines.append(f"{name} <code>{symbol}</code>：{price}（{change_pct}）")
    lines.extend(["", DISCLAIMER])
    return "\n".join(lines)


def build_ai_summary(summary: dict[str, Any]) -> str:
    provider = escape(str(summary.get("provider") or "AI"))
    direction = escape(str(summary.get("direction") or "neutral"))
    text = escape(str(summary.get("summary") or "目前沒有摘要內容。"))
    return "\n".join(
        [
            f"<b>🤖 AI 市場摘要</b> {_today_label()}",
            DIVIDER,
            f"來源：<code>{provider}</code>",
            f"方向：<code>{direction}</code>",
            "",
            text,
            "",
            DISCLAIMER,
        ]
    )


def build_fallback_message(title: str = "📊 幾米投資晨報") -> str:
    return "\n".join(
        [
            f"<b>{escape(title)}</b> {_today_label()}",
            DIVIDER,
            "資料暫時無法取得，請至儀表板查看最新狀況。",
            DISCLAIMER,
        ]
    )


def build_summary_disabled() -> str:
    return "目前 AI 摘要尚未啟用，請至儀表板查看即時資料。"


def build_morning_brief(market: dict[str, Any], sentiment: dict[str, Any], news: list[dict[str, Any]]) -> str:
    tw = market.get("tw") or {}
    us = market.get("us") or {}
    vix = _safe_float(sentiment.get("vix"))
    fear_greed = _safe_float(sentiment.get("fear_greed_score"))
    key_points = _limit_items(
        [
            _market_snapshot_line("台股", tw),
            _market_snapshot_line("美股 SPY", us),
            f"市場情緒：Fear&amp;Greed <code>{_fmt_number(fear_greed, 0)}</code>｜VIX <code>{_fmt_number(vix)}</code>",
        ],
        3,
    )
    risks = _sentiment_risk_items(sentiment) + _market_risk_items("台股", tw, 2.0) + _market_risk_items("美股 SPY", us, 1.5)
    rule_hits = _rule_hit_items(sentiment, tw)
    observations = _limit_items(
        [
            "先確認 VIX、Fear &amp; Greed 與台股開盤方向是否同步。",
            "若新聞焦點集中在同一產業，優先觀察相關權值股量能。",
        ],
        2,
    )
    extras = _headline_lines(news, 2)
    return _build_brief_message(
        "📊 幾米投資晨報",
        key_points=key_points,
        risks=risks,
        rule_hits=rule_hits,
        observations=observations,
        extras=extras,
    )


def build_midday_flash(sentiment: dict[str, Any]) -> str:
    label = escape(str(sentiment.get("fear_greed_label") or "-"))
    vix = _safe_float(sentiment.get("vix"))
    fear_greed = _safe_float(sentiment.get("fear_greed_score"))
    key_points = _limit_items(
        [
            f"Fear&amp;Greed <code>{_fmt_number(fear_greed, 0)}</code> {label}",
            f"VIX <code>{_fmt_number(vix)}</code>｜Put/Call <code>{_fmt_number(sentiment.get('put_call_ratio'))}</code>",
        ],
        2,
    )
    risks = _sentiment_risk_items(sentiment)
    rule_hits = _rule_hit_items(sentiment, {})
    observations = ["午後優先確認波動是否擴大，以及台股尾盤量能是否放大。"]
    return _build_brief_message(
        "⚡ 幾米午間快訊",
        key_points=key_points,
        risks=risks,
        rule_hits=rule_hits,
        observations=observations,
    )


def build_closing_report(
    market: dict[str, Any],
    institutions: dict[str, Any],
    watchlist: list[dict[str, Any]],
) -> str:
    tw = market.get("tw") or {}
    flow = institutions.get("data") or {}
    foreign = _net_to_yi((flow.get("foreign") or {}).get("net"))
    trust = _net_to_yi((flow.get("trust") or {}).get("net"))
    dealer = _net_to_yi((flow.get("dealer") or {}).get("net"))
    items = _pad_items(watchlist[:3], 3, {"symbol": "-", "name": "資料暫缺", "score": "-"})
    key_points = _limit_items(
        [
            _market_snapshot_line("台股收盤", tw),
            f"三大法人：外資 <code>{foreign:+.1f}億</code>｜投信 <code>{trust:+.1f}億</code>｜自營 <code>{dealer:+.1f}億</code>",
            f"Watchlist 前段：{_ranking_line(1, items[0])}",
        ],
        3,
    )
    risks = _market_risk_items("台股", tw, 2.0)
    if abs(foreign) >= 100:
        risks.append(f"外資買賣超達 <code>{foreign:+.1f}億</code>，留意隔日權值股延續性。")
    rule_hits = _limit_items(
        [
            f"技術排行第 1 名：{_ranking_line(1, items[0])}",
            f"技術排行第 2 名：{_ranking_line(2, items[1])}",
        ],
        2,
    )
    observations = _limit_items(
        [
            "明日優先觀察法人方向是否延續，並比對台指期與匯率變化。",
            "高分標的若量能未同步放大，先視為追蹤名單而非訊號確認。",
        ],
        2,
    )
    return _build_brief_message(
        "📌 幾米收盤報告",
        key_points=key_points,
        risks=risks,
        rule_hits=rule_hits,
        observations=observations,
    )


def build_summary_metadata(message: str) -> dict[str, Any]:
    sections: dict[str, int] = {}
    current_section: str | None = None
    for line in message.splitlines():
        if line.startswith("<b>【") and "】</b>" in line:
            current_section = line.split("【", 1)[1].split("】", 1)[0]
            sections.setdefault(current_section, 0)
            continue
        if current_section and line.startswith("- "):
            sections[current_section] = sections.get(current_section, 0) + 1
    return {
        "summary_section_count": len(sections),
        "key_points_count": sections.get("今日重點", 0),
        "risk_items_count": sections.get("風險 / 異常", 0),
        "included_rule_hits": sections.get("關注規則", 0),
    }


def build_twii_move_alert(market: dict[str, Any]) -> str:
    change_pct = _safe_float(market.get("change_pct"))
    direction = "上漲" if change_pct is not None and change_pct >= 0 else "下跌"
    return "\n".join(
        [
            f"<b>🚨 台股大盤異常波動</b> {_today_label()}",
            DIVIDER,
            f"台灣加權指數目前 <b>{direction}</b>：<code>{_fmt_number(market.get('price'))}</code> <code>{_fmt_pct(change_pct)}</code>",
            "",
            "觀察重點：留意權值股、期貨與匯率是否同步放大波動。",
            DISCLAIMER,
        ]
    )


def build_vix_alert(sentiment: dict[str, Any]) -> str:
    vix_value = _safe_float(sentiment.get("vix"))
    state = "高恐慌" if vix_value is not None and vix_value > 25 else "過度樂觀"
    return "\n".join(
        [
            f"<b>🚨 VIX 波動警示</b> {_today_label()}",
            DIVIDER,
            f"VIX 目前為 <code>{_fmt_number(vix_value)}</code>，狀態：<b>{state}</b>",
            "",
            "觀察重點：留意市場避險需求、科技股波動與隔夜美股情緒變化。",
            DISCLAIMER,
        ]
    )


def build_fear_greed_alert(sentiment: dict[str, Any]) -> str:
    score = _safe_float(sentiment.get("fear_greed_score"))
    label = escape(str(sentiment.get("fear_greed_label") or "-"))
    state = "極度恐慌" if score is not None and score < 20 else "極度貪婪"
    return "\n".join(
        [
            f"<b>🚨 Fear&amp;Greed 極值警示</b> {_today_label()}",
            DIVIDER,
            f"Fear&amp;Greed 目前為 <code>{_fmt_number(score, 0)}</code> {label}，狀態：<b>{state}</b>",
            "",
            "觀察重點：留意情緒極端後的反向波動與量能確認。",
            DISCLAIMER,
        ]
    )


def build_market_rule_alert(result: dict[str, Any]) -> str:
    name = escape(str(result.get("name") or result.get("rule_key") or "市場規則"))
    rule_key = escape(str(result.get("rule_key") or "-"))
    reason = escape(str(result.get("reason") or "規則已命中"))
    severity = escape(str(result.get("severity") or "warning"))
    current_value = _fmt_number(result.get("current_value"))
    return "\n".join(
        [
            f"<b>🚨 市場規則警示</b> {_today_label()}",
            DIVIDER,
            f"<b>{name}</b> <code>{rule_key}</code>",
            f"目前數值：<code>{current_value}</code>｜等級：<code>{severity}</code>",
            "",
            f"命中原因：{reason}",
            "",
            "觀察重點：請結合通知設定、大盤結構與儀表板即時資料再判讀。",
            DISCLAIMER,
        ]
    )


def build_price_alert(symbol: str, price: float, threshold: float, alert_type: str) -> str:
    alert_type_label = "高於" if alert_type == "above" else "低於"
    return "\n".join(
        [
            f"<b>🚨 個股觸價警示</b> {_today_label()}",
            DIVIDER,
            f"📌 <b>{escape(symbol)}</b> 現價 <code>{_fmt_number(price)}</code>",
            f"設定閾值：{alert_type_label} <code>{_fmt_number(threshold)}</code>",
            "",
            "🔍 <b>觀察重點</b>",
            "• 價格已突破您設定的警示點位",
            "• 請至儀表板查看完整技術分析",
            "",
            DISCLAIMER,
        ]
    )


def build_technical_alert(symbol: str, signal_type: str, value: Any) -> str:
    labels = {
        "rsi_overbought": ("RSI", f"<code>{_fmt_number(value)}</code>（超買區間）", "RSI 進入超買區，留意獲利了結賣壓"),
        "rsi_oversold": ("RSI", f"<code>{_fmt_number(value)}</code>（超賣區間）", "RSI 進入超賣區，留意反彈與量能確認"),
        "macd_golden": ("MACD", "金叉", "MACD 出現金叉，留意趨勢是否延續"),
        "macd_death": ("MACD", "死叉", "MACD 出現死叉，留意趨勢轉弱風險"),
    }
    indicator, value_label, first_point = labels.get(signal_type, ("訊號", escape(str(value)), "留意訊號後續延續性"))
    return "\n".join(
        [
            f"<b>📊 技術訊號警示</b> {_today_label()}",
            DIVIDER,
            f"📌 <b>{escape(symbol)}</b>　{indicator} {value_label}",
            "",
            "🔍 <b>觀察重點</b>",
            f"• {first_point}",
            "• 搭配成交量與均線確認方向",
            "",
            DISCLAIMER,
        ]
    )


def _build_brief_message(
    title: str,
    key_points: list[str],
    risks: list[str] | None = None,
    rule_hits: list[str] | None = None,
    observations: list[str] | None = None,
    extras: list[str] | None = None,
) -> str:
    lines = [f"<b>{escape(title)}</b> {_today_label()}", DIVIDER]
    lines.extend(_section_lines("今日重點", _limit_items(key_points, 3)))
    lines.extend(_section_lines("風險 / 異常", _limit_items(risks or ["目前未見明顯風險升溫訊號。"], 3)))
    lines.extend(_section_lines("關注規則", _limit_items(rule_hits or ["市場宏觀規則未見明顯命中；維持一般觀察。"], 3)))
    lines.extend(_section_lines("建議觀察", _limit_items(observations or ["以儀表板即時資料確認方向，不因單一訊號做判斷。"], 3)))
    if extras:
        lines.extend(_section_lines("補充資訊", _limit_items(extras, 2)))
    lines.extend(["", DISCLAIMER])
    return "\n".join(lines)


def _section_lines(title: str, items: list[str]) -> list[str]:
    compact_items = [item for item in items if item]
    if not compact_items:
        return []
    lines = ["", f"<b>【{escape(title)}】</b>"]
    lines.extend(f"- {item}" for item in compact_items)
    return lines


def _market_snapshot_line(label: str, market: dict[str, Any]) -> str:
    return f"{escape(label)}：<code>{_fmt_number(market.get('price'))}</code> <code>{_fmt_pct(market.get('change_pct'))}</code>"


def _market_risk_items(label: str, market: dict[str, Any], threshold_pct: float) -> list[str]:
    change_pct = _safe_float(market.get("change_pct"))
    if change_pct is None or abs(change_pct) < threshold_pct:
        return []
    direction = "上漲" if change_pct > 0 else "下跌"
    return [f"{escape(label)}單日{direction} <code>{_fmt_pct(change_pct)}</code>，波動超過 {threshold_pct:.1f}% 門檻。"]


def _sentiment_risk_items(sentiment: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    vix = _safe_float(sentiment.get("vix"))
    fear_greed = _safe_float(sentiment.get("fear_greed_score"))
    if vix is not None and vix >= 25:
        risks.append(f"VIX <code>{_fmt_number(vix)}</code>，避險情緒升溫。")
    if fear_greed is not None and fear_greed <= 20:
        risks.append(f"Fear&amp;Greed <code>{_fmt_number(fear_greed, 0)}</code>，市場接近極度恐懼。")
    if fear_greed is not None and fear_greed >= 80:
        risks.append(f"Fear&amp;Greed <code>{_fmt_number(fear_greed, 0)}</code>，市場接近極度貪婪。")
    return risks


def _rule_hit_items(sentiment: dict[str, Any], tw_market: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    vix = _safe_float(sentiment.get("vix"))
    fear_greed = _safe_float(sentiment.get("fear_greed_score"))
    tw_change = _safe_float(tw_market.get("change_pct"))
    if tw_change is not None and abs(tw_change) >= 2:
        hits.append(f"TWII 漲跌幅警示：<code>{_fmt_pct(tw_change)}</code> 超出 ±2%。")
    if vix is not None and vix >= 25:
        hits.append(f"VIX 高波動警示：<code>{_fmt_number(vix)}</code> 高於 25。")
    if fear_greed is not None and (fear_greed <= 20 or fear_greed >= 80):
        hits.append(f"Fear&amp;Greed 極端警示：<code>{_fmt_number(fear_greed, 0)}</code> 落在極端區。")
    return hits


def _headline_lines(news: list[dict[str, Any]], limit: int) -> list[str]:
    return [_headline_text(item) for item in news[:limit] if item]


def _limit_items(items: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _today_label() -> str:
    return datetime.now(TAIPEI).strftime("%Y-%m-%d")


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


def _headline_text(item: dict[str, Any] | str | None) -> str:
    if isinstance(item, dict):
        return escape(str(item.get("title") or item.get("headline") or "今日新聞資料暫缺"))
    if item:
        return escape(str(item))
    return "今日新聞資料暫缺"


def _ranking_line(rank: int, item: dict[str, Any]) -> str:
    name = escape(str(item.get("name") or item.get("symbol") or "資料暫缺"))
    symbol = escape(str(item.get("symbol") or "-"))
    score = escape(str(item.get("score") or "-"))
    return f"{rank}. {name} <code>{symbol}</code>：{score}"


def _net_to_yi(value: Any) -> float:
    number = _safe_float(value)
    return (number or 0) / 100_000_000


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pad_items(items: list[Any], length: int, fallback: Any | None = None) -> list[Any]:
    result = list(items)
    while len(result) < length:
        result.append(fallback)
    return result
