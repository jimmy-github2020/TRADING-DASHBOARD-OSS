from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from config import load_settings


class WorkerSettingsTest(unittest.TestCase):
    def test_background_automation_is_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()

        self.assertFalse(settings.worker_automation_enabled)
        self.assertFalse(settings.enable_live_trading)
        self.assertTrue(settings.notification_dry_run)

    def test_background_automation_requires_explicit_opt_in(self) -> None:
        with patch.dict(
            os.environ,
            {"WORKER_AUTOMATION_ENABLED": "true"},
            clear=True,
        ):
            settings = load_settings()

        self.assertTrue(settings.worker_automation_enabled)
