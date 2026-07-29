from __future__ import annotations

from dataclasses import dataclass

from cache import QuoteCache
from models import IngestionSummary, SymbolSpec
from providers import ProviderError, provider_for
from repository import MarketRepository
from universe import BINANCE_SYMBOLS, YFINANCE_SYMBOLS


DEFAULT_INGESTION_LIMIT = 200


@dataclass(frozen=True)
class IngestionRequest:
    provider: str
    symbol: str
    timeframe: str
    period: str | None = None
    limit: int | None = DEFAULT_INGESTION_LIMIT


class MarketIngestionService:
    def __init__(self, repository: MarketRepository, cache: QuoteCache) -> None:
        self.repository = repository
        self.cache = cache

    def ingest(self, request: IngestionRequest) -> IngestionSummary:
        provider = provider_for(request.provider)
        with self.repository.connect() as conn:
            run_id = self.repository.start_ingestion_run(
                conn,
                request.provider,
                request.symbol,
                request.timeframe,
            )
            try:
                symbol_spec = find_symbol(request.provider, request.symbol)
                if symbol_spec:
                    self.repository.upsert_symbol(conn, symbol_spec)

                candles = provider.fetch_ohlcv(
                    request.symbol,
                    request.timeframe,
                    period=request.period,
                    limit=request.limit,
                )
                rows_inserted, rows_updated = self.repository.upsert_candles(conn, candles)
                self.cache.store_latest_snapshot(candles)
                self.repository.finish_ingestion_run(
                    conn,
                    run_id,
                    "success",
                    rows_inserted=rows_inserted,
                    rows_updated=rows_updated,
                    message=f"rows_seen={len(candles)}",
                )
                conn.commit()
                return IngestionSummary(
                    provider=request.provider,
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                    rows_inserted=rows_inserted,
                    rows_updated=rows_updated,
                    rows_seen=len(candles),
                )
            except Exception as exc:
                self.repository.record_provider_error(
                    conn,
                    request.provider,
                    request.symbol,
                    request.timeframe,
                    type(exc).__name__,
                    str(exc),
                )
                self.repository.finish_ingestion_run(
                    conn,
                    run_id,
                    "error",
                    error_count=1,
                    message=str(exc)[:2000],
                )
                conn.commit()
                raise ProviderError(str(exc)) from exc

    def ingest_many(self, requests: list[IngestionRequest]) -> list[IngestionSummary]:
        summaries: list[IngestionSummary] = []
        for request in requests:
            try:
                summaries.append(self.ingest(request))
            except ProviderError as exc:
                print(
                    f"[ingestion:error] provider={request.provider} "
                    f"symbol={request.symbol} timeframe={request.timeframe} error={exc}"
                )
        return summaries


def default_requests(mode: str = "snapshot") -> list[IngestionRequest]:
    if mode == "daily":
        return [
            *(IngestionRequest("yfinance", spec.symbol, "1d") for spec in YFINANCE_SYMBOLS),
            *(IngestionRequest("binance", spec.symbol, "1d") for spec in BINANCE_SYMBOLS),
        ]

    return [
        *(IngestionRequest("yfinance", spec.symbol, "1h", period="60d") for spec in YFINANCE_SYMBOLS),
        *(IngestionRequest("binance", spec.symbol, "1h") for spec in BINANCE_SYMBOLS),
    ]


def all_symbol_requests(timeframe: str, period: str | None = None, limit: int | None = None) -> list[IngestionRequest]:
    request_limit = limit if limit is not None else DEFAULT_INGESTION_LIMIT
    return [
        *(IngestionRequest("yfinance", spec.symbol, timeframe, period=period, limit=request_limit) for spec in YFINANCE_SYMBOLS),
        *(IngestionRequest("binance", spec.symbol, timeframe, limit=request_limit) for spec in BINANCE_SYMBOLS),
    ]


def tracked_instrument_requests(
    instruments: list[dict[str, str]],
    mode: str,
) -> list[IngestionRequest]:
    requests: list[IngestionRequest] = []
    seen: set[tuple[str, str, str]] = set()

    for instrument in instruments:
        tier = instrument["tracking_tier"]
        provider = instrument["provider"]
        symbol = instrument["provider_symbol"]
        request: IngestionRequest | None = None
        if mode == "quote" and tier in {"quote", "daily", "intraday"}:
            request = IngestionRequest(provider, symbol, "1d", period="5d", limit=5)
        elif mode == "daily" and tier in {"daily", "intraday"}:
            request = IngestionRequest(provider, symbol, "1d", period="1y", limit=260)
        elif mode == "intraday" and tier == "intraday":
            request = IngestionRequest(provider, symbol, "1h", period="60d", limit=200)

        if request is None:
            continue
        key = (request.provider, request.symbol, request.timeframe)
        if key in seen:
            continue
        seen.add(key)
        requests.append(request)
    return requests


def find_symbol(provider: str, symbol: str) -> SymbolSpec | None:
    for spec in (*YFINANCE_SYMBOLS, *BINANCE_SYMBOLS):
        if spec.provider == provider and spec.symbol == symbol:
            return spec
    return None
