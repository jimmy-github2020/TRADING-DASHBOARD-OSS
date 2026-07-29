from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    provider: str
    name: str
    asset_class: str
    exchange: str | None = None
    currency: str | None = None
    timezone: str | None = None


@dataclass(frozen=True)
class Candle:
    time: datetime
    symbol: str
    timeframe: str
    provider: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None


@dataclass(frozen=True)
class IngestionSummary:
    provider: str
    symbol: str
    timeframe: str
    rows_inserted: int
    rows_updated: int
    rows_seen: int


@dataclass(frozen=True)
class SignalEvent:
    event_type: str
    symbol: str
    provider: str
    timeframe: str
    title: str
    message: str
    payload: dict[str, Any]
