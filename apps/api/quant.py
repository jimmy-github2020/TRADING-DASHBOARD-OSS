from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import asyncpg
import numpy as np
import pandas as pd


class ApiStrategyScanner:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def scan(self, timeframe: str = "1d", limit: int = 120) -> dict[str, int]:
        conn = await asyncpg.connect(self.database_url)
        triggered = 0
        errors = 0
        try:
            strategies = await conn.fetch(
                "SELECT id::text, name, conditions FROM strategies WHERE is_active = TRUE ORDER BY created_at"
            )
            symbols = await conn.fetch(
                "SELECT symbol, provider FROM symbols WHERE is_active = TRUE ORDER BY provider, symbol"
            )
            for symbol_row in symbols:
                try:
                    candles = await _fetch_candles(
                        conn,
                        symbol_row["provider"],
                        symbol_row["symbol"],
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
                            await conn.execute(
                                """
                                INSERT INTO signals (symbol, strategy_id, direction, price, metadata)
                                VALUES ($1, $2::uuid, $3, $4, $5::jsonb)
                                """,
                                symbol_row["symbol"],
                                strategy["id"],
                                conditions.get("direction", "neutral"),
                                context.latest_price,
                                json.dumps(
                                    {
                                        "strategy_name": strategy["name"],
                                        "provider": symbol_row["provider"],
                                        "timeframe": timeframe,
                                        "condition_logic": conditions.get("logic", "AND"),
                                    }
                                ),
                            )
                            triggered += 1
                except Exception as exc:
                    errors += 1
                    await conn.execute(
                        """
                        INSERT INTO provider_errors (provider, symbol, timeframe, error_type, error_message)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        symbol_row["provider"],
                        symbol_row["symbol"],
                        timeframe,
                        type(exc).__name__,
                        str(exc)[:2000],
                    )
            return {
                "scanned_symbols": len(symbols),
                "scanned_strategies": len(strategies),
                "triggered_signals": triggered,
                "errors": errors,
            }
        finally:
            await conn.close()


async def _fetch_candles(
    conn: asyncpg.Connection,
    provider: str,
    symbol: str,
    timeframe: str,
    limit: int,
) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT time, open, high, low, close, volume
        FROM (
          SELECT time, open, high, low, close, volume
          FROM market_ohlcv
          WHERE provider = $1 AND symbol = $2 AND timeframe = $3
          ORDER BY time DESC
          LIMIT $4
        ) candles
        ORDER BY time ASC
        """,
        provider,
        symbol,
        timeframe,
        limit,
    )
    return [dict(row) for row in rows]


class IndicatorContext:
    def __init__(self, candles: list[dict]) -> None:
        self.frame = pd.DataFrame(candles)
        self.close = self.frame["close"].astype(float)
        self.high = self.frame["high"].astype(float)
        self.low = self.frame["low"].astype(float)

    @property
    def latest_price(self) -> float:
        return float(self.close.iloc[-1])

    def rsi(self, period: int) -> float | None:
        return _last(_rsi(self.close, period))

    def macd_cross(self, direction: str) -> bool:
        ema_12 = self.close.ewm(span=12, adjust=False).mean()
        ema_26 = self.close.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9, adjust=False).mean()
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
    results = [evaluate_condition(item, context) for item in conditions.get("conditions", [])]
    if not results:
        return False
    if str(conditions.get("logic", "AND")).upper() == "OR":
        return any(results)
    return all(results)


def evaluate_condition(condition: dict[str, Any], context: IndicatorContext) -> bool:
    kind = condition.get("type")
    if kind == "rsi":
        return _compare(context.rsi(int(condition.get("period", 14))), condition.get("operator"), float(condition.get("value")))
    if kind == "macd_cross":
        return context.macd_cross(str(condition.get("direction", "bullish")))
    if kind == "ma_cross":
        return context.ma_cross(int(condition.get("short", 5)), int(condition.get("long", 20)), str(condition.get("direction", "bullish")))
    if kind == "bollinger_break":
        return context.bollinger_break(str(condition.get("side", "upper")), int(condition.get("period", 20)), float(condition.get("stddev", 2)))
    if kind == "kd_cross":
        return context.kd_cross(str(condition.get("direction", "bullish")))
    return False


def _compare(value: float | None, operator: str, target: float) -> bool:
    if value is None:
        return False
    return {
        "<": value < target,
        "<=": value <= target,
        ">": value > target,
        ">=": value >= target,
        "==": value == target,
    }.get(str(operator), False)


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


class CorrelationInputError(ValueError):
    pass


DEFAULT_ANALYSIS_SYMBOLS = ["0050.TW", "2330.TW", "^GSPC", "^NDX", "^VIX", "GC=F", "CL=F", "DX-Y.NYB"]
DEFAULT_STOCK_RANKING_SYMBOLS = ["0050.TW", "006208.TW", "2330.TW", "2317.TW", "2882.TW", "^GSPC", "^VIX", "GC=F"]
SECTOR_ETFS = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]

SECTOR_NAMES = {
    "XLK": "科技",
    "XLF": "金融",
    "XLV": "醫療",
    "XLE": "能源",
    "XLY": "非必需消費",
    "XLP": "必需消費",
    "XLI": "工業",
    "XLB": "原物料",
    "XLU": "公用事業",
    "XLRE": "不動產",
    "XLC": "通訊",
}

SYMBOL_NAMES = {
    "0050.TW": "Taiwan 50",
    "006208.TW": "Fubon Taiwan 50",
    "2330.TW": "TSMC",
    "2317.TW": "Hon Hai",
    "2882.TW": "Cathay Financial",
    "^GSPC": "S&P 500",
    "^NDX": "Nasdaq 100",
    "^VIX": "VIX",
    "GC=F": "Gold",
    "CL=F": "WTI Crude Oil",
    "DX-Y.NYB": "US Dollar Index",
    "^TWII": "Taiwan Weighted",
    "^DJI": "Dow Jones",
    "^TNX": "US 10Y Yield",
    "^IRX": "US 2Y Yield",
}

STOCK_RANKING_NAMES = {
    "0050.TW": "台灣50",
    "006208.TW": "富邦台50",
    "2330.TW": "台積電",
    "2317.TW": "鴻海",
    "2882.TW": "國泰金",
    "^GSPC": "S&P500",
    "^VIX": "VIX恐慌",
    "GC=F": "黃金",
}


class CorrelationAnalyzer:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def calculate(self, symbols: list[str], period: str = "30d") -> dict[str, Any]:
        clean_symbols = list(dict.fromkeys(symbol.strip() for symbol in symbols if symbol.strip()))
        period_days = parse_period(period)
        if len(clean_symbols) < 2:
            raise CorrelationInputError("至少需要 2 個標的才能計算相關性矩陣")

        conn = await asyncpg.connect(self.database_url)
        try:
            closes: dict[str, pd.Series] = {}
            for symbol in clean_symbols:
                rows = await conn.fetch(
                    """
                    SELECT time, close
                    FROM (
                      SELECT time, close
                      FROM market_ohlcv
                      WHERE symbol = $1 AND timeframe = '1d'
                      ORDER BY time DESC
                      LIMIT $2
                    ) candles
                    ORDER BY time ASC
                    """,
                    symbol,
                    period_days + 1,
                )
                if len(rows) < 6:
                    raise CorrelationInputError(f"{symbol} 在 {period} 內資料不足 5 筆")
                frame = pd.DataFrame([dict(row) for row in rows])
                closes[symbol] = pd.Series(
                    frame["close"].astype(float).to_numpy(),
                    index=pd.to_datetime(frame["time"]),
                    name=symbol,
                )

            close_frame = pd.concat(closes.values(), axis=1, join="inner").sort_index()
            returns = np.log(close_frame / close_frame.shift(1)).dropna(how="any")
            if len(returns) < 5:
                raise CorrelationInputError(f"{period} 內可對齊的日報酬資料不足 5 筆")

            corr = returns.corr(method="pearson").reindex(index=clean_symbols, columns=clean_symbols)
            matrix = corr.round(4).where(pd.notnull(corr), None).values.tolist()
            return {
                "symbols": clean_symbols,
                "matrix": matrix,
                "period": period,
                "calculated_at": datetime.now(timezone.utc).isoformat(),
                "data_points": int(len(returns)),
            }
        finally:
            await conn.close()


def parse_period(period: str) -> int:
    allowed = {"7": 7, "30": 30, "90": 90, "7d": 7, "30d": 30, "90d": 90}
    if period not in allowed:
        raise CorrelationInputError("period only supports 7, 30, 90, 7d, 30d, or 90d")
    return allowed[period]


class VolatilityInputError(ValueError):
    pass


class VolatilityAnalyzer:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def calculate(
        self,
        symbols: list[str] | None = None,
        period: str = "30",
        annualize: bool = True,
    ) -> dict[str, Any]:
        clean_symbols = list(dict.fromkeys(symbol.strip() for symbol in (symbols or DEFAULT_ANALYSIS_SYMBOLS) if symbol.strip()))
        period_days = parse_period(period)
        if len(clean_symbols) < 2:
            raise VolatilityInputError("At least 2 symbols are required")

        conn = await asyncpg.connect(self.database_url)
        try:
            names = await self._fetch_symbol_names(conn, clean_symbols)
            items: list[dict[str, Any]] = []
            for symbol in clean_symbols:
                rows = await conn.fetch(
                    """
                    SELECT time, close
                    FROM (
                      SELECT time, close
                      FROM market_ohlcv
                      WHERE symbol = $1 AND timeframe = '1d'
                      ORDER BY time DESC
                      LIMIT $2
                    ) candles
                    ORDER BY time ASC
                    """,
                    symbol,
                    period_days + 1,
                )
                if len(rows) < 6:
                    raise VolatilityInputError(f"{symbol} has fewer than 5 daily return data points")

                close = pd.Series([float(row["close"]) for row in rows])
                returns = np.log(close / close.shift(1)).dropna()
                if len(returns) < 5:
                    raise VolatilityInputError(f"{symbol} has fewer than 5 aligned return data points")

                daily_std = float(returns.std(ddof=1))
                volatility = daily_std * (float(np.sqrt(252)) if annualize else 1.0) * 100
                period_return = (float(close.iloc[-1]) / float(close.iloc[0]) - 1.0) * 100
                max_drawdown = float((close / close.cummax() - 1.0).min()) * 100
                items.append(
                    {
                        "symbol": symbol,
                        "name": names.get(symbol) or SYMBOL_NAMES.get(symbol) or symbol,
                        "volatility_pct": round(volatility, 4),
                        "rank": 0,
                        "period_return_pct": round(period_return, 4),
                        "max_drawdown_pct": round(max_drawdown, 4),
                    }
                )

            items.sort(key=lambda item: item["volatility_pct"], reverse=True)
            for index, item in enumerate(items, start=1):
                item["rank"] = index

            return {
                "symbols": clean_symbols,
                "period": str(period_days),
                "annualize": annualize,
                "calculated_at": datetime.now(timezone.utc).isoformat(),
                "data_points": period_days,
                "items": items,
            }
        finally:
            await conn.close()

    async def _fetch_symbol_names(self, conn: asyncpg.Connection, symbols: list[str]) -> dict[str, str]:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (symbol) symbol, name
            FROM symbols
            WHERE symbol = ANY($1::text[])
            ORDER BY symbol, provider
            """,
            symbols,
        )
        return {row["symbol"]: row["name"] for row in rows if row["name"]}


class SectorRotationInputError(ValueError):
    pass


class SectorRotationAnalyzer:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def calculate(self, period: str = "30", benchmark: str = "SPY") -> dict[str, Any]:
        period_days = parse_period(period)
        clean_benchmark = benchmark.strip().upper()
        if clean_benchmark not in SECTOR_ETFS and clean_benchmark != "SPY":
            raise SectorRotationInputError("benchmark must be one of the sector ETFs or SPY")

        symbols = list(dict.fromkeys([*SECTOR_ETFS, clean_benchmark]))
        conn = await asyncpg.connect(self.database_url)
        try:
            close_by_symbol = await self._fetch_close_series(conn, symbols, period_days + 1)
            if clean_benchmark not in close_by_symbol:
                raise SectorRotationInputError(f"{clean_benchmark} has insufficient benchmark data")

            benchmark_close = close_by_symbol[clean_benchmark]
            benchmark_return = _period_return_pct(benchmark_close)
            items: list[dict[str, Any]] = []

            for symbol in SECTOR_ETFS:
                if symbol == clean_benchmark:
                    continue
                close = close_by_symbol.get(symbol)
                if close is None:
                    raise SectorRotationInputError(f"{symbol} has insufficient sector data")

                returns = np.log(close / close.shift(1)).dropna()
                if len(returns) < 5:
                    raise SectorRotationInputError(f"{symbol} has fewer than 5 aligned return data points")

                period_return = _period_return_pct(close)
                relative_return = period_return - benchmark_return
                momentum_score = float(returns.mean()) * float(np.sqrt(period_days))
                volatility = float(returns.std(ddof=1)) * float(np.sqrt(252)) * 100
                sharpe_ratio = momentum_score / (volatility / 100) if volatility != 0 else 0.0
                rs_score = _relative_strength(period_return, benchmark_return)
                items.append(
                    {
                        "symbol": symbol,
                        "sector_name": SECTOR_NAMES[symbol],
                        "period_return_pct": round(period_return, 4),
                        "relative_return_pct": round(relative_return, 4),
                        "momentum_score": round(momentum_score, 6),
                        "volatility_pct": round(volatility, 4),
                        "sharpe_ratio": round(sharpe_ratio, 4),
                        "rs_score": round(rs_score, 4),
                    }
                )

            items.sort(key=lambda item: item["rs_score"], reverse=True)
            for index, item in enumerate(items, start=1):
                item["rank"] = index

            return {
                "period": str(period_days),
                "benchmark": clean_benchmark,
                "benchmark_return_pct": round(benchmark_return, 4),
                "calculated_at": datetime.now(timezone.utc).isoformat(),
                "data_points": period_days,
                "items": items,
            }
        finally:
            await conn.close()

    async def _fetch_close_series(
        self,
        conn: asyncpg.Connection,
        symbols: list[str],
        limit: int,
    ) -> dict[str, pd.Series]:
        result: dict[str, pd.Series] = {}
        for symbol in symbols:
            rows = await conn.fetch(
                """
                SELECT time, close
                FROM (
                  SELECT time, close
                  FROM market_ohlcv
                  WHERE symbol = $1 AND timeframe = '1d'
                  ORDER BY time DESC
                  LIMIT $2
                ) candles
                ORDER BY time ASC
                """,
                symbol,
                limit,
            )
            if len(rows) < 6:
                continue
            frame = pd.DataFrame([dict(row) for row in rows])
            result[symbol] = pd.Series(
                frame["close"].astype(float).to_numpy(),
                index=pd.to_datetime(frame["time"]),
                name=symbol,
            )
        return result


def _period_return_pct(close: pd.Series) -> float:
    return (float(close.iloc[-1]) / float(close.iloc[0]) - 1.0) * 100


def _relative_strength(period_return: float, benchmark_return: float) -> float:
    denominator = 1.0 + benchmark_return / 100
    if denominator == 0:
        return 0.0
    return (1.0 + period_return / 100) / denominator


class StockRankingInputError(ValueError):
    pass


class StockRankingAnalyzer:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def calculate(
        self,
        symbols: list[str] | None = None,
        period: str = "30",
        benchmark: str = "^GSPC",
    ) -> dict[str, Any]:
        period_days = parse_period(period)
        clean_symbols = list(dict.fromkeys(symbol.strip() for symbol in (symbols or DEFAULT_STOCK_RANKING_SYMBOLS) if symbol.strip()))
        clean_benchmark = benchmark.strip()
        if len(clean_symbols) < 2:
            raise StockRankingInputError("At least 2 symbols are required")

        fetch_symbols = list(dict.fromkeys([*clean_symbols, clean_benchmark]))
        conn = await asyncpg.connect(self.database_url)
        try:
            close_by_symbol = await self._fetch_close_series(conn, fetch_symbols, max(period_days + 1, 21))
            if clean_benchmark not in close_by_symbol:
                raise StockRankingInputError(f"{clean_benchmark} has insufficient benchmark data")

            benchmark_return = _period_return_pct(close_by_symbol[clean_benchmark].tail(period_days + 1))
            raw_items: list[dict[str, Any]] = []
            for symbol in clean_symbols:
                close = close_by_symbol.get(symbol)
                if close is None:
                    raise StockRankingInputError(f"{symbol} has insufficient data")

                period_close = close.tail(period_days + 1)
                returns = np.log(period_close / period_close.shift(1)).dropna()
                if len(returns) < 5:
                    raise StockRankingInputError(f"{symbol} has fewer than 5 aligned return data points")

                period_return = _period_return_pct(period_close)
                momentum_raw = float(np.log(float(period_close.iloc[-1]) / float(period_close.iloc[0])))
                volatility = float(returns.std(ddof=1)) * float(np.sqrt(252)) * 100
                rs_raw = period_return - benchmark_return
                ma20 = close.tail(20).mean() if len(close) >= 20 else None
                trend_score = 50.0 if ma20 is None else (100.0 if float(close.iloc[-1]) > float(ma20) else 0.0)

                raw_items.append(
                    {
                        "symbol": symbol,
                        "name": STOCK_RANKING_NAMES.get(symbol) or SYMBOL_NAMES.get(symbol) or symbol,
                        "momentum_raw": momentum_raw,
                        "volatility_raw": volatility,
                        "rs_raw": rs_raw,
                        "trend_score": trend_score,
                        "period_return_pct": round(period_return, 4),
                        "volatility_pct": round(volatility, 4),
                    }
                )

            momentum_scores = _score_values([item["momentum_raw"] for item in raw_items])
            low_vol_scores = _score_values([-item["volatility_raw"] for item in raw_items])
            rs_scores = _score_values([item["rs_raw"] for item in raw_items])

            items: list[dict[str, Any]] = []
            for index, item in enumerate(raw_items):
                momentum_score = momentum_scores[index]
                low_vol_score = low_vol_scores[index]
                rs_score = rs_scores[index]
                trend_score = item["trend_score"]
                composite = (
                    momentum_score * 0.3
                    + low_vol_score * 0.2
                    + rs_score * 0.3
                    + trend_score * 0.2
                )
                items.append(
                    {
                        "symbol": item["symbol"],
                        "name": item["name"],
                        "composite_score": round(composite, 2),
                        "momentum_score": round(momentum_score, 2),
                        "low_vol_score": round(low_vol_score, 2),
                        "rs_score": round(rs_score, 2),
                        "trend_score": round(trend_score, 2),
                        "rank": 0,
                        "period_return_pct": item["period_return_pct"],
                        "volatility_pct": item["volatility_pct"],
                    }
                )

            items.sort(key=lambda row: row["composite_score"], reverse=True)
            for rank, item in enumerate(items, start=1):
                item["rank"] = rank

            return {
                "symbols": clean_symbols,
                "period": str(period_days),
                "benchmark": clean_benchmark,
                "benchmark_return_pct": round(benchmark_return, 4),
                "calculated_at": datetime.now(timezone.utc).isoformat(),
                "data_points": period_days,
                "items": items,
            }
        finally:
            await conn.close()

    async def _fetch_close_series(
        self,
        conn: asyncpg.Connection,
        symbols: list[str],
        limit: int,
    ) -> dict[str, pd.Series]:
        result: dict[str, pd.Series] = {}
        for symbol in symbols:
            rows = await conn.fetch(
                """
                SELECT time, close
                FROM (
                  SELECT time, close
                  FROM market_ohlcv
                  WHERE symbol = $1 AND timeframe = '1d'
                  ORDER BY time DESC
                  LIMIT $2
                ) candles
                ORDER BY time ASC
                """,
                symbol,
                limit,
            )
            if len(rows) < 6:
                continue
            frame = pd.DataFrame([dict(row) for row in rows])
            result[symbol] = pd.Series(
                frame["close"].astype(float).to_numpy(),
                index=pd.to_datetime(frame["time"]),
                name=symbol,
            )
        return result


def _score_values(values: list[float]) -> list[float]:
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return [50.0 for _ in values]
    return [max(0.0, min(100.0, (value - minimum) / (maximum - minimum) * 100)) for value in values]
