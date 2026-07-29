from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram.jobs import (
    closing_report_job,
    market_alert_rules_job,
    midday_flash_job,
    morning_brief_job,
    price_alert_job,
    technical_signal_job,
)


def register_telegram_jobs(scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(
        morning_brief_job,
        "cron",
        hour=8,
        minute=30,
        id="telegram_morning_brief",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        midday_flash_job,
        "cron",
        hour=12,
        minute=0,
        id="telegram_midday_flash",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        closing_report_job,
        "cron",
        hour=13,
        minute=45,
        id="telegram_closing_report",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        market_alert_rules_job,
        "interval",
        minutes=15,
        id="telegram_alert_market_rules",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        price_alert_job,
        "cron",
        day_of_week="mon-fri",
        hour="9-13",
        minute="*/5",
        id="telegram_alert_price",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        technical_signal_job,
        "interval",
        minutes=60,
        id="telegram_alert_technical_signal",
        max_instances=1,
        coalesce=True,
    )


def register_instrument_sync_jobs(
    scheduler: AsyncIOScheduler,
    sync_taiwan_instruments: Callable[[], None],
    sync_us_instruments: Callable[[], None],
) -> None:
    scheduler.add_job(
        sync_taiwan_instruments,
        "cron",
        day_of_week="mon-fri",
        hour=18,
        minute=30,
        id="sync_taiwan_instruments",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        sync_us_instruments,
        "cron",
        day_of_week="tue-sat",
        hour=7,
        minute=30,
        id="sync_us_instruments",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
