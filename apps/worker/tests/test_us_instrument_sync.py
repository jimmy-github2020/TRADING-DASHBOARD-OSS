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

from us_instrument_sync import (
    infer_security_type,
    normalize_symbol_directory,
    to_yfinance_symbol,
)


NASDAQ_SAMPLE = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N
QQQ|Invesco QQQ Trust, Series 1|G|N|N|100|Y|N
ZTEST|NASDAQ TEST STOCK|Q|Y|N|100|N|N
File Creation Time: 0724202621:32|||||||
"""

OTHER_SAMPLE = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.B|Berkshire Hathaway Inc. Class B|N|BRK.B|N|100|N|BRK.B
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
File Creation Time: 0724202621:32|||||||
"""


class UsInstrumentNormalizerTest(unittest.TestCase):
    def test_nasdaq_directory_filters_test_issues(self) -> None:
        records = normalize_symbol_directory(NASDAQ_SAMPLE, "nasdaq")

        self.assertEqual([item.canonical_symbol for item in records], ["AAPL", "QQQ"])
        self.assertEqual(records[1].security_type, "etf")
        self.assertEqual(records[0].exchange, "NASDAQ")

    def test_other_directory_maps_exchange_and_yahoo_symbol(self) -> None:
        records = normalize_symbol_directory(OTHER_SAMPLE, "other")
        berkshire = records[0]

        self.assertEqual(berkshire.canonical_symbol, "BRK.B")
        self.assertEqual(berkshire.exchange, "NYSE")
        self.assertIn(("yfinance", "BRK-B"), berkshire.provider_symbols)

    def test_symbol_transform_is_provider_specific(self) -> None:
        self.assertEqual(to_yfinance_symbol("BRK.B"), "BRK-B")
        self.assertEqual(to_yfinance_symbol("ABC/A"), "ABC-A")

    def test_security_type_inference(self) -> None:
        self.assertEqual(infer_security_type("Example Warrant", False), "warrant")
        self.assertEqual(infer_security_type("Example Preferred Stock", False), "preferred")
        self.assertEqual(infer_security_type("Example", True), "etf")


if __name__ == "__main__":
    unittest.main()
