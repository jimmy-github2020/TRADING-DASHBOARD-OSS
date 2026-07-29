from __future__ import annotations

import asyncio
import json
from typing import Literal, TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yfinance as yf

SentimentScope = Literal["tw", "us"]

FNG_URL = "https://api.alternative.me/fng/"
USER_AGENT = "TRADING-DASHBOARD/0.1 (+local-development)"


class SentimentFetchResult(TypedDict):
    vix: float | None
    put_call_ratio: float | None
    fear_greed_score: int | None
    fear_greed_label: str | None


def _fetch_url(url: str, timeout: int = 8) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _fetch_fear_greed() -> tuple[int | None, str | None]:
    try:
        payload = json.loads(_fetch_url(FNG_URL).decode("utf-8"))
        latest = (payload.get("data") or [{}])[0]
        raw_value = latest.get("value")
        score = int(raw_value) if raw_value is not None else None
        label = latest.get("value_classification")
        return score, str(label) if label else None
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, json.JSONDecodeError, IndexError):
        return None, None


def _fetch_vix() -> float | None:
    try:
        history = yf.Ticker("^VIX").history(period="5d", interval="1d", timeout=8)
        if history.empty or "Close" not in history:
            return None
        close_values = history["Close"].dropna()
        if close_values.empty:
            return None
        return round(float(close_values.iloc[-1]), 4)
    except Exception:
        return None


def _fetch_sentiment_sync(_scope: SentimentScope) -> SentimentFetchResult:
    fear_greed_score, fear_greed_label = _fetch_fear_greed()
    vix = _fetch_vix()

    return {
        "vix": vix,
        # TODO: Replace this mock with a real PCR provider when CBOE/FRED integration is added.
        "put_call_ratio": 0.85,
        "fear_greed_score": fear_greed_score,
        "fear_greed_label": fear_greed_label,
    }


async def fetch_sentiment(scope: SentimentScope) -> SentimentFetchResult:
    return await asyncio.to_thread(_fetch_sentiment_sync, scope)
