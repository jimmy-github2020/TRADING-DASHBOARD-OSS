from __future__ import annotations

import math
from typing import Any

import yfinance as yf

from market_quote import YAHOO_SYMBOL_MAP


def fetch_fundamentals(symbol: str) -> dict[str, Any]:
    yahoo_symbol = YAHOO_SYMBOL_MAP.get(symbol, symbol)
    ticker = yf.Ticker(yahoo_symbol)
    info = ticker.info or {}
    cashflow = ticker.cashflow

    price = _as_float(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
    week_low = _as_float(info.get("fiftyTwoWeekLow"))
    week_high = _as_float(info.get("fiftyTwoWeekHigh"))
    week52_pos = _calculate_52w_position(price, week_low, week_high)
    free_cash_flow = _calculate_free_cash_flow(cashflow)
    market_cap = _as_float(info.get("marketCap"))
    roe = _ratio_to_percent(info.get("returnOnEquity"))
    gross_margin = _ratio_to_percent(info.get("grossMargins"))
    operating_margin = _ratio_to_percent(info.get("operatingMargins"))
    pe = _as_float(info.get("trailingPE"))
    pb = _as_float(info.get("priceToBook"))
    free_cash_flow_yield = _safe_percent(free_cash_flow, market_cap)
    revenue_growth = _ratio_to_percent(info.get("revenueGrowth"))
    earnings_growth = _ratio_to_percent(info.get("earningsQuarterlyGrowth"))
    current_ratio = _as_float(info.get("currentRatio"))
    debt_to_equity = _as_float(info.get("debtToEquity"))

    return {
        "symbol": symbol,
        "yahoo_symbol": yahoo_symbol,
        "name": info.get("shortName") or info.get("longName") or symbol,
        "currency": info.get("currency"),
        "price": price,
        "pe": pe,
        "forward_pe": _as_float(info.get("forwardPE")),
        "peg": _as_float(info.get("pegRatio")),
        "pb": pb,
        "ps": _as_float(info.get("priceToSalesTrailing12Months")),
        "ev_to_ebitda": _as_float(info.get("enterpriseToEbitda")),
        "eps_ttm": _as_float(info.get("trailingEps")),
        "forward_eps": _as_float(info.get("forwardEps")),
        "roe": roe,
        "roa": _ratio_to_percent(info.get("returnOnAssets")),
        "gross_margin": gross_margin,
        "operating_margin": operating_margin,
        "revenue_growth_yoy": revenue_growth,
        "eps_growth_yoy": earnings_growth,
        "current_ratio": current_ratio,
        "debt_to_equity": debt_to_equity,
        "dividend_rate": _as_float(info.get("dividendRate")),
        "dividend_yield": _yield_to_percent(info.get("dividendYield")),
        "ex_dividend_date": _unix_to_iso_date(info.get("exDividendDate")),
        "payout_ratio": _ratio_to_percent(info.get("payoutRatio")),
        "beta": _as_float(info.get("beta")),
        "market_cap": market_cap,
        "float_shares": _as_float(info.get("floatShares")),
        "shares_outstanding": _as_float(info.get("sharesOutstanding")),
        "free_cash_flow": free_cash_flow,
        "free_cash_flow_yield": free_cash_flow_yield,
        "week_52_high": week_high,
        "week_52_low": week_low,
        "week_52_position": week52_pos,
        "distance_from_52w_high": _distance_from_high(price, week_high),
        "distance_from_52w_low": _distance_from_low(price, week_low),
        "target_price_mean": _as_float(info.get("targetMeanPrice")),
        "target_price_high": _as_float(info.get("targetHighPrice")),
        "target_price_low": _as_float(info.get("targetLowPrice")),
        "recommendation": info.get("recommendationKey"),
        "analyst_count": _as_float(info.get("numberOfAnalystOpinions")),
        "bos_scores": _calculate_bos_scores(
            roe=roe,
            gross_margin=gross_margin,
            operating_margin=operating_margin,
            revenue_growth=revenue_growth,
            earnings_growth=earnings_growth,
            pe=pe,
            pb=pb,
            free_cash_flow_yield=free_cash_flow_yield,
            current_ratio=current_ratio,
            debt_to_equity=debt_to_equity,
            week52_position=week52_pos,
        ),
        "source": "yfinance",
    }


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _ratio_to_percent(value: Any) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    return number * 100


def _yield_to_percent(value: Any) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    return number if abs(number) > 0.5 else number * 100


def _safe_percent(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * 100


def _calculate_52w_position(price: float | None, low: float | None, high: float | None) -> float | None:
    if price is None or low is None or high is None or high == low:
        return None
    position = (price - low) / (high - low) * 100
    return max(0, min(100, position))


def _distance_from_high(price: float | None, high: float | None) -> float | None:
    if price is None or high in (None, 0):
        return None
    return (price - high) / high * 100


def _distance_from_low(price: float | None, low: float | None) -> float | None:
    if price is None or low in (None, 0):
        return None
    return (price - low) / low * 100


def _calculate_free_cash_flow(cashflow: Any) -> float | None:
    if cashflow is None or getattr(cashflow, "empty", True):
        return None
    latest_column = cashflow.columns[0]
    if "Free Cash Flow" in cashflow.index:
        return _as_float(cashflow.loc["Free Cash Flow", latest_column])

    operating_cash_flow = _as_float(_row_value(cashflow, "Operating Cash Flow", latest_column))
    capex = _as_float(_row_value(cashflow, "Capital Expenditure", latest_column))
    if operating_cash_flow is None or capex is None:
        return None
    return operating_cash_flow + capex


def _calculate_bos_scores(
    *,
    roe: float | None,
    gross_margin: float | None,
    operating_margin: float | None,
    revenue_growth: float | None,
    earnings_growth: float | None,
    pe: float | None,
    pb: float | None,
    free_cash_flow_yield: float | None,
    current_ratio: float | None,
    debt_to_equity: float | None,
    week52_position: float | None,
) -> dict[str, float]:
    profitability = _weighted_average(
        [
            (_score_positive(roe, target=30), 0.4),
            (_score_positive(gross_margin, target=60), 0.3),
            (_score_positive(operating_margin, target=40), 0.3),
        ],
        fallback=5,
    )
    growth = _weighted_average(
        [
            (_score_positive(earnings_growth, target=30), 0.55),
            (_score_positive(revenue_growth, target=25), 0.45),
        ],
        fallback=5,
    )
    value = _weighted_average(
        [
            (_score_inverse(pe, good=10, bad=60), 0.4),
            (_score_inverse(pb, good=1.2, bad=12), 0.3),
            (_score_positive(free_cash_flow_yield, target=8), 0.3),
        ],
        fallback=5,
    )
    financial = _weighted_average(
        [
            (_score_range(current_ratio, low=0.8, high=2.5), 0.45),
            (_score_inverse(debt_to_equity, good=30, bad=200), 0.55),
        ],
        fallback=5,
    )
    momentum = _weighted_average(
        [
            (_score_positive(week52_position, target=100), 1),
        ],
        fallback=5,
    )

    return {
        "profitability": round(profitability, 1),
        "growth": round(growth, 1),
        "value": round(value, 1),
        "financial": round(financial, 1),
        "momentum": round(momentum, 1),
    }


def _score_positive(value: float | None, *, target: float) -> float | None:
    if value is None:
        return None
    if target == 0:
        return None
    return max(0, min(10, value / target * 10))


def _score_inverse(value: float | None, *, good: float, bad: float) -> float | None:
    if value is None or bad == good:
        return None
    if value <= good:
        return 10
    if value >= bad:
        return 0
    return max(0, min(10, (bad - value) / (bad - good) * 10))


def _score_range(value: float | None, *, low: float, high: float) -> float | None:
    if value is None or high == low:
        return None
    return max(0, min(10, (value - low) / (high - low) * 10))


def _weighted_average(values: list[tuple[float | None, float]], *, fallback: float) -> float:
    present = [(score, weight) for score, weight in values if score is not None]
    if not present:
        return fallback
    weight_sum = sum(weight for _, weight in present)
    if weight_sum == 0:
        return fallback
    return sum(score * weight for score, weight in present) / weight_sum


def _row_value(table: Any, row_name: str, column: Any) -> Any:
    if row_name not in table.index:
        return None
    return table.loc[row_name, column]


def _unix_to_iso_date(value: Any) -> str | None:
    number = _as_float(value)
    if number is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(number, tz=timezone.utc).date().isoformat()
