from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Literal

import numpy as np
import pandas as pd
import yfinance as yf

TechnicalSignal = Literal["bullish", "bearish", "neutral", "overbought", "oversold"]
RankingDirection = Literal["bullish", "bearish", "neutral"]
CACHE_TTL_SECONDS = 300

_CACHE: dict[tuple[Any, ...], tuple[float, Any]] = {}

WATCHLIST: list[tuple[str, str]] = [
    ("2330.TW", "台積電"),
    ("2308.TW", "台達電"),
    ("2454.TW", "聯發科"),
    ("2317.TW", "鴻海"),
    ("0050.TW", "元大台灣50"),
    ("006208.TW", "富邦台50"),
    ("2882.TW", "國泰金"),
    ("2002.TW", "中鋼"),
    ("2301.TW", "光寶科"),
    ("2327.TW", "國巨"),
    ("2618.TW", "長榮航"),
    ("3481.TW", "群創"),
    ("6442.TW", "光聖"),
    ("8299.TW", "群聯"),
    ("NVDA", "NVIDIA"),
    ("AVGO", "Broadcom"),
    ("TSM", "台積電 ADR"),
    ("MU", "Micron"),
    ("MRVL", "Marvell"),
    ("RKLB", "Rocket Lab"),
]


def _cached(key: tuple[Any, ...]) -> Any | None:
    cached = _CACHE.get(key)
    if cached and cached[0] > monotonic():
        return cached[1]
    return None


def _store_cache(key: tuple[Any, ...], value: Any) -> Any:
    _CACHE[key] = (monotonic() + CACHE_TTL_SECONDS, value)
    return value


def _latest_date() -> str:
    return datetime.now(UTC).date().isoformat()


def _fetch_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    history = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False, timeout=10)
    if history.empty:
        raise ValueError(f"No OHLCV data returned for {symbol}")
    required = {"High", "Low", "Close"}
    if not required.issubset(set(history.columns)):
        raise ValueError(f"OHLCV data for {symbol} is missing required columns")
    return history.dropna(subset=["High", "Low", "Close"])


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) <= period:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs.iloc[-1]))
    if pd.isna(value):
        return None
    return round(float(value), 2)


def _macd(close: pd.Series) -> float | None:
    if len(close) < 26:
        return None
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    value = (ema12 - ema26).iloc[-1]
    if pd.isna(value):
        return None
    return round(float(value), 2)


def _macd_cross(close: pd.Series) -> Literal["golden", "death", "none"]:
    if len(close) < 35:
        return "none"
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    if pd.isna(macd.iloc[-1]) or pd.isna(signal.iloc[-1]) or pd.isna(macd.iloc[-2]) or pd.isna(signal.iloc[-2]):
        return "none"
    if macd.iloc[-2] <= signal.iloc[-2] and macd.iloc[-1] > signal.iloc[-1]:
        return "golden"
    if macd.iloc[-2] >= signal.iloc[-2] and macd.iloc[-1] < signal.iloc[-1]:
        return "death"
    return "none"


def _kd(history: pd.DataFrame, period: int = 9) -> tuple[float | None, float | None]:
    if len(history) < period:
        return None, None
    low_min = history["Low"].rolling(period).min()
    high_max = history["High"].rolling(period).max()
    rsv = (history["Close"] - low_min) / (high_max - low_min).replace(0, np.nan) * 100
    k_values: list[float] = []
    d_values: list[float] = []
    k_prev = 50.0
    d_prev = 50.0
    for value in rsv.fillna(50):
        k_prev = k_prev * (2 / 3) + float(value) * (1 / 3)
        d_prev = d_prev * (2 / 3) + k_prev * (1 / 3)
        k_values.append(k_prev)
        d_values.append(d_prev)
    return round(k_values[-1], 2), round(d_values[-1], 2)


def _ma(close: pd.Series, period: int) -> float | None:
    if len(close) < period:
        return None
    value = close.rolling(period).mean().iloc[-1]
    if pd.isna(value):
        return None
    return round(float(value), 2)


def rsi_signal(value: float | None) -> Literal["overbought", "oversold", "neutral"]:
    if value is None:
        return "neutral"
    if value > 70:
        return "overbought"
    if value < 30:
        return "oversold"
    return "neutral"


def macd_signal(value: float | None) -> Literal["bullish", "bearish"]:
    return "bullish" if value is not None and value > 0 else "bearish"


def kd_signal(k_value: float | None, d_value: float | None) -> Literal["golden_cross", "death_cross", "neutral"]:
    if k_value is None or d_value is None:
        return "neutral"
    if k_value > d_value:
        return "golden_cross"
    if k_value < d_value:
        return "death_cross"
    return "neutral"


def ma_signal(close: float | None, ma_value: float | None) -> RankingDirection:
    if close is None or ma_value is None:
        return "neutral"
    if close > ma_value:
        return "bullish"
    if close < ma_value:
        return "bearish"
    return "neutral"


def _overall(signals: list[str]) -> RankingDirection:
    bullish = sum(1 for item in signals if item in ("bullish", "golden_cross"))
    bearish = sum(1 for item in signals if item in ("bearish", "death_cross"))
    if bullish > bearish:
        return "bullish"
    if bearish > bullish:
        return "bearish"
    return "neutral"


def _summary_sync(symbol: str) -> dict[str, Any]:
    history = _fetch_history(symbol)
    close = history["Close"]
    latest_close = float(close.iloc[-1])
    rsi = _rsi(close)
    macd = _macd(close)
    kd_k, kd_d = _kd(history)
    ma20 = _ma(close, 20)
    ma60 = _ma(close, 60)
    signals = {
        "RSI": rsi_signal(rsi),
        "MACD": macd_signal(macd),
        "KD": "bullish" if kd_signal(kd_k, kd_d) == "golden_cross" else "bearish" if kd_signal(kd_k, kd_d) == "death_cross" else "neutral",
        "MA20": ma_signal(latest_close, ma20),
        "MA60": ma_signal(latest_close, ma60),
    }
    return {
        "symbol": symbol,
        "updated_at": history.index[-1].date().isoformat(),
        "indicators": {
            "RSI": {"value": rsi, "signal": signals["RSI"]},
            "MACD": {"value": macd, "signal": signals["MACD"]},
            "KD": {"k": kd_k, "d": kd_d, "signal": signals["KD"]},
            "MA20": {"value": ma20, "signal": signals["MA20"]},
            "MA60": {"value": ma60, "signal": signals["MA60"]},
        },
        "overall": _overall(list(signals.values())),
    }


async def get_technical_summary(symbol: str = "^TWII") -> dict[str, Any]:
    normalized_symbol = symbol.strip() or "^TWII"
    key = ("technical_summary", normalized_symbol)
    cached = _cached(key)
    if cached:
        return cached
    result = await asyncio.to_thread(_summary_sync, normalized_symbol)
    return _store_cache(key, result)


def _score_from_summary(symbol: str, name: str) -> dict[str, Any]:
    summary = _summary_sync(symbol)
    indicators = summary["indicators"]
    score = 50
    signals: list[str] = []

    rsi_value = indicators["RSI"]["value"]
    if rsi_value is not None:
        if 45 <= rsi_value <= 70:
            score += 15
            signals.append("RSI 強勢")
        elif rsi_value > 75:
            score -= 8
            signals.append("RSI 過熱")
        elif rsi_value < 35:
            score -= 10
            signals.append("RSI 偏弱")

    for key in ("MACD", "MA20", "MA60"):
        signal = indicators[key]["signal"]
        if signal == "bullish":
            score += 10
            signals.append(f"{key} 多頭")
        elif signal == "bearish":
            score -= 8
            signals.append(f"{key} 空頭")

    kd = indicators["KD"]["signal"]
    if kd == "bullish":
        score += 8
        signals.append("KD 金叉")
    elif kd == "bearish":
        score -= 6
        signals.append("KD 死叉")

    score = max(0, min(100, score))
    direction = "bullish" if score >= 65 else "bearish" if score < 45 else "neutral"
    return {
        "symbol": symbol,
        "name": name,
        "score": score,
        "signals": signals[:3] or ["訊號中性"],
        "direction": direction,
    }


async def get_technical_ranking(market: str = "TAIEX", limit: int = 10) -> dict[str, Any]:
    normalized_market = market.strip().upper() or "TAIEX"
    normalized_limit = max(1, min(limit, 20))
    key = ("technical_ranking", normalized_market, normalized_limit)
    cached = _cached(key)
    if cached:
        return cached

    items: list[dict[str, Any]] = []
    for symbol, name in WATCHLIST:
        try:
            items.append(await asyncio.to_thread(_score_from_summary, symbol, name))
        except Exception:
            continue
    if not items:
        raise ValueError("No technical ranking data could be calculated")

    ranked = sorted(items, key=lambda item: item["score"], reverse=True)[:normalized_limit]
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    result = {"updated_at": _latest_date(), "rankings": ranked}
    return _store_cache(key, result)


def _signal_from_symbol(symbol: str, name: str) -> dict[str, Any]:
    history = _fetch_history(symbol, period="6mo")
    close = history["Close"]
    macd = _macd(close)
    return {
        "symbol": symbol,
        "name": name,
        "rsi": _rsi(close),
        "macd_signal": macd_signal(macd),
        "macd": macd,
        "macd_cross": _macd_cross(close),
        "updated_at": history.index[-1].date().isoformat(),
    }


async def get_watchlist_technical_signals(limit: int = 20) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(limit, 50))
    key = ("technical_signals", normalized_limit)
    cached = _cached(key)
    if cached:
        return cached

    items: list[dict[str, Any]] = []
    for symbol, name in WATCHLIST[:normalized_limit]:
        try:
            items.append(await asyncio.to_thread(_signal_from_symbol, symbol, name))
        except Exception:
            continue
    return _store_cache(key, items)
