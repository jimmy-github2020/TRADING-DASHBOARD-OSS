from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd


class BacktestInputError(ValueError):
    pass


@dataclass(frozen=True)
class BacktestRequestData:
    strategy_id: str
    symbols: list[str]
    start_date: date
    end_date: date
    timeframe: str
    initial_capital: float
    commission: float


class BacktestEngine:
    def run(self, request: BacktestRequestData, strategy: dict, candles_by_symbol: dict[str, list[dict]]) -> dict:
        if not request.symbols:
            raise BacktestInputError("At least one symbol is required")
        if request.start_date > request.end_date:
            raise BacktestInputError("start_date must be before end_date")

        per_symbol_capital = request.initial_capital / len(request.symbols)
        equity_frames: list[pd.Series] = []
        all_trades: list[dict[str, Any]] = []

        for symbol in request.symbols:
            candles = candles_by_symbol.get(symbol, [])
            if len(candles) < 30:
                raise BacktestInputError(f"{symbol} has insufficient OHLCV data for backtest")
            frame = _candles_to_frame(candles)
            signal = evaluate_strategy_series(strategy["conditions"], frame)
            equity, trades = simulate_symbol(
                frame=frame,
                signal=signal,
                symbol=symbol,
                initial_capital=per_symbol_capital,
                commission=request.commission,
            )
            equity_frames.append(equity)
            all_trades.extend(trades)

        portfolio_equity = pd.concat(equity_frames, axis=1).ffill().sum(axis=1)
        portfolio_equity = portfolio_equity[~portfolio_equity.index.duplicated(keep="last")]
        metrics = calculate_metrics(portfolio_equity, all_trades, request.initial_capital)

        return {
            "id": str(uuid4()),
            "strategy_id": request.strategy_id,
            "symbols": request.symbols,
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "timeframe": request.timeframe,
            "initial_capital": request.initial_capital,
            "commission": request.commission,
            **metrics,
            "equity_curve": [
                {"timestamp": timestamp.isoformat(), "value": round(float(value), 4)}
                for timestamp, value in portfolio_equity.items()
            ],
            "trades": all_trades,
        }


def _candles_to_frame(candles: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(candles)
    frame["time"] = pd.to_datetime(frame["time"])
    frame = frame.set_index("time").sort_index()
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = frame[column].astype(float)
    return frame


def evaluate_strategy_series(conditions: dict[str, Any], frame: pd.DataFrame) -> pd.Series:
    items = conditions.get("conditions", [])
    if not items:
        return pd.Series(False, index=frame.index)

    results = [evaluate_condition_series(item, frame) for item in items]
    signal = results[0]
    logic = str(conditions.get("logic", "AND")).upper()
    for result in results[1:]:
        signal = signal | result if logic == "OR" else signal & result
    return signal.fillna(False)


def evaluate_condition_series(condition: dict[str, Any], frame: pd.DataFrame) -> pd.Series:
    kind = condition.get("type")
    close = frame["close"]
    if kind == "rsi":
        value = _rsi(close, int(condition.get("period", 14)))
        return _compare(value, str(condition.get("operator")), float(condition.get("value")))
    if kind == "macd_cross":
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9, adjust=False).mean()
        return _cross(macd, signal, str(condition.get("direction", "bullish")))
    if kind == "ma_cross":
        short_ma = close.rolling(window=int(condition.get("short", 5))).mean()
        long_ma = close.rolling(window=int(condition.get("long", 20))).mean()
        return _cross(short_ma, long_ma, str(condition.get("direction", "bullish")))
    if kind == "bollinger_break":
        period = int(condition.get("period", 20))
        stddev = float(condition.get("stddev", 2))
        mid = close.rolling(window=period).mean()
        spread = close.rolling(window=period).std() * stddev
        upper = mid + spread
        lower = mid - spread
        if str(condition.get("side", "upper")) == "upper":
            return (close.shift(1) <= upper.shift(1)) & (close > upper)
        return (close.shift(1) >= lower.shift(1)) & (close < lower)
    if kind == "kd_cross":
        low = frame["low"]
        high = frame["high"]
        lowest_low = low.rolling(window=9).min()
        highest_high = high.rolling(window=9).max()
        k = ((close - lowest_low) / (highest_high - lowest_low) * 100).rolling(window=3).mean()
        d = k.rolling(window=3).mean()
        return _cross(k, d, str(condition.get("direction", "bullish")))
    return pd.Series(False, index=frame.index)


def simulate_symbol(
    frame: pd.DataFrame,
    signal: pd.Series,
    symbol: str,
    initial_capital: float,
    commission: float,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    cash = initial_capital
    shares = 0.0
    entry_price = 0.0
    entry_value = 0.0
    entry_date: pd.Timestamp | None = None
    equity_values: list[float] = []
    trades: list[dict[str, Any]] = []

    for timestamp, row in frame.iterrows():
        price = float(row["close"])
        should_hold = bool(signal.loc[timestamp])

        if shares == 0 and should_hold:
            shares = (cash * (1 - commission)) / price
            entry_value = shares * price
            cash = 0.0
            entry_price = price
            entry_date = timestamp
        elif shares > 0 and not should_hold:
            exit_value = shares * price * (1 - commission)
            trade_return = (exit_value - entry_value) / entry_value * 100 if entry_value > 0 else 0.0
            holding_days = max(1, (timestamp.date() - entry_date.date()).days) if entry_date is not None else 1
            trades.append(
                {
                    "symbol": symbol,
                    "entry_date": entry_date.isoformat() if entry_date is not None else timestamp.isoformat(),
                    "exit_date": timestamp.isoformat(),
                    "holding_days": holding_days,
                    "entry_price": round(entry_price, 4),
                    "exit_price": round(price, 4),
                    "return_pct": round(trade_return, 4),
                }
            )
            cash = exit_value
            shares = 0.0
            entry_price = 0.0
            entry_value = 0.0
            entry_date = None

        equity_values.append(cash + shares * price)

    if shares > 0:
        timestamp = frame.index[-1]
        price = float(frame["close"].iloc[-1])
        exit_value = shares * price * (1 - commission)
        trade_return = (exit_value - entry_value) / entry_value * 100 if entry_value > 0 else 0.0
        holding_days = max(1, (timestamp.date() - entry_date.date()).days) if entry_date is not None else 1
        trades.append(
            {
                "symbol": symbol,
                "entry_date": entry_date.isoformat() if entry_date is not None else timestamp.isoformat(),
                "exit_date": timestamp.isoformat(),
                "holding_days": holding_days,
                "entry_price": round(entry_price, 4),
                "exit_price": round(price, 4),
                "return_pct": round(trade_return, 4),
            }
        )

    return pd.Series(equity_values, index=frame.index, name=symbol), trades


def calculate_metrics(equity: pd.Series, trades: list[dict[str, Any]], initial_capital: float) -> dict[str, float | int]:
    total_return = (float(equity.iloc[-1]) / initial_capital - 1) * 100
    days = max(1, (equity.index[-1].date() - equity.index[0].date()).days)
    annual_return = ((float(equity.iloc[-1]) / initial_capital) ** (365 / days) - 1) * 100
    returns = equity.pct_change().dropna()
    sharpe = float((returns.mean() / returns.std()) * np.sqrt(252)) if len(returns) > 1 and returns.std() != 0 else 0.0
    drawdown = equity / equity.cummax() - 1
    max_drawdown = float(drawdown.min()) * 100
    wins = [trade for trade in trades if trade["return_pct"] > 0]
    losses = [trade for trade in trades if trade["return_pct"] < 0]
    total_profit = sum(trade["return_pct"] for trade in wins)
    total_loss = abs(sum(trade["return_pct"] for trade in losses))
    return {
        "total_return_pct": round(total_return, 4),
        "annual_return_pct": round(annual_return, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown_pct": round(max_drawdown, 4),
        "win_rate": round(len(wins) / len(trades) * 100, 4) if trades else 0.0,
        "total_trades": len(trades),
        "avg_holding_days": round(sum(trade["holding_days"] for trade in trades) / len(trades), 4) if trades else 0.0,
        "profit_factor": round(total_profit / total_loss, 4) if total_loss > 0 else (round(total_profit, 4) if total_profit > 0 else 0.0),
    }


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _compare(value: pd.Series, operator: str, target: float) -> pd.Series:
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
    return pd.Series(False, index=value.index)


def _cross(left: pd.Series, right: pd.Series, direction: str) -> pd.Series:
    if direction == "bearish":
        return (left.shift(1) >= right.shift(1)) & (left < right)
    return (left.shift(1) <= right.shift(1)) & (left > right)
