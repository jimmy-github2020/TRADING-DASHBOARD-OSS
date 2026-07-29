from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import json

from models import Candle
from repository import MarketRepository


@dataclass(frozen=True)
class StrategyScanResult:
    scanned_symbols: int
    scanned_strategies: int
    triggered_signals: int
    errors: int


class StrategyScanner:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    def scan(self, timeframe: str = "1d", limit: int = 120) -> StrategyScanResult:
        triggered = 0
        errors = 0
        with self.repository.connect() as conn:
            strategies = self.repository.fetch_active_strategies(conn)
            symbols = self.repository.fetch_active_symbols(conn)

            for symbol in symbols:
                try:
                    candles = self.repository.fetch_recent_candles(
                        conn,
                        symbol.provider,
                        symbol.symbol,
                        timeframe,
                        limit,
                    )
                    if len(candles) < 30:
                        continue
                    context = IndicatorContext(candles)
                    for strategy in strategies:
                        conditions = strategy["conditions"]
                        if isinstance(conditions, str):
                            conditions = json.loads(conditions)
                        if evaluate_strategy(conditions, context):
                            direction = conditions.get("direction", "neutral")
                            self.repository.insert_signal(
                                conn,
                                symbol.symbol,
                                strategy["id"],
                                direction,
                                candles[-1].close,
                                {
                                    "strategy_name": strategy["name"],
                                    "provider": symbol.provider,
                                    "timeframe": timeframe,
                                    "condition_logic": conditions.get("logic", "AND"),
                                    "candle_time": candles[-1].time.isoformat(),
                                },
                            )
                            triggered += 1
                except Exception as exc:
                    errors += 1
                    self.repository.record_provider_error(
                        conn,
                        symbol.provider,
                        symbol.symbol,
                        timeframe,
                        type(exc).__name__,
                        str(exc),
                    )
            conn.commit()

        return StrategyScanResult(
            scanned_symbols=len(symbols),
            scanned_strategies=len(strategies),
            triggered_signals=triggered,
            errors=errors,
        )


class IndicatorContext:
    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles
        self.frame = pd.DataFrame(
            [
                {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume or 0,
                }
                for candle in candles
            ]
        )
        self.close = self.frame["close"].astype(float)
        self.high = self.frame["high"].astype(float)
        self.low = self.frame["low"].astype(float)

    @property
    def latest_price(self) -> float:
        return self.candles[-1].close

    def rsi(self, period: int) -> float | None:
        return _last(_rsi(self.close, period))

    def ma(self, period: int) -> float | None:
        return _last(self.close.rolling(window=period).mean())

    def macd_cross(self, direction: str) -> bool:
        ema_12 = self.close.ewm(span=12, adjust=False).mean()
        ema_26 = self.close.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9, adjust=False).mean()
        if len(macd.dropna()) < 2:
            return False
        if direction == "bullish":
            return bool(macd.iloc[-2] <= signal.iloc[-2] and macd.iloc[-1] > signal.iloc[-1])
        if direction == "bearish":
            return bool(macd.iloc[-2] >= signal.iloc[-2] and macd.iloc[-1] < signal.iloc[-1])
        return False

    def ma_cross(self, short: int, long: int, direction: str) -> bool:
        short_ma = self.close.rolling(window=short).mean()
        long_ma = self.close.rolling(window=long).mean()
        if pd.isna(short_ma.iloc[-2]) or pd.isna(long_ma.iloc[-2]):
            return False
        if direction == "bullish":
            return bool(short_ma.iloc[-2] <= long_ma.iloc[-2] and short_ma.iloc[-1] > long_ma.iloc[-1])
        if direction == "bearish":
            return bool(short_ma.iloc[-2] >= long_ma.iloc[-2] and short_ma.iloc[-1] < long_ma.iloc[-1])
        return False

    def bollinger_break(self, side: str, period: int = 20, stddev: float = 2.0) -> bool:
        mid = self.close.rolling(window=period).mean()
        spread = self.close.rolling(window=period).std() * stddev
        upper = mid + spread
        lower = mid - spread
        if pd.isna(upper.iloc[-2]) or pd.isna(lower.iloc[-2]):
            return False
        if side == "upper":
            return bool(self.close.iloc[-2] <= upper.iloc[-2] and self.close.iloc[-1] > upper.iloc[-1])
        if side == "lower":
            return bool(self.close.iloc[-2] >= lower.iloc[-2] and self.close.iloc[-1] < lower.iloc[-1])
        return False

    def kd_cross(self, direction: str) -> bool:
        lowest_low = self.low.rolling(window=9).min()
        highest_high = self.high.rolling(window=9).max()
        k = ((self.close - lowest_low) / (highest_high - lowest_low) * 100).rolling(window=3).mean()
        d = k.rolling(window=3).mean()
        if pd.isna(k.iloc[-2]) or pd.isna(d.iloc[-2]):
            return False
        if direction == "bullish":
            return bool(k.iloc[-2] <= d.iloc[-2] and k.iloc[-1] > d.iloc[-1])
        if direction == "bearish":
            return bool(k.iloc[-2] >= d.iloc[-2] and k.iloc[-1] < d.iloc[-1])
        return False


def evaluate_strategy(conditions: dict[str, Any], context: IndicatorContext) -> bool:
    items = conditions.get("conditions", [])
    if not items:
        return False

    results = [evaluate_condition(item, context) for item in items]
    logic = str(conditions.get("logic", "AND")).upper()
    if logic == "OR":
        return any(results)
    return all(results)


def evaluate_condition(condition: dict[str, Any], context: IndicatorContext) -> bool:
    kind = condition.get("type")
    if kind == "rsi":
        value = context.rsi(int(condition.get("period", 14)))
        return _compare(value, condition.get("operator"), float(condition.get("value")))
    if kind == "macd_cross":
        return context.macd_cross(str(condition.get("direction", "bullish")))
    if kind == "ma_cross":
        return context.ma_cross(
            int(condition.get("short", 5)),
            int(condition.get("long", 20)),
            str(condition.get("direction", "bullish")),
        )
    if kind == "bollinger_break":
        return context.bollinger_break(
            str(condition.get("side", "upper")),
            int(condition.get("period", 20)),
            float(condition.get("stddev", 2)),
        )
    if kind == "kd_cross":
        return context.kd_cross(str(condition.get("direction", "bullish")))
    return False


def _compare(value: float | None, operator: str, target: float) -> bool:
    if value is None:
        return False
    if operator == "<":
        return value < target
    if operator == "<=":
        return value <= target
    if operator == ">":
        return value > target
    if operator == ">=":
        return value >= target
    if operator == "==":
        return value == target
    return False


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
