from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from services.news_fetcher import _fetch_news_sync


class NewsFetcherOptInTest(unittest.TestCase):
    def test_tw_rss_is_disabled_by_default_without_network_access(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("services.news_fetcher._fetch_tw_news") as fetch_tw,
        ):
            result = _fetch_news_sync("tw", 5)

        self.assertEqual(result["items"], [])
        self.assertIn("disabled", result["error_message"])
        fetch_tw.assert_not_called()

    def test_newsapi_is_disabled_by_default_without_network_access(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("services.news_fetcher._fetch_us_news") as fetch_us,
        ):
            result = _fetch_news_sync("us", 5)

        self.assertEqual(result["items"], [])
        self.assertIn("disabled", result["error_message"])
        fetch_us.assert_not_called()

    def test_explicit_opt_in_calls_the_selected_provider(self) -> None:
        expected = {"items": [], "error_message": None}
        with (
            patch.dict(os.environ, {"UDN_RSS_ENABLED": "true"}, clear=True),
            patch("services.news_fetcher._fetch_tw_news", return_value=expected) as fetch_tw,
        ):
            result = _fetch_news_sync("tw", 3)

        self.assertEqual(result, expected)
        fetch_tw.assert_called_once_with(3)
