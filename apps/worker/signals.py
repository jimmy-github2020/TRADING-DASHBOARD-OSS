from __future__ import annotations

import pandas as pd

from models import Candle, SignalEvent


def scan_signal_events(candles: list[Candle]) -> list[SignalEvent]:
    if len(candles) < 30:
        return []

    frame = pd.DataFrame(
        [
            {
                "time": candle.time,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume or 0,
            }
            for candle in candles
        ]
    )
    close = frame["close"].astype(float)
    latest = candles[-1]
    previous = candles[-2]
    events: list[SignalEvent] = []

    rsi = _rsi(close, 14)
    latest_rsi = _last(rsi)
    if latest_rsi is not None and latest_rsi < 30:
        events.append(
            _event(
                latest,
                "rsi_oversold",
                f"RSI(14) = {latest_rsi:.2f}，低於 30，列入觀察。",
                {"rsi_14": latest_rsi},
            )
        )
    if latest_rsi is not None and latest_rsi > 70:
        events.append(
            _event(
                latest,
                "rsi_overbought",
                f"RSI(14) = {latest_rsi:.2f}，高於 70，列入觀察。",
                {"rsi_14": latest_rsi},
            )
        )

    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    signal = macd.ewm(span=9, adjust=False).mean()
    if len(macd.dropna()) >= 2:
        previous_cross = macd.iloc[-2] <= signal.iloc[-2]
        latest_cross = macd.iloc[-1] > signal.iloc[-1]
        if previous_cross and latest_cross:
            events.append(
                _event(
                    latest,
                    "macd_bullish_cross",
                    "MACD 線由下向上穿越 Signal 線，條件觸發，列入觀察。",
                    {"macd": float(macd.iloc[-1]), "signal": float(signal.iloc[-1])},
                )
            )

    bb_mid = close.rolling(window=20).mean()
    bb_std = close.rolling(window=20).std()
    upper = bb_mid + 2 * bb_std
    lower = bb_mid - 2 * bb_std
    if pd.notna(upper.iloc[-1]) and previous.close <= upper.iloc[-2] and latest.close > upper.iloc[-1]:
        events.append(
            _event(
                latest,
                "bb_upper_break",
                "收盤價突破布林通道上軌，條件觸發，列入觀察。",
                {"bb_upper": float(upper.iloc[-1])},
            )
        )
    if pd.notna(lower.iloc[-1]) and previous.close >= lower.iloc[-2] and latest.close < lower.iloc[-1]:
        events.append(
            _event(
                latest,
                "bb_lower_break",
                "收盤價跌破布林通道下軌，條件觸發，列入觀察。",
                {"bb_lower": float(lower.iloc[-1])},
            )
        )

    if latest.symbol == "^VIX" and latest.close > 30:
        events.append(
            _event(
                latest,
                "vix_above_30",
                f"VIX = {latest.close:.2f}，高於 30，市場波動風險升高。",
                {"vix": latest.close},
            )
        )

    return events


def _event(candle: Candle, event_type: str, message: str, payload: dict[str, float]) -> SignalEvent:
    full_payload = {
        **payload,
        "candle_time": candle.time.isoformat(),
        "close": candle.close,
        "disclaimer": "本訊息僅供研究與紀錄，非投資建議。",
    }
    return SignalEvent(
        event_type=event_type,
        symbol=candle.symbol,
        provider=candle.provider,
        timeframe=candle.timeframe,
        title=f"[訊號條件觸發] {candle.symbol}",
        message=f"{message}\n本訊息僅供研究與紀錄，非投資建議。",
        payload=full_payload,
    )


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _last(series: pd.Series) -> float | None:
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    return float(cleaned.iloc[-1])
