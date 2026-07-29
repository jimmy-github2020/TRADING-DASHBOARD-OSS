from __future__ import annotations

from typing import Any

import pandas as pd


def calculate_indicators(candles: list[dict]) -> dict[str, Any]:
    if not candles:
        return {}

    frame = pd.DataFrame(candles)
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["volume"].fillna(0).astype(float)

    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    bb_mid = close.rolling(window=20).mean()
    bb_std = close.rolling(window=20).std()
    lowest_low = low.rolling(window=9).min()
    highest_high = high.rolling(window=9).max()
    k_value = ((close - lowest_low) / (highest_high - lowest_low) * 100).rolling(window=3).mean()
    d_value = k_value.rolling(window=3).mean()

    return {
        "rsi_14": _last(_rsi(close, 14)),
        "macd": {
            "macd": _last(macd),
            "signal": _last(macd_signal),
            "histogram": _last(macd - macd_signal),
        },
        "bb_20_2": {
            "middle": _last(bb_mid),
            "upper": _last(bb_mid + 2 * bb_std),
            "lower": _last(bb_mid - 2 * bb_std),
        },
        "kd_9_3": {
            "k": _last(k_value),
            "d": _last(d_value),
        },
        "ema_20": _last(ema_20),
        "atr_14": _last(_atr(high, low, close, 14)),
        "obv": _last(_obv(close, volume)),
    }


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = close.diff().apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
    return (direction * volume).fillna(0).cumsum()


def _last(series: pd.Series) -> float | None:
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    return float(cleaned.iloc[-1])
