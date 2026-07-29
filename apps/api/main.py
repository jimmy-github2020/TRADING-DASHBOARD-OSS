import asyncio
import hashlib
import json
from datetime import date
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from ai_brief import MarketBriefDisabledError, MarketBriefProviderError, MarketBriefService
from backtest import BacktestEngine, BacktestInputError, BacktestRequestData
from cache import QuoteCache
from config import load_settings
from fundamentals import fetch_fundamentals
from indicators import calculate_indicators
from market_quote import fetch_yahoo_fallback_ohlcv, fetch_yahoo_fallback_quotes
from mcp_server import router as mcp_router
from quant import (
    ApiStrategyScanner,
    CorrelationAnalyzer,
    CorrelationInputError,
    SectorRotationAnalyzer,
    SectorRotationInputError,
    StockRankingAnalyzer,
    StockRankingInputError,
    VolatilityAnalyzer,
    VolatilityInputError,
)
from repository import MarketRepository
from responses import api_response
from routers.alert_rules import router as alert_rules_router
from routers.ai_brief import router as ai_brief_router
from routers.elliott_wave import router as elliott_wave_router
from routers.institutional import router as institutional_router
from routers.instruments import router as instruments_router
from routers.market_candles import router as market_candles_router
from routers.news import router as news_router
from routers.notifications import router as notifications_router
from routers.sentiment import router as sentiment_router
from routers.stocks import router as stocks_router
from routers.technical import router as technical_router
from routers.telegram import root_router as telegram_root_router
from routers.telegram import router as telegram_router
from routers.watchlists import router as watchlists_router


settings = load_settings()
repository = MarketRepository(settings.database_url)
quote_cache = QuoteCache(settings.redis_url)
strategy_scanner = ApiStrategyScanner(settings.database_url)
correlation_analyzer = CorrelationAnalyzer(settings.database_url)
volatility_analyzer = VolatilityAnalyzer(settings.database_url)
sector_rotation_analyzer = SectorRotationAnalyzer(settings.database_url)
stock_ranking_analyzer = StockRankingAnalyzer(settings.database_url)
backtest_engine = BacktestEngine()
market_brief_service = MarketBriefService(
    repository=repository,
    sector_rotation_analyzer=sector_rotation_analyzer,
    stock_ranking_analyzer=stock_ranking_analyzer,
    redis_url=settings.redis_url,
    openai_api_key=settings.openai_api_key,
    enabled=settings.ai_brief_enabled,
    model=settings.ai_brief_model,
)

app = FastAPI(title="Trading Dashboard API", version="0.1.0")
app.include_router(alert_rules_router)
app.include_router(ai_brief_router)
app.include_router(elliott_wave_router)
app.include_router(institutional_router)
app.include_router(instruments_router)
app.include_router(market_candles_router)
app.include_router(news_router)
app.include_router(notifications_router)
app.include_router(sentiment_router)
app.include_router(stocks_router)
app.include_router(technical_router)
app.include_router(telegram_router)
app.include_router(telegram_root_router)
app.include_router(watchlists_router)
app.include_router(mcp_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    conditions: dict[str, Any]


class StrategyActiveRequest(BaseModel):
    is_active: bool


class BacktestRunRequest(BaseModel):
    strategy_id: str
    symbols: list[str] = Field(min_length=1)
    start_date: date
    end_date: date
    timeframe: str = Field(default="1d", pattern="^(1d|1h)$")
    initial_capital: float = Field(default=100000, gt=0)
    commission: float = Field(default=0.001, ge=0)


class PortfolioHoldingRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    name_zh: str | None = Field(default=None, max_length=50)
    name_en: str | None = Field(default=None, max_length=100)
    category: str = Field(default="觀察", max_length=10)
    owned: bool = False


class DailyNoteRequest(BaseModel):
    content: str = ""


async def _get_fundamentals_payload(symbol: str) -> dict[str, Any]:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")
    cache_key = f"fundamentals:v3:{normalized_symbol}"
    client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    try:
        cached = await client.get(cache_key)
        if cached:
            payload = json.loads(cached)
            payload["_cache"] = "hit"
            return payload

        try:
            payload = await asyncio.to_thread(fetch_fundamentals, normalized_symbol)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Fundamentals provider error: {exc}") from exc

        await client.setex(cache_key, 3600, json.dumps(payload, ensure_ascii=False))
        payload["_cache"] = "miss"
        return payload
    finally:
        await client.aclose()


async def check_postgres() -> str:
    conn: asyncpg.Connection | None = None
    try:
        conn = await asyncpg.connect(settings.database_url)
        await conn.fetchval("SELECT 1")
        return "ok"
    except Exception:
        return "error"
    finally:
        if conn is not None:
            await conn.close()


async def check_redis() -> str:
    client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    try:
        pong: Any = await client.ping()
        return "ok" if pong else "error"
    except Exception:
        return "error"
    finally:
        await client.aclose()


@app.get("/health")
async def health() -> dict[str, str]:
    db_status = await check_postgres()
    redis_status = await check_redis()
    status = "ok" if db_status == "ok" and redis_status == "ok" else "error"

    return {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db": db_status,
        "redis": redis_status,
    }


@app.get("/api/v1/health")
async def health_v1() -> dict[str, str]:
    return await health()


@app.get("/api/v1/symbols")
async def get_symbols() -> dict[str, Any]:
    symbols = await repository.fetch_symbols()
    return api_response(symbols, {"count": len(symbols)})


@app.get("/api/v1/quotes/snapshot")
async def get_quote_snapshot() -> dict[str, Any]:
    snapshots = await quote_cache.fetch_snapshots()
    source = "redis"
    if not snapshots:
        snapshots = await repository.fetch_latest_snapshots()
        source = "db"
    return api_response(snapshots, {"count": len(snapshots), "source": source})


@app.get("/api/v1/market/quote")
async def get_market_quote(
    symbols: str,
    timeframe: str = Query("1d", pattern="^(1d|1h)$"),
    realtime: bool = False,
) -> dict[str, Any]:
    symbol_list = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="At least one symbol is required")
    quotes = await repository.fetch_market_quotes(symbol_list, timeframe)
    if realtime and timeframe == "1d":
        # TODO: Move realtime quote ingestion into worker/Redis so UI polling does not depend on Yahoo fallback.
        fallback_quotes = await fetch_yahoo_fallback_quotes(symbol_list)
        fallback_by_symbol = {quote["symbol"]: quote for quote in fallback_quotes}
        quotes = [fallback_by_symbol.get(quote["symbol"], quote) for quote in quotes]
    missing_symbols = [quote["symbol"] for quote in quotes if quote.get("source") == "missing"]
    if missing_symbols and timeframe == "1d":
        # TODO: Move this fallback into the worker/yfinance ingestion path so the homepage can rely on TimescaleDB only.
        fallback_quotes = await fetch_yahoo_fallback_quotes(missing_symbols)
        fallback_by_symbol = {quote["symbol"]: quote for quote in fallback_quotes}
        quotes = [fallback_by_symbol.get(quote["symbol"], quote) for quote in quotes]
    source = "db+yahoo_fallback" if any(quote.get("source") == "yahoo_fallback" for quote in quotes) else "db"
    return api_response(quotes, {"count": len(quotes), "timeframe": timeframe, "source": source, "realtime": realtime})


@app.get("/api/v1/portfolio/holdings")
async def get_portfolio_holdings() -> dict[str, Any]:
    holdings = await repository.fetch_portfolio_holdings()
    return api_response(holdings, {"count": len(holdings)})


@app.post("/api/v1/portfolio/holdings")
async def add_portfolio_holding(request: PortfolioHoldingRequest) -> dict[str, Any]:
    holding = await repository.upsert_portfolio_holding(
        symbol=request.symbol.strip().upper(),
        name_zh=request.name_zh,
        name_en=request.name_en,
        category=request.category,
        owned=request.owned,
    )
    return api_response(holding, {"created": True})


async def _get_daily_note_payload(note_date: date) -> dict[str, Any]:
    note = await repository.fetch_daily_note(note_date)
    if note is None:
        return {
            "note_date": note_date.isoformat(),
            "content": "",
            "created_at": None,
            "updated_at": None,
        }
    return note


@app.post("/api/notes/{note_date}")
async def save_daily_note(note_date: date, request: DailyNoteRequest) -> dict[str, Any]:
    return await repository.upsert_daily_note(note_date, request.content)


@app.get("/api/notes/{note_date}")
async def get_daily_note(note_date: date) -> dict[str, Any]:
    return await _get_daily_note_payload(note_date)


@app.get("/api/v1/notes/{note_date}")
async def get_daily_note_v1(note_date: date) -> dict[str, Any]:
    note = await _get_daily_note_payload(note_date)
    return api_response(note, {"source": "db" if note["updated_at"] else "empty"})


@app.post("/api/v1/notes/{note_date}")
async def save_daily_note_v1(note_date: date, request: DailyNoteRequest) -> dict[str, Any]:
    note = await repository.upsert_daily_note(note_date, request.content)
    return api_response(note, {"saved": True})


@app.get("/api/fundamentals")
async def get_fundamentals(symbol: str) -> dict[str, Any]:
    payload = await _get_fundamentals_payload(symbol)
    cache_state = payload.pop("_cache", "miss")
    return api_response(payload, {"cache": cache_state})


@app.get("/api/v1/fundamentals")
async def get_fundamentals_v1(symbol: str) -> dict[str, Any]:
    payload = await _get_fundamentals_payload(symbol)
    cache_state = payload.pop("_cache", "miss")
    return api_response(payload, {"cache": cache_state})


async def _build_ohlcv_response(
    symbol: str,
    timeframe: str,
    provider: str,
    limit: int,
    range_value: str | None = None,
) -> dict[str, Any]:
    candles = await repository.fetch_ohlcv(symbol, timeframe, provider, limit)
    source = "db"
    warning: str | None = None
    fallback_range: str | None = None
    if not candles:
        fallback = await fetch_yahoo_fallback_ohlcv(symbol, timeframe, limit, range_value)
        candles = fallback["candles"]
        warning = fallback.get("warning")
        fallback_range = fallback.get("range")
        source = "yahoo_fallback" if candles else source
    if not candles:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No OHLCV data found",
                "symbol": symbol,
                "timeframe": timeframe,
                "provider": provider,
            },
        )
    return api_response(
        candles,
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "provider": provider,
            "range": range_value,
            "limit": limit,
            "count": len(candles),
            "source": source,
            "fallback_range": fallback_range,
            "warning": warning,
        },
    )


@app.get("/api/v1/quotes/ohlcv")
async def get_ohlcv(
    symbol: str,
    timeframe: str = Query("1d", pattern="^(5m|1d|1h)$"),
    provider: str = Query("yfinance", pattern="^(yfinance|binance)$"),
    limit: int = Query(500, ge=1, le=5000),
    range: str | None = Query(None, pattern="^(1d|3d|1w|2w|1m|3m|6m|1y|2y|3y|5y|10y)$"),
) -> dict[str, Any]:
    return await _build_ohlcv_response(symbol, timeframe, provider, limit, range)


@app.get("/api/ohlcv")
async def get_ohlcv_alias(
    symbol: str,
    interval: str = Query("1d", pattern="^(5m|1d|1h)$"),
    provider: str = Query("yfinance", pattern="^(yfinance|binance)$"),
    limit: int = Query(120, ge=1, le=5000),
    range: str | None = Query(None, pattern="^(1d|3d|1w|2w|1m|3m|6m|1y|2y|3y|5y|10y)$"),
) -> dict[str, Any]:
    return await _build_ohlcv_response(symbol, interval, provider, limit, range)


@app.get("/api/v1/indicators")
async def get_indicators(
    symbol: str,
    timeframe: str = Query("1d", pattern="^(1d|1h)$"),
    provider: str = Query("yfinance", pattern="^(yfinance|binance)$"),
    limit: int = Query(200, ge=30, le=5000),
) -> dict[str, Any]:
    candles = await repository.fetch_ohlcv(symbol, timeframe, provider, limit)
    source = "db"
    if not candles:
        fallback = await fetch_yahoo_fallback_ohlcv(symbol, timeframe, limit)
        candles = fallback["candles"]
        source = "yahoo_fallback" if candles else source
    if not candles:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No OHLCV data found for indicator calculation",
                "symbol": symbol,
                "timeframe": timeframe,
                "provider": provider,
            },
        )
    return api_response(
        calculate_indicators(candles),
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "provider": provider,
            "input_count": len(candles),
            "source": source,
        },
    )


@app.get("/api/v1/analysis/correlation")
async def get_correlation(
    symbols: str,
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
) -> dict[str, Any]:
    symbol_list = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()]
    if len(symbol_list) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 個標的")

    cache_key = f"correlation:{','.join(sorted(symbol_list))}:{period}"
    client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    try:
        cached = await client.get(cache_key)
        if cached:
            return api_response(json.loads(cached), {"cache": "hit"})

        try:
            result = await correlation_analyzer.calculate(symbol_list, period)
        except CorrelationInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        await client.setex(cache_key, 600, json.dumps(result))
        return api_response(result, {"cache": "miss"})
    finally:
        await client.aclose()


@app.get("/api/v1/analysis/volatility")
async def get_volatility(
    symbols: str | None = None,
    period: str = Query("30", pattern="^(7|30|90|7d|30d|90d)$"),
    annualize: bool = True,
) -> dict[str, Any]:
    symbol_list = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()] if symbols else None
    if symbol_list is not None and len(symbol_list) < 2:
        raise HTTPException(status_code=400, detail="At least 2 symbols are required")

    cache_symbols = sorted(symbol_list) if symbol_list else ["default"]
    symbols_hash = hashlib.sha1(",".join(cache_symbols).encode("utf-8")).hexdigest()[:16]
    period_days = period.removesuffix("d")
    cache_key = f"volatility:{symbols_hash}:{period_days}:{str(annualize).lower()}"
    client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    try:
        cached = await client.get(cache_key)
        if cached:
            return api_response(json.loads(cached), {"cache": "hit"})

        try:
            result = await volatility_analyzer.calculate(symbol_list, period_days, annualize)
        except VolatilityInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        await client.setex(cache_key, 600, json.dumps(result))
        return api_response(result, {"cache": "miss"})
    finally:
        await client.aclose()


@app.get("/api/v1/analysis/sector-rotation")
async def get_sector_rotation(
    period: str = Query("30", pattern="^(7|30|90|7d|30d|90d)$"),
    benchmark: str = "SPY",
) -> dict[str, Any]:
    period_days = period.removesuffix("d")
    cache_key = f"sector_rotation:{period_days}:{benchmark.strip().upper()}"
    client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    try:
        cached = await client.get(cache_key)
        if cached:
            return api_response(json.loads(cached), {"cache": "hit"})

        try:
            result = await sector_rotation_analyzer.calculate(period_days, benchmark)
        except SectorRotationInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        await client.setex(cache_key, 600, json.dumps(result, ensure_ascii=False))
        return api_response(result, {"cache": "miss"})
    finally:
        await client.aclose()


@app.get("/api/v1/analysis/stock-ranking")
async def get_stock_ranking(
    symbols: str | None = None,
    period: str = Query("30", pattern="^(7|30|90|7d|30d|90d)$"),
    benchmark: str = "^GSPC",
) -> dict[str, Any]:
    symbol_list = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()] if symbols else None
    if symbol_list is not None and len(symbol_list) < 2:
        raise HTTPException(status_code=400, detail="At least 2 symbols are required")

    cache_symbols = sorted(symbol_list) if symbol_list else ["default"]
    symbols_hash = hashlib.sha1(",".join(cache_symbols).encode("utf-8")).hexdigest()[:16]
    period_days = period.removesuffix("d")
    cache_key = f"stock_ranking:{symbols_hash}:{period_days}:{benchmark.strip()}"
    client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    try:
        cached = await client.get(cache_key)
        if cached:
            return api_response(json.loads(cached), {"cache": "hit"})

        try:
            result = await stock_ranking_analyzer.calculate(symbol_list, period_days, benchmark)
        except StockRankingInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        await client.setex(cache_key, 600, json.dumps(result, ensure_ascii=False))
        return api_response(result, {"cache": "miss"})
    finally:
        await client.aclose()


@app.post("/api/v1/backtest/run")
async def run_backtest(request: BacktestRunRequest) -> dict[str, Any]:
    strategy = await repository.fetch_strategy(request.strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    candles_by_symbol: dict[str, list[dict]] = {}
    for symbol in request.symbols:
        candles_by_symbol[symbol] = await repository.fetch_ohlcv_range(
            symbol=symbol,
            timeframe=request.timeframe,
            provider="yfinance",
            start_date=request.start_date,
            end_date=request.end_date,
        )

    try:
        result = backtest_engine.run(
            BacktestRequestData(
                strategy_id=request.strategy_id,
                symbols=request.symbols,
                start_date=request.start_date,
                end_date=request.end_date,
                timeframe=request.timeframe,
                initial_capital=request.initial_capital,
                commission=request.commission,
            ),
            strategy,
            candles_by_symbol,
        )
    except BacktestInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved = await repository.insert_backtest_result(result)
    return api_response(saved, {"created": True})


@app.get("/api/v1/backtest/list")
async def list_backtests(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    results = await repository.fetch_backtest_results(limit)
    return api_response(results, {"count": len(results)})


@app.get("/api/v1/backtest/{backtest_id}")
async def get_backtest(backtest_id: str) -> dict[str, Any]:
    result = await repository.fetch_backtest_result(backtest_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return api_response(result, {"id": backtest_id})


@app.post("/api/v1/ai/market-brief")
async def generate_market_brief() -> dict[str, Any]:
    try:
        result = await market_brief_service.generate()
    except MarketBriefDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MarketBriefProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    cache_state = result.pop("cache", "miss")
    return api_response(result, {"cache": cache_state})


@app.get("/api/v1/ai/market-brief/latest")
async def get_latest_market_brief() -> dict[str, Any]:
    if not settings.ai_brief_enabled:
        raise HTTPException(status_code=503, detail="AI Market Brief is not enabled")
    result = await repository.fetch_latest_ai_market_brief()
    if result is None:
        raise HTTPException(status_code=404, detail="No AI Market Brief has been generated yet")
    result["generated_at"] = result["created_at"]
    return api_response(result, {"source": "db"})


@app.get("/api/v1/ai/market-brief/history")
async def get_market_brief_history(limit: int = Query(5, ge=1, le=20)) -> dict[str, Any]:
    if not settings.ai_brief_enabled:
        raise HTTPException(status_code=503, detail="AI Market Brief is not enabled")
    results = await repository.fetch_ai_market_briefs(limit)
    for result in results:
        result["generated_at"] = result["created_at"]
    return api_response(results, {"count": len(results)})


@app.get("/api/v1/strategies")
async def get_strategies() -> dict[str, Any]:
    strategies = await repository.fetch_strategies()
    return api_response(strategies, {"count": len(strategies)})


@app.post("/api/v1/strategies")
async def create_strategy(request: StrategyCreateRequest) -> dict[str, Any]:
    strategy = await repository.create_strategy(request.name, request.conditions)
    return api_response(strategy, {"created": True})


@app.patch("/api/v1/strategies/{strategy_id}/active")
async def update_strategy_active(strategy_id: str, request: StrategyActiveRequest) -> dict[str, Any]:
    try:
        strategy = await repository.update_strategy_active(strategy_id, request.is_active)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return api_response(strategy, {"updated": True})


@app.delete("/api/v1/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str) -> dict[str, Any]:
    await repository.delete_strategy(strategy_id)
    return api_response({"id": strategy_id}, {"deleted": True})


@app.get("/api/v1/signals")
async def get_signals(
    strategy_id: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    signals = await repository.fetch_signals(strategy_id=strategy_id, limit=limit)
    return api_response(signals, {"count": len(signals)})


@app.post("/api/v1/signals/scan")
@app.post("/api/signals/scan")
async def scan_signals(
    timeframe: str = Query("1d", pattern="^(1d|1h)$"),
    limit: int = Query(120, ge=30, le=5000),
) -> dict[str, Any]:
    result = await strategy_scanner.scan(timeframe=timeframe, limit=limit)
    return api_response(result, {"timeframe": timeframe, "limit": limit})


@app.websocket("/ws/quotes")
async def quote_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=10)
            except asyncio.TimeoutError:
                message = ""

            if message.lower() == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
            elif message:
                await websocket.send_json(
                    {
                        "type": "echo",
                        "message": message,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
            else:
                snapshots = await quote_cache.fetch_snapshots()
                if not snapshots:
                    snapshots = await repository.fetch_latest_snapshots()
                await websocket.send_json(api_response(snapshots, {"type": "snapshot"}))
    except WebSocketDisconnect:
        return
