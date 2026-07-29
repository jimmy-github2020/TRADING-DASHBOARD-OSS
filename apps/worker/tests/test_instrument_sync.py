from __future__ import annotations

from datetime import datetime, timezone
from importlib.util import find_spec
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock

if "psycopg" not in sys.modules and find_spec("psycopg") is None:
    psycopg_stub = ModuleType("psycopg")
    psycopg_stub.connect = None
    psycopg_stub.Connection = object
    sys.modules["psycopg"] = psycopg_stub
if "requests" not in sys.modules and find_spec("requests") is None:
    requests_stub = ModuleType("requests")
    requests_stub.Session = object
    sys.modules["requests"] = requests_stub

from instrument_sync import TaiwanInstrumentSyncService, normalize_company_rows
from repository import MarketRepository


class TaiwanInstrumentNormalizerTest(unittest.TestCase):
    def test_twse_row_uses_provider_neutral_symbol(self) -> None:
        records = normalize_company_rows(
            [
                {
                    "公司代號": "2330",
                    "公司簡稱": "台積電",
                    "英文簡稱": "TSMC",
                    "產業別": "24",
                    "上市日期": "19940905",
                }
            ],
            "twse",
            datetime(2026, 7, 24, tzinfo=timezone.utc),
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].canonical_symbol, "2330")
        self.assertEqual(records[0].exchange, "TWSE")
        self.assertEqual(
            records[0].provider_symbols,
            (("twse", "2330"), ("yfinance", "2330.TW")),
        )
        self.assertEqual(records[0].listed_at.isoformat(), "1994-09-05")

    def test_tpex_row_uses_yahoo_two_suffix(self) -> None:
        record = normalize_company_rows(
            [
                {
                    "SecuritiesCompanyCode": "6488",
                    "CompanyAbbreviation": "環球晶",
                    "Symbol": "GWC",
                    "SecuritiesIndustryCode": "24",
                    "DateOfListing": "20110923",
                }
            ],
            "tpex",
        )[0]

        self.assertEqual(record.exchange, "TPEx")
        self.assertEqual(record.name_zh, "環球晶")
        self.assertEqual(record.name_en, "GWC")
        self.assertEqual(record.sector, "24")
        self.assertEqual(record.listed_at.isoformat(), "2011-09-23")
        self.assertIn(("yfinance", "6488.TWO"), record.provider_symbols)

    def test_display_name_removes_trailing_market_marker(self) -> None:
        record = normalize_company_rows(
            [{"公司代號": "2327", "公司簡稱": "國巨*", "上市日期": "19930922"}],
            "twse",
        )[0]

        self.assertEqual(record.name_zh, "國巨")

    def test_invalid_rows_and_duplicates_are_filtered(self) -> None:
        records = normalize_company_rows(
            [
                {"公司代號": "", "公司簡稱": "empty"},
                {"公司代號": "not-a-symbol", "公司簡稱": "invalid"},
                {"公司代號": "2330", "公司簡稱": "old"},
                {"公司代號": "2330", "公司簡稱": "new"},
            ],
            "twse",
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name_zh, "new")


class TaiwanInstrumentSyncServiceTest(unittest.TestCase):
    def test_dry_run_fetches_but_does_not_write(self) -> None:
        repository = Mock()
        session = Mock()
        response = Mock()
        response.json.return_value = [{"公司代號": "2330", "公司簡稱": "台積電"}]
        session.get.return_value = response
        service = TaiwanInstrumentSyncService(repository, session=session)

        result = service.sync(source="twse", dry_run=True)[0]

        self.assertEqual(result.status, "dry_run")
        self.assertEqual(result.rows_seen, 1)
        repository.sync_instruments.assert_not_called()

    def test_one_source_failure_does_not_block_the_other(self) -> None:
        repository = Mock()
        repository.sync_instruments.return_value = (1, 0)
        session = Mock()
        failed = Mock()
        failed.raise_for_status.side_effect = RuntimeError("TWSE unavailable")
        success = Mock()
        success.json.return_value = [{"公司代號": "6488", "公司簡稱": "環球晶"}]
        session.get.side_effect = [failed, success]
        service = TaiwanInstrumentSyncService(repository, session=session)

        results = service.sync(source="all")

        self.assertEqual([item.status for item in results], ["failed", "success"])
        repository.record_instrument_sync_failure.assert_called_once()
        repository.sync_instruments.assert_called_once()


class InstrumentProviderMappingTest(unittest.TestCase):
    def test_sync_demotes_previous_primary_before_mapping_upsert(self) -> None:
        repository = MarketRepository("postgresql://example")
        connection = Mock()

        def execute(query: str, params: tuple | None = None) -> Mock:
            result = Mock()
            normalized_query = " ".join(query.split())
            if "INSERT INTO instrument_sync_runs" in normalized_query:
                result.fetchone.return_value = (1,)
            elif "INSERT INTO instruments" in normalized_query:
                result.fetchone.return_value = (50, False)
            return result

        connection.execute.side_effect = execute
        connection_context = Mock()
        connection_context.__enter__ = Mock(return_value=connection)
        connection_context.__exit__ = Mock(return_value=False)
        repository.connect = Mock(return_value=connection_context)
        record = SimpleNamespace(
            canonical_symbol="3357",
            market="TW",
            exchange="TPEx",
            security_type="stock",
            name_zh="臺慶科",
            name_en=None,
            currency="TWD",
            timezone="Asia/Taipei",
            sector="28",
            listed_at=None,
            source="tpex_openapi",
            source_updated_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
            provider_symbols=(("yfinance", "3357.TWO"),),
        )

        repository.sync_instruments("TW", "tpex_openapi", [record])

        queries = [" ".join(call.args[0].split()) for call in connection.execute.call_args_list]
        demote_index = next(
            index
            for index, query in enumerate(queries)
            if query.startswith("UPDATE instrument_provider_symbols")
        )
        upsert_index = next(
            index
            for index, query in enumerate(queries)
            if query.startswith("INSERT INTO instrument_provider_symbols")
        )
        self.assertLess(demote_index, upsert_index)
        self.assertEqual(
            connection.execute.call_args_list[demote_index].args[1],
            (50, "yfinance", "3357.TWO"),
        )


if __name__ == "__main__":
    unittest.main()
