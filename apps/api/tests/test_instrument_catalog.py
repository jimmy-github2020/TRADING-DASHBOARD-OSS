from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from importlib.util import find_spec
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

if find_spec("asyncpg") is None:
    sys.modules["asyncpg"] = SimpleNamespace(connect=None)

from services.instrument_catalog import (
    InstrumentCatalogRepository,
    _build_filters,
    _serialize_instrument,
)


class InstrumentCatalogHelpersTest(unittest.TestCase):
    def test_build_filters_keeps_parameter_positions_stable(self) -> None:
        filters, values = _build_filters(
            query="台積",
            market="TW",
            exchange=None,
            security_type="stock",
            active_only=True,
        )

        self.assertEqual(values, ["台積", "TW", "stock"])
        self.assertIn("$1", filters[0])
        self.assertEqual(filters[1], "LOWER(i.market) = LOWER($2)")
        self.assertEqual(filters[2], "LOWER(i.security_type) = LOWER($3)")
        self.assertEqual(filters[3], "i.is_active = true")

    def test_build_filters_can_include_inactive_instruments(self) -> None:
        filters, values = _build_filters(
            query=None,
            market=None,
            exchange=None,
            security_type=None,
            active_only=False,
        )

        self.assertEqual(filters, [])
        self.assertEqual(values, [])

    def test_serialize_instrument_parses_jsonb_text_and_dates(self) -> None:
        row = {
            "id": 1,
            "listed_at": date(2020, 1, 2),
            "source_updated_at": datetime(2026, 7, 24, 8, 30, tzinfo=timezone.utc),
            "provider_symbols": (
                '[{"provider":"yfinance","symbol":"2330.TW",'
                '"is_primary":true,"is_active":true}]'
            ),
        }

        result = _serialize_instrument(row)

        self.assertEqual(result["listed_at"], "2020-01-02")
        self.assertEqual(result["source_updated_at"], "2026-07-24T08:30:00+00:00")
        self.assertEqual(result["provider_symbols"][0]["symbol"], "2330.TW")


class InstrumentCatalogRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_list_instruments_returns_total_and_serialized_mappings(self) -> None:
        connection = AsyncMock()
        connection.fetchval.return_value = 1
        connection.fetch.return_value = [
            {
                "id": 1,
                "canonical_symbol": "2330",
                "market": "TW",
                "provider_symbols": (
                    '[{"provider":"yfinance","symbol":"2330.TW",'
                    '"is_primary":true,"is_active":true}]'
                ),
            }
        ]

        with patch(
            "services.instrument_catalog.asyncpg.connect",
            new=AsyncMock(return_value=connection),
        ):
            items, total = await InstrumentCatalogRepository(
                "postgresql://example"
            ).list_instruments(
                query="2330",
                market="TW",
                limit=25,
                offset=50,
            )

        self.assertEqual(total, 1)
        self.assertEqual(items[0]["provider_symbols"][0]["symbol"], "2330.TW")
        fetch_args = connection.fetch.await_args.args
        self.assertEqual(fetch_args[-4:], ("2330", "TW", 25, 50))
        connection.close.assert_awaited_once()

    async def test_catalog_stats_projects_storage_by_effective_tier(self) -> None:
        connection = AsyncMock()
        connection.fetch.side_effect = [
            [{"market": "TW", "security_type": "stock", "count": 1000}],
            [
                {"tracking_tier": "quote", "count": 10},
                {"tracking_tier": "daily", "count": 2},
                {"tracking_tier": "intraday", "count": 1},
            ],
            [],
        ]
        connection.fetchrow.return_value = {
            "catalog_bytes": 1024,
            "ohlcv_bytes": 2048,
        }
        with patch(
            "services.instrument_catalog.asyncpg.connect",
            new=AsyncMock(return_value=connection),
        ):
            stats = await InstrumentCatalogRepository(
                "postgresql://example"
            ).get_catalog_stats()

        self.assertEqual(stats["storage"]["projected_tracked_rows"], 1030)
        self.assertEqual(stats["storage"]["projected_bytes_conservative"], 1030 * 768)
        self.assertEqual(stats["tracking_tiers"]["intraday"], 1)


if __name__ == "__main__":
    unittest.main()
