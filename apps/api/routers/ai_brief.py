from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import asyncpg
from fastapi import APIRouter, Query
from pydantic import BaseModel
from redis.asyncio import Redis

from ai_tools import (
    get_daily_notes,
    get_market_summary,
    get_news_headlines,
    get_sentiment_data,
    get_technical_signals,
)
from config import load_settings
from services.ai_provider import AiBriefResult, generate_brief

router = APIRouter(prefix="/api/v1", tags=["ai-brief"])
settings = load_settings()


class AiBriefRequest(BaseModel):
    scope: Literal["tw", "us"] = "tw"


def _taipei_today() -> str:
    return (datetime.now(UTC) + timedelta(hours=8)).date().isoformat()


def _pending_result(provider: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "status": "pending",
        "direction": None,
        "summary": None,
        "key_points": [],
        "error": None,
    }


def _direction_score(direction: str | None) -> int:
    if direction == "bullish":
        return 1
    if direction == "bearish":
        return -1
    return 0


def _calculate_consensus(results: list[AiBriefResult]) -> dict[str, Any]:
    ok_results = [result for result in results if result.status == "ok" and result.direction is not None]
    if not ok_results:
        return {"status": "unavailable", "score": 50, "direction": None}

    average = sum(_direction_score(result.direction) for result in ok_results) / len(ok_results)
    score = round((average + 1) / 2 * 100)
    if average > 0:
        direction = "bullish"
    elif average < 0:
        direction = "bearish"
    else:
        direction = "neutral"

    if len(ok_results) == len(results):
        unique_directions = {result.direction for result in ok_results}
        status = "full" if len(unique_directions) == 1 else "partial"
    else:
        status = "partial"
    return {"status": status, "score": score, "direction": direction}


async def _build_context(scope: str) -> dict[str, Any]:
    market, technical, sentiment, news, notes = await asyncio.gather(
        get_market_summary(scope=scope),
        get_technical_signals(scope=scope),
        get_sentiment_data(scope=scope),
        get_news_headlines(scope=scope, limit=5),
        get_daily_notes(),
    )
    return {
        "scope": scope,
        "generated_at": datetime.now(UTC).isoformat(),
        "market_summary": market,
        "technical_signals": technical,
        "sentiment_data": sentiment,
        "news_headlines": news,
        "daily_notes": notes,
    }


async def _get_cached(cache_key: str) -> dict[str, Any] | None:
    client: Redis | None = None
    try:
        client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        cached = await client.get(cache_key)
        return json.loads(cached) if cached else None
    except Exception:
        return None
    finally:
        if client is not None:
            await client.aclose()


async def _set_cached(cache_key: str, payload: dict[str, Any]) -> None:
    client: Redis | None = None
    try:
        client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        await client.setex(cache_key, 900, json.dumps(payload, ensure_ascii=False))
    except Exception:
        return
    finally:
        if client is not None:
            await client.aclose()


async def _ensure_log_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_brief_log (
            id SERIAL PRIMARY KEY,
            scope TEXT NOT NULL,
            date DATE NOT NULL,
            openai_status TEXT,
            perplexity_status TEXT,
            gemini_status TEXT,
            consensus_status TEXT,
            consensus_score INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    await conn.execute("ALTER TABLE ai_brief_log ADD COLUMN IF NOT EXISTS gemini_status TEXT")


async def _insert_log(scope: str, date_value: str, payload: dict[str, Any]) -> None:
    conn: asyncpg.Connection | None = None
    try:
        conn = await asyncpg.connect(settings.database_url)
        await _ensure_log_table(conn)
        await conn.execute(
            """
            INSERT INTO ai_brief_log (
                scope, date, openai_status, perplexity_status, gemini_status, consensus_status, consensus_score
            )
            VALUES ($1, $2::date, $3, $4, $5, $6, $7)
            """,
            scope,
            date_value,
            payload["openai"]["status"],
            payload["perplexity"]["status"],
            payload["gemini"]["status"],
            payload["consensus"]["status"],
            payload["consensus"]["score"],
        )
    except Exception:
        return
    finally:
        if conn is not None:
            await conn.close()


async def _fetch_latest_logs(scope: str, limit: int) -> list[dict[str, Any]]:
    conn: asyncpg.Connection | None = None
    try:
        conn = await asyncpg.connect(settings.database_url)
        await _ensure_log_table(conn)
        rows = await conn.fetch(
            """
            SELECT id, scope, date, consensus_status, consensus_score, created_at
            FROM ai_brief_log
            WHERE scope = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            scope,
            limit,
        )
        return [
            {
                "id": row["id"],
                "scope": row["scope"],
                "date": row["date"].isoformat(),
                "consensus_status": row["consensus_status"],
                "consensus_score": row["consensus_score"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]
    except Exception:
        return []
    finally:
        if conn is not None:
            await conn.close()


@router.post("/ai/brief")
async def generate_ai_brief(request: AiBriefRequest) -> dict[str, Any]:
    today = _taipei_today()
    cache_key = f"ai_brief:v2:{request.scope}:{today}"
    cached = await _get_cached(cache_key)
    if cached:
        await _insert_log(request.scope, today, cached)
        return cached

    context = await _build_context(request.scope)
    openai_result, perplexity_result, gemini_result = await asyncio.gather(
        generate_brief("openai", context),
        generate_brief("perplexity", context),
        generate_brief("gemini", context),
    )
    consensus = _calculate_consensus([openai_result, perplexity_result, gemini_result])
    payload = {
        "scope": request.scope,
        "date": today,
        "openai": openai_result.to_dict(),
        "perplexity": perplexity_result.to_dict(),
        "gemini": gemini_result.to_dict(),
        "claude": _pending_result("claude"),
        "consensus": consensus,
    }
    await _insert_log(request.scope, today, payload)
    await _set_cached(cache_key, payload)
    return payload


@router.get("/ai/brief/latest")
async def get_latest_ai_brief(
    scope: Literal["tw", "us"] = Query("tw"),
    limit: int = Query(5, ge=1, le=20),
) -> list[dict[str, Any]]:
    return await _fetch_latest_logs(scope=scope, limit=limit)
