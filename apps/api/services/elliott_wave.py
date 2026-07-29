from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from services.ai_provider import is_configured_api_key

CACHE_TTL_SECONDS = 600
GEMINI_MODEL = "gemini-2.5-flash"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

WAVE_BASES: list[dict[str, Any]] = [
    {"id": "C1", "date": "2022-10-25", "price": 12666, "label": "熊市總底"},
    {"id": "C2", "date": "2023-10-31", "price": 16001, "label": "AI二段起漲"},
    {"id": "C3", "date": "2024-01-17", "price": 17162, "label": "突破前高"},
]

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _cached(key: str) -> dict[str, Any] | None:
    cached = _CACHE.get(key)
    if cached and cached[0] > monotonic():
        return cached[1]
    return None


def _store_cache(key: str, value: dict[str, Any]) -> dict[str, Any]:
    _CACHE[key] = (monotonic() + CACHE_TTL_SECONDS, value)
    return value


def _to_float(value: object, default: float = 0.0) -> float:
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        delta = closes[index] - closes[index - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for index in range(period + 1, len(closes)):
        delta = closes[index] - closes[index - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0)) / period
        avg_loss = (avg_loss * (period - 1) + abs(min(delta, 0))) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _fetch_market_context(symbol: str) -> dict[str, Any]:
    history = yf.Ticker(symbol).history(period="5y", interval="1d", auto_adjust=False, timeout=12)
    if history.empty or "Close" not in history.columns:
        raise ValueError(f"No close price data returned for {symbol}")

    usable = history.dropna(subset=["Close"]).copy()
    if len(usable) < 30:
        raise ValueError(f"Not enough close price data returned for {symbol}")

    closes = [_to_float(value) for value in usable["Close"].tolist()]
    latest = usable.iloc[-1]
    previous = usable.iloc[-2]
    current_price = _to_float(latest.get("Close"))
    previous_close = _to_float(previous.get("Close"))
    change = current_price - previous_close
    change_pct = (change / previous_close * 100) if previous_close else 0.0

    last_20 = usable.tail(20)
    high_20d = round(_to_float(last_20["High"].max(), current_price))
    low_20d = round(_to_float(last_20["Low"].min(), current_price))
    latest_volume = _to_float(latest.get("Volume"))
    avg_volume = _to_float(last_20["Volume"].mean(), 0)
    volume_ratio = round(latest_volume / avg_volume, 2) if avg_volume else 0

    price_rows = []
    for index, row in usable.tail(130).iterrows():
        timestamp = pd.Timestamp(index).date().isoformat()
        price_rows.append(f"{timestamp} {float(row['Close']):.2f}")

    return {
        "symbol": symbol,
        "current_price": round(current_price, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "high_20d": int(high_20d),
        "low_20d": int(low_20d),
        "rsi": _rsi(closes),
        "volume_ratio": volume_ratio,
        "price_data": "\n".join(price_rows),
    }


def _build_prompt(context: dict[str, Any]) -> str:
    return f"""
你是一位台股技術分析師，專精艾略特波浪理論。
請根據以下市場資料，判斷台灣加權指數目前所處的波浪位置。

【本輪主升行情三種起算說法】
- C1：2022-10-25，起漲價 12666（熊市總底，FED升息末端最終低點）
- C2：2023-10-31，起漲價 16001（AI算力爆發，NVDA財報觸媒第二段起漲）
- C3：2024-01-17，起漲價 17162（突破2022歷史前高後回測確立主升段）

【當前市場數據】
- 台灣加權指數現價：{context["current_price"]}
- 今日漲跌：{context["change"]}（{context["change_pct"]}%）
- 近20日最高：{context["high_20d"]}
- 近20日最低：{context["low_20d"]}
- RSI(14)：{context["rsi"]}
- 成交量相對20日均量：{context["volume_ratio"]}倍

【最近收盤價序列】
{context["price_data"]}

【輸出規則】
請嚴格只回傳以下 JSON 格式，不加任何額外文字、不加 markdown、不加說明：
{{
  "base_id": "C1" 或 "C2" 或 "C3",
  "base_date": "YYYY-MM-DD",
  "base_price": 數字,
  "base_reason": "一句話說明為何此起算點最吻合，不超過25字",
  "wave_number": "1" 或 "2" 或 "3" 或 "4" 或 "5" 或 "A" 或 "B" 或 "C",
  "wave_phase": "上升" 或 "修正" 或 "盤整",
  "wave_label": "例如：第3浪上升段、第4浪修正、第5浪初段",
  "support": 數字（整數，近期最關鍵支撐價位）,
  "resistance": 數字（整數，近期最關鍵壓力價位）,
  "trend": "bullish" 或 "bearish" 或 "neutral",
  "note": "操作方向提示，不超過25字，禁止具體買賣建議"
}}
""".strip()


def _parse_json_response(text: str) -> dict[str, Any]:
    compact = text.strip()
    try:
        return json.loads(compact)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", compact, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _call_gemini(context: dict[str, Any]) -> dict[str, Any]:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not is_configured_api_key(api_key, {"", "YOUR_GEMINI_API_KEY"}):
        raise RuntimeError("GEMINI_API_KEY not configured")

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", GEMINI_MODEL).strip() or GEMINI_MODEL
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            "temperature": 0.15,
            "max_output_tokens": 512,
            "response_mime_type": "application/json",
        },
    )
    response = model.generate_content(_build_prompt(context), request_options={"timeout": 50})
    return _parse_json_response((getattr(response, "text", "") or "").strip())


def _base_by_id(base_id: str) -> dict[str, Any]:
    return next((base for base in WAVE_BASES if base["id"] == base_id), WAVE_BASES[1])


def _fallback_analysis(context: dict[str, Any], source: str = "fallback") -> dict[str, Any]:
    price = context["current_price"]
    rsi = context["rsi"] or 50
    high_20d = int(context["high_20d"])
    low_20d = int(context["low_20d"])
    if price >= high_20d * 0.98 and rsi >= 55:
        wave_number = "5"
        wave_phase = "上升"
        wave_label = "第5浪初段"
        trend = "bullish"
        note = "站穩支撐則趨勢延續"
    elif price <= low_20d * 1.03:
        wave_number = "4"
        wave_phase = "修正"
        wave_label = "第4浪修正"
        trend = "bearish"
        note = "跌破支撐需提高警覺"
    else:
        wave_number = "B"
        wave_phase = "盤整"
        wave_label = "B浪反彈"
        trend = "neutral"
        note = "區間整理等待突破"
    return {
        "base_id": "C2",
        "base_date": "2023-10-31",
        "base_price": 16001,
        "base_reason": "AI鏈第二段起漲最吻合",
        "wave_number": wave_number,
        "wave_phase": wave_phase,
        "wave_label": wave_label,
        "support": low_20d,
        "resistance": high_20d,
        "trend": trend,
        "note": note,
        "source": source,
    }


def _normalize_analysis(raw: dict[str, Any], context: dict[str, Any], source: str) -> dict[str, Any]:
    base = _base_by_id(str(raw.get("base_id") or "C2"))
    support = raw.get("support") if raw.get("support") is not None else context["low_20d"]
    resistance = raw.get("resistance") if raw.get("resistance") is not None else context["high_20d"]
    trend = str(raw.get("trend") or "neutral")
    if trend not in {"bullish", "bearish", "neutral"}:
        trend = "neutral"
    wave_number = str(raw.get("wave_number") or "B")
    wave_phase = str(raw.get("wave_phase") or "盤整")
    wave_label = str(raw.get("wave_label") or f"第{wave_number}浪{wave_phase}")
    return {
        "base_id": base["id"],
        "base_date": str(raw.get("base_date") or base["date"]),
        "base_price": int(raw.get("base_price") or base["price"]),
        "base_reason": str(raw.get("base_reason") or base["label"])[:40],
        "wave_number": wave_number,
        "wave_phase": wave_phase,
        "wave_label": wave_label[:24],
        "support": int(round(float(support))),
        "resistance": int(round(float(resistance))),
        "trend": trend,
        "note": str(raw.get("note") or "僅供技術觀察參考")[:40],
        "source": source,
    }


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    generated_at = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")
    return {
        **payload,
        "all_bases": WAVE_BASES,
        "generated_at": generated_at,
    }


def _analyze_sync(symbol: str) -> dict[str, Any]:
    context = _fetch_market_context(symbol)
    try:
        raw = _call_gemini(context)
        payload = _normalize_analysis(raw, context, "gemini")
    except Exception:
        payload = _fallback_analysis(context, "fallback")
    return _envelope(payload)


async def analyze_elliott_wave(symbol: str = "^TWII") -> dict[str, Any]:
    normalized_symbol = symbol.strip() or "^TWII"
    cache_key = f"elliott:{normalized_symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached
    result = await asyncio.to_thread(_analyze_sync, normalized_symbol)
    if result.get("source") == "gemini":
        return _store_cache(cache_key, result)
    return result
