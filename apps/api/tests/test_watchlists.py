from __future__ import annotations

import unittest
from importlib.util import find_spec
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

if "asyncpg" not in sys.modules and find_spec("asyncpg") is None:
    sys.modules["asyncpg"] = SimpleNamespace(connect=None)

from services.watchlists import WatchlistRepository, slugify_watchlist


class WatchlistHelpersTest(unittest.TestCase):
    def test_slugify_uses_stable_ascii_slug(self) -> None:
        self.assertEqual(slugify_watchlist("US Growth Stocks"), "us-growth-stocks")
        self.assertTrue(slugify_watchlist("台股觀察").startswith("list-"))


class WatchlistRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_list_watchlists_serializes_counts(self) -> None:
        connection = AsyncMock()
        connection.fetch.return_value = [
            {
                "id": 1,
                "name": "Default",
                "slug": "default",
                "is_default": True,
                "item_count": 3,
            }
        ]
        with patch(
            "services.watchlists.asyncpg.connect",
            new=AsyncMock(return_value=connection),
        ):
            result = await WatchlistRepository("postgresql://example").list_watchlists()

        self.assertEqual(result[0]["item_count"], 3)
        connection.close.assert_awaited_once()

    async def test_remove_item_reports_missing_row(self) -> None:
        connection = AsyncMock()
        connection.execute.return_value = "DELETE 0"
        with patch(
            "services.watchlists.asyncpg.connect",
            new=AsyncMock(return_value=connection),
        ):
            removed = await WatchlistRepository("postgresql://example").remove_item(
                watchlist_id=1,
                item_id=99,
            )
        self.assertFalse(removed)


if __name__ == "__main__":
    unittest.main()
