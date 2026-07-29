from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import logging
import re
from typing import Any, Iterable

import requests

from repository import MarketRepository


LOGGER = logging.getLogger(__name__)

TWSE_COMPANY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_COMPANY_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
SOURCE_URLS = {
    "twse": TWSE_COMPANY_URL,
    "tpex": TPEX_COMPANY_URL,
}


@dataclass(frozen=True)
class InstrumentRecord:
    canonical_symbol: str
    market: str
    exchange: str
    security_type: str
    name_zh: str | None
    name_en: str | None
    currency: str
    timezone: str
    sector: str | None
    listed_at: date | None
    source: str
    source_updated_at: datetime
    provider_symbols: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SyncResult:
    source: str
    status: str
    rows_seen: int
    rows_inserted: int
    rows_updated: int
    error_count: int
    message: str | None = None


class TaiwanInstrumentSyncService:
    def __init__(
        self,
        repository: MarketRepository,
        session: requests.Session | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.repository = repository
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def sync(self, source: str = "all", dry_run: bool = False) -> list[SyncResult]:
        sources = tuple(SOURCE_URLS) if source == "all" else (source,)
        invalid = [item for item in sources if item not in SOURCE_URLS]
        if invalid:
            raise ValueError(f"Unsupported Taiwan instrument source: {invalid[0]}")

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
                        market="TW",
                        source=f"{source_name}_openapi",
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
                LOGGER.exception("Taiwan instrument sync failed source=%s", source_name)
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
                        market="TW",
                        source=f"{source_name}_openapi",
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
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"{source} response is not a JSON array")

        records = normalize_company_rows(payload, source)
        if not records:
            raise ValueError(f"{source} returned no valid listed companies")
        return records


def normalize_company_rows(
    rows: Iterable[dict[str, Any]],
    source: str,
    fetched_at: datetime | None = None,
) -> list[InstrumentRecord]:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    exchange = "TWSE" if source == "twse" else "TPEx"
    suffix = ".TW" if source == "twse" else ".TWO"
    listed_keys = ("上市日期", "上櫃日期", "掛牌日期")
    normalized: dict[str, InstrumentRecord] = {}

    for row in rows:
        symbol = _clean(
            row.get("公司代號")
            or row.get("股票代號")
            or row.get("Code")
            or row.get("SecuritiesCompanyCode")
        )
        if not symbol or not re.fullmatch(r"[0-9A-Z]{4,8}", symbol):
            continue

        name_zh = _clean_display_name(
            row.get("公司簡稱")
            or row.get("公司名稱")
            or row.get("Name")
            or row.get("CompanyAbbreviation")
            or row.get("CompanyName")
        )
        name_en = _clean(
            row.get("英文簡稱")
            or row.get("公司英文名稱")
            or row.get("Symbol")
        )
        sector = _clean(
            row.get("產業別")
            or row.get("產業類別")
            or row.get("SecuritiesIndustryCode")
        )
        listed_at = _parse_date(
            next((row.get(key) for key in listed_keys if row.get(key)), None)
            or row.get("DateOfListing")
        )
        official_provider = "twse" if source == "twse" else "tpex"

        normalized[symbol] = InstrumentRecord(
            canonical_symbol=symbol,
            market="TW",
            exchange=exchange,
            security_type="stock",
            name_zh=name_zh,
            name_en=name_en,
            currency="TWD",
            timezone="Asia/Taipei",
            sector=sector,
            listed_at=listed_at,
            source=f"{source}_openapi",
            source_updated_at=fetched_at,
            provider_symbols=(
                (official_provider, symbol),
                ("yfinance", f"{symbol}{suffix}"),
            ),
        )

    return sorted(normalized.values(), key=lambda item: item.canonical_symbol)


def _parse_date(value: Any) -> date | None:
    text = _clean(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) != 8:
        return None
    try:
        return datetime.strptime(digits, "%Y%m%d").date()
    except ValueError:
        return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_display_name(value: Any) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    cleaned = re.sub(r"[*＊]+$", "", text).strip()
    return cleaned or None
