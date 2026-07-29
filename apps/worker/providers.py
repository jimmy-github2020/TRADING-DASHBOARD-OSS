from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Callable, Iterable

import pandas as pd
import requests
import yfinance as yf

from models import Candle


class ProviderError(RuntimeError):
    pass


def retry_call[T](operation: Callable[[], T], attempts: int = 3, base_delay: float = 1.0) -> T:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(base_delay * (2**attempt))
    raise ProviderError(str(last_error)) from last_error


class YFinanceProvider:
    name = "yfinance"
    _intervals = {"1d": "1d", "1h": "60m"}
    _default_periods = {"1d": "2y", "1h": "60d"}

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        period: str | None = None,
        limit: int | None = None,
    ) -> list[Candle]:
        if timeframe not in self._intervals:
            raise ProviderError(f"Unsupported yfinance timeframe: {timeframe}")

        interval = self._intervals[timeframe]
        fetch_period = period or self._default_periods[timeframe]

        def download() -> pd.DataFrame:
            data = yf.download(
                symbol,
                period=fetch_period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if data.empty:
                raise ProviderError(f"No data returned for {symbol} {timeframe}")
            return data

        frame = retry_call(download)
        frame = _normalize_yfinance_columns(frame)
        candles = [
            Candle(
                time=_to_utc_datetime(index),
                symbol=symbol,
                timeframe=timeframe,
                provider=self.name,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=_optional_float(row.get("Volume")),
            )
            for index, row in frame.iterrows()
            if _is_complete_ohlc(row)
        ]
        return candles[-limit:] if limit else candles


class BinanceProvider:
    name = "binance"
    _intervals = {"1d": "1d", "1h": "1h"}
    _base_url = "https://api.binance.com/api/v3/klines"

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        period: str | None = None,
        limit: int | None = 500,
    ) -> list[Candle]:
        if timeframe not in self._intervals:
            raise ProviderError(f"Unsupported Binance timeframe: {timeframe}")

        request_limit = max(1, min(limit or 500, 1000))

        def request() -> list[list[object]]:
            response = requests.get(
                self._base_url,
                params={
                    "symbol": symbol,
                    "interval": self._intervals[timeframe],
                    "limit": request_limit,
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload:
                raise ProviderError(f"No data returned for {symbol} {timeframe}")
            return payload

        rows = retry_call(request)
        return [
            Candle(
                time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
                symbol=symbol,
                timeframe=timeframe,
                provider=self.name,
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in rows
        ]


def provider_for(name: str) -> YFinanceProvider | BinanceProvider:
    if name == "yfinance":
        return YFinanceProvider()
    if name == "binance":
        return BinanceProvider()
    raise ProviderError(f"Unsupported provider: {name}")


def _normalize_yfinance_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        frame = frame.copy()
        frame.columns = frame.columns.get_level_values(0)
    return frame.dropna(subset=["Open", "High", "Low", "Close"])


def _to_utc_datetime(value: object) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(timezone.utc)
    return timestamp.tz_convert(timezone.utc).to_pydatetime()


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _is_complete_ohlc(row: pd.Series) -> bool:
    required: Iterable[str] = ("Open", "High", "Low", "Close")
    return all(field in row and not pd.isna(row[field]) for field in required)
