from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import logging
import re
from typing import Iterable

import requests

from instrument_sync import InstrumentRecord, SyncResult
from repository import MarketRepository


LOGGER = logging.getLogger(__name__)

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
SOURCE_URLS = {
    "nasdaq": NASDAQ_LISTED_URL,
    "other": OTHER_LISTED_URL,
}
OTHER_EXCHANGES = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
}


class UsInstrumentSyncService:
    def __init__(
        self,
        repository: MarketRepository,
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.repository = repository
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def sync(self, source: str = "all", dry_run: bool = False) -> list[SyncResult]:
        sources = tuple(SOURCE_URLS) if source == "all" else (source,)
        invalid = [item for item in sources if item not in SOURCE_URLS]
        if invalid:
            raise ValueError(f"Unsupported U.S. instrument source: {invalid[0]}")

        results: list[SyncResult] = []
        for source_name in sources:
            try:
                records = self.fetch(source_name)
                if dry_run:
                    result = SyncResult(
                        source=source_name,
                        status="dry_run",
                        rows_seen=len(records),
                        rows_inserted=0,
                        rows_updated=0,
                        error_count=0,
                    )
                else:
                    inserted, updated = self.repository.sync_instruments(
                        market="US",
                        source=f"nasdaq_trader_{source_name}",
                        records=records,
                    )
                    result = SyncResult(
                        source=source_name,
                        status="success",
                        rows_seen=len(records),
                        rows_inserted=inserted,
                        rows_updated=updated,
                        error_count=0,
                    )
            except Exception as exc:
                LOGGER.exception("U.S. instrument sync failed source=%s", source_name)
                result = SyncResult(
                    source=source_name,
                    status="failed",
                    rows_seen=0,
                    rows_inserted=0,
                    rows_updated=0,
                    error_count=1,
                    message=str(exc)[:1000],
                )
                if not dry_run:
                    self.repository.record_instrument_sync_failure(
                        market="US",
                        source=f"nasdaq_trader_{source_name}",
                        message=result.message or "Unknown instrument sync error",
                    )
            results.append(result)
        return results

    def fetch(self, source: str) -> list[InstrumentRecord]:
        response = self.session.get(
            SOURCE_URLS[source],
            timeout=self.timeout_seconds,
            headers={"User-Agent": "TRADING-DASHBOARD/1.0"},
        )
        response.raise_for_status()
        records = normalize_symbol_directory(response.text, source)
        if not records:
            raise ValueError(f"{source} returned no valid U.S. instruments")
        return records


def normalize_symbol_directory(
    content: str,
    source: str,
    fetched_at: datetime | None = None,
) -> list[InstrumentRecord]:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    reader = csv.DictReader(io.StringIO(content), delimiter="|")
    normalized: dict[str, InstrumentRecord] = {}

    for row in reader:
        if _is_file_footer(row):
            continue
        symbol = _clean(
            row.get("Symbol")
            if source == "nasdaq"
            else row.get("ACT Symbol") or row.get("NASDAQ Symbol")
        )
        if not symbol or not re.fullmatch(r"[A-Z0-9][A-Z0-9.$^/-]{0,15}", symbol):
            continue
        if _clean(row.get("Test Issue")) == "Y":
            continue

        name = _clean(row.get("Security Name"))
        exchange = (
            "NASDAQ"
            if source == "nasdaq"
            else OTHER_EXCHANGES.get(_clean(row.get("Exchange")) or "", "OTHER")
        )
        security_type = infer_security_type(
            name=name,
            is_etf=_clean(row.get("ETF")) == "Y",
        )

        normalized[symbol] = InstrumentRecord(
            canonical_symbol=symbol,
            market="US",
            exchange=exchange,
            security_type=security_type,
            name_zh=None,
            name_en=name,
            currency="USD",
            timezone="America/New_York",
            sector=None,
            listed_at=None,
            source=f"nasdaq_trader_{source}",
            source_updated_at=fetched_at,
            provider_symbols=(
                ("nasdaq_trader", symbol),
                ("yfinance", to_yfinance_symbol(symbol)),
            ),
        )

    return sorted(normalized.values(), key=lambda item: item.canonical_symbol)


def infer_security_type(name: str | None, is_etf: bool) -> str:
    if is_etf:
        return "etf"
    lowered = (name or "").lower()
    if "warrant" in lowered:
        return "warrant"
    if " unit" in lowered or lowered.endswith("units"):
        return "unit"
    if "preferred" in lowered or "depositary" in lowered:
        return "preferred"
    if " right" in lowered:
        return "right"
    return "stock"


def to_yfinance_symbol(symbol: str) -> str:
    return symbol.replace(".", "-").replace("/", "-")


def _is_file_footer(row: dict[str, str | None]) -> bool:
    return any(
        (value or "").startswith("File Creation Time")
        for value in row.values()
    )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
