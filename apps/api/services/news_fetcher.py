from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Literal, TypedDict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from services.nlp_sentiment import analyze_headline_sentiment

NewsScope = Literal["tw", "us"]

TW_RSS_URL = "https://money.udn.com/rssfeed/news/1001/5591"
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"
USER_AGENT = "TRADING-DASHBOARD/0.1 (+local-development)"


class NewsItemPayload(TypedDict):
    title: str
    source: str
    url: str
    published_at: str | None
    sentiment: Literal["positive", "neutral", "negative"]
    sentiment_score: float


class NewsFetchResult(TypedDict):
    items: list[NewsItemPayload]
    error_message: str | None


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return value


def _with_sentiment(title: str, source: str, url: str, published_at: str | None) -> NewsItemPayload:
    sentiment = analyze_headline_sentiment(title)
    return {
        "title": title,
        "source": source,
        "url": url,
        "published_at": published_at,
        "sentiment": sentiment["sentiment"],
        "sentiment_score": sentiment["sentiment_score"],
    }


def _fetch_url(url: str, headers: dict[str, str] | None = None, timeout: int = 8) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _fetch_tw_news(limit: int) -> NewsFetchResult:
    body = _fetch_url(TW_RSS_URL)
    root = ElementTree.fromstring(body)
    items: list[NewsItemPayload] = []

    for item in root.findall("./channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        url = (item.findtext("link") or "").strip()
        published_at = _normalize_datetime((item.findtext("pubDate") or "").strip())
        items.append(
            _with_sentiment(
                title=title,
                source="經濟日報",
                url=url,
                published_at=published_at,
            )
        )

    return {"items": items, "error_message": None}


def _fetch_us_news(limit: int) -> NewsFetchResult:
    api_key = os.getenv("NEWS_API_KEY", "").strip()
    if not api_key:
        return {"items": [], "error_message": "NEWS_API_KEY is not configured"}

    query = urlencode(
        {
            "category": "business",
            "language": "en",
            "pageSize": limit,
        }
    )
    body = _fetch_url(
        f"{NEWS_API_URL}?{query}",
        headers={"X-Api-Key": api_key},
    )
    payload = json.loads(body.decode("utf-8"))
    if payload.get("status") != "ok":
        message = payload.get("message") or "NewsAPI returned a non-ok status"
        return {"items": [], "error_message": str(message)}

    items: list[NewsItemPayload] = []
    for article in payload.get("articles", [])[:limit]:
        title = (article.get("title") or "").strip()
        if not title:
            continue
        source = ((article.get("source") or {}).get("name") or "NewsAPI").strip()
        url = (article.get("url") or "").strip()
        published_at = article.get("publishedAt")
        if published_at:
            try:
                published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
            except ValueError:
                published_at = str(published_at)
        items.append(_with_sentiment(title=title, source=source, url=url, published_at=published_at))

    return {"items": items, "error_message": None}


def _fetch_news_sync(scope: NewsScope, limit: int) -> NewsFetchResult:
    try:
        if scope == "tw":
            if not _env_enabled("UDN_RSS_ENABLED"):
                return {
                    "items": [],
                    "error_message": "UDN RSS is disabled; set UDN_RSS_ENABLED=true only if your use is authorized",
                }
            return _fetch_tw_news(limit)
        if not _env_enabled("NEWS_API_ENABLED"):
            return {
                "items": [],
                "error_message": "NewsAPI is disabled; set NEWS_API_ENABLED=true with an eligible plan",
            }
        return _fetch_us_news(limit)
    except (ElementTree.ParseError, HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"items": [], "error_message": str(exc)}


async def fetch_news(scope: NewsScope, limit: int = 10) -> NewsFetchResult:
    return await asyncio.to_thread(_fetch_news_sync, scope, limit)
