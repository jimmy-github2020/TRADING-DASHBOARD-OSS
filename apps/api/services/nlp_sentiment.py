from __future__ import annotations

from typing import Literal, TypedDict

SentimentLabel = Literal["positive", "neutral", "negative"]


class SentimentResult(TypedDict):
    sentiment: SentimentLabel
    sentiment_score: float


POSITIVE_WORDS = (
    "beat",
    "growth",
    "rally",
    "upgrade",
    "bullish",
    "breakout",
    "surge",
    "上漲",
    "突破",
    "買超",
    "強勢",
    "創高",
    "反彈",
    "走強",
    "多頭",
    "看漲",
    "獲利",
    "利多",
    "升息受惠",
    "大漲",
    "漲停",
    "買進",
    "加碼",
)

NEGATIVE_WORDS = (
    "miss",
    "cut",
    "risk",
    "inflation",
    "selloff",
    "downgrade",
    "crash",
    "recession",
    "下跌",
    "賣超",
    "崩跌",
    "衰退",
    "虧損",
    "跌破",
    "走弱",
    "空頭",
    "看跌",
    "利空",
    "降評",
    "大跌",
    "跌停",
    "賣出",
    "減碼",
    "警示",
    "恐慌",
)


def _count_keywords(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword.lower() in text)


def analyze_headline_sentiment(headline: str) -> SentimentResult:
    """Return a lightweight keyword-based sentiment score for a news headline."""
    normalized = headline.lower()
    positive_hits = _count_keywords(normalized, POSITIVE_WORDS)
    negative_hits = _count_keywords(normalized, NEGATIVE_WORDS)
    sentiment_score = max(min((positive_hits * 0.2) - (negative_hits * 0.2), 1.0), -1.0)

    if sentiment_score > 0.05:
        sentiment: SentimentLabel = "positive"
    elif sentiment_score < -0.05:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return {"sentiment": sentiment, "sentiment_score": round(sentiment_score, 4)}
