from __future__ import annotations

from importlib.util import find_spec
import sys
from types import ModuleType
import unittest

if "psycopg" not in sys.modules and find_spec("psycopg") is None:
    psycopg_stub = ModuleType("psycopg")
    psycopg_stub.connect = None
    psycopg_stub.Connection = object
    sys.modules["psycopg"] = psycopg_stub
if "requests" not in sys.modules and find_spec("requests") is None:
    requests_stub = ModuleType("requests")
    requests_stub.Session = object
    sys.modules["requests"] = requests_stub
if "pandas" not in sys.modules and find_spec("pandas") is None:
    pandas_stub = ModuleType("pandas")
    pandas_stub.DataFrame = object
    pandas_stub.MultiIndex = object
    pandas_stub.Series = object
    sys.modules["pandas"] = pandas_stub
if "yfinance" not in sys.modules and find_spec("yfinance") is None:
    sys.modules["yfinance"] = ModuleType("yfinance")
if "redis" not in sys.modules and find_spec("redis") is None:
    redis_stub = ModuleType("redis")
    redis_stub.Redis = object
    sys.modules["redis"] = redis_stub

from ingestion import tracked_instrument_requests


def instrument(symbol: str, tier: str) -> dict[str, str]:
    return {
        "canonical_symbol": symbol,
        "market": "TW",
        "tracking_tier": tier,
        "provider": "yfinance",
        "provider_symbol": f"{symbol}.TW",
    }


class TrackingTierRequestTest(unittest.TestCase):
    def test_catalog_never_creates_market_request(self) -> None:
        rows = [instrument("2330", "catalog")]
        self.assertEqual(tracked_instrument_requests(rows, "quote"), [])
        self.assertEqual(tracked_instrument_requests(rows, "daily"), [])
        self.assertEqual(tracked_instrument_requests(rows, "intraday"), [])

    def test_quote_only_creates_short_daily_snapshot(self) -> None:
        request = tracked_instrument_requests([instrument("2330", "quote")], "quote")[0]
        self.assertEqual((request.timeframe, request.period, request.limit), ("1d", "5d", 5))
        self.assertEqual(tracked_instrument_requests([instrument("2330", "quote")], "daily"), [])

    def test_daily_and_intraday_costs_are_separate(self) -> None:
        daily = tracked_instrument_requests([instrument("2330", "daily")], "daily")[0]
        intraday = tracked_instrument_requests([instrument("2330", "intraday")], "intraday")[0]
        self.assertEqual((daily.timeframe, daily.period, daily.limit), ("1d", "1y", 260))
        self.assertEqual((intraday.timeframe, intraday.period, intraday.limit), ("1h", "60d", 200))

    def test_requests_are_deduplicated(self) -> None:
        rows = [instrument("2330", "quote"), instrument("2330", "quote")]
        self.assertEqual(len(tracked_instrument_requests(rows, "quote")), 1)


if __name__ == "__main__":
    unittest.main()
