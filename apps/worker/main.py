import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from cache import QuoteCache
from config import load_settings
from ingestion import (
    IngestionRequest,
    MarketIngestionService,
    all_symbol_requests,
    default_requests,
    tracked_instrument_requests,
)
from instrument_sync import TaiwanInstrumentSyncService
from notifications import NotificationService
from quant import StrategyScanner
from repository import MarketRepository
from scheduler import register_instrument_sync_jobs, register_telegram_jobs
from telegram.jobs import closing_report_job, midday_flash_job, morning_brief_job
from telegram.jobs import (
    fear_greed_alert_job,
    market_alert_rules_job,
    price_alert_job,
    technical_signal_job,
    twii_alert_job,
    vix_alert_job,
)
from us_instrument_sync import UsInstrumentSyncService


READY_FILE = Path("/tmp/worker-ready")
running = True


def _dedupe_requests(requests: list[IngestionRequest]) -> list[IngestionRequest]:
    unique: dict[tuple[str, str, str], IngestionRequest] = {}
    for request in requests:
        key = (request.provider, request.symbol, request.timeframe)
        current = unique.get(key)
        if current is None or (request.limit or 0) > (current.limit or 0):
            unique[key] = request
    return list(unique.values())


def heartbeat() -> None:
    READY_FILE.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")


def handle_shutdown(*_: object) -> None:
    global running
    running = False


def build_service() -> MarketIngestionService:
    settings = load_settings()
    return MarketIngestionService(
        repository=MarketRepository(settings.database_url),
        cache=QuoteCache(settings.redis_url),
    )


def build_notification_service() -> NotificationService:
    settings = load_settings()
    return NotificationService(
        repository=MarketRepository(settings.database_url),
        settings=settings,
    )


def build_strategy_scanner() -> StrategyScanner:
    settings = load_settings()
    return StrategyScanner(repository=MarketRepository(settings.database_url))


def build_instrument_sync_service() -> TaiwanInstrumentSyncService:
    settings = load_settings()
    return TaiwanInstrumentSyncService(
        repository=MarketRepository(settings.database_url),
    )


def build_us_instrument_sync_service() -> UsInstrumentSyncService:
    settings = load_settings()
    return UsInstrumentSyncService(
        repository=MarketRepository(settings.database_url),
    )


def run_once(args: argparse.Namespace) -> None:
    service = build_service()
    if args.all_symbols:
        summaries = service.ingest_many(
            all_symbol_requests(args.timeframe, period=args.period, limit=args.limit)
        )
        print(
            "[ingestion:run-once-all] "
            f"timeframe={args.timeframe} limit={args.limit or 200} success_count={len(summaries)}"
        )
        return

    if not args.provider or not args.symbol:
        raise SystemExit("run-once requires --provider and --symbol unless --all-symbols is used")

    request = IngestionRequest(
        provider=args.provider,
        symbol=args.symbol,
        timeframe=args.timeframe,
        period=args.period,
        limit=args.limit,
    )
    summary = service.ingest(request)
    print(
        "[ingestion:success] "
        f"provider={summary.provider} symbol={summary.symbol} "
        f"timeframe={summary.timeframe} rows_seen={summary.rows_seen} "
        f"rows_inserted={summary.rows_inserted} rows_updated={summary.rows_updated}"
    )


def run_batch(args: argparse.Namespace) -> None:
    service = build_service()
    summaries = service.ingest_many(default_requests(args.mode))
    print(f"[ingestion:batch] mode={args.mode} success_count={len(summaries)}")


def notify_scan(args: argparse.Namespace) -> None:
    service = build_notification_service()
    result = service.scan_and_notify(
        timeframe=args.timeframe,
        limit=args.limit,
        dry_run=not args.send,
    )
    print(
        "[notification:scan] "
        f"scanned_symbols={result.scanned_symbols} "
        f"triggered_events={result.triggered_events} "
        f"delivered_events={result.delivered_events} "
        f"skipped_cooldown={result.skipped_cooldown} "
        f"dry_run={result.dry_run}"
    )


def telegram_smoke(args: argparse.Namespace) -> None:
    service = build_notification_service()
    status, error = service.send_telegram_smoke_test(dry_run=not args.send)
    print(
        "[notification:telegram-smoke] "
        f"status={status} "
        f"dry_run={not args.send} "
        f"error={error or ''}"
    )


def telegram_job(args: argparse.Namespace) -> None:
    settings = load_settings()
    if args.send:
        settings = replace(settings, notification_dry_run=False)
    elif args.dry_run:
        settings = replace(settings, notification_dry_run=True)

    jobs = {
        "morning": morning_brief_job,
        "midday": midday_flash_job,
        "closing": closing_report_job,
    }
    result = jobs[args.job](settings)
    print(
        "[notification:telegram-job] "
        f"job={args.job} "
        f"mode={'send' if args.send else 'dry-run'} "
        f"status={result.status} "
        f"targets_scanned={result.targets_scanned} "
        f"disabled_skipped_count={result.disabled_skipped_count} "
        f"frequency_skipped_count={result.frequency_skipped_count} "
        f"sent_count={result.sent_count} "
        f"dedup_skipped_count={result.dedup_skipped_count} "
        f"error_count={result.error_count} "
        f"error={result.error or ''}"
    )


def alert_check(args: argparse.Namespace) -> None:
    settings = load_settings()
    if args.send:
        settings = replace(settings, notification_dry_run=False)
    elif args.dry_run:
        settings = replace(settings, notification_dry_run=True)

    jobs = {
        "market-rules": market_alert_rules_job,
        "twii": twii_alert_job,
        "vix": vix_alert_job,
        "fg": fear_greed_alert_job,
        "price": price_alert_job,
        "signal": technical_signal_job,
    }
    if args.alert == "all":
        selected = jobs.keys()
    elif args.alert == "market":
        selected = ["market-rules"]
    else:
        selected = [args.alert]
    for alert_name in selected:
        result = jobs[alert_name](settings)
        print(
            "[notification:alert-check] "
            f"alert={alert_name} "
            f"mode={'send' if args.send else 'dry-run'} "
            f"status={result.status} "
            f"alerts_scanned={result.scanned_count} "
            f"targets_scanned={result.targets_scanned} "
            f"disabled_skipped_count={result.disabled_skipped_count} "
            f"frequency_skipped_count={result.frequency_skipped_count} "
            f"triggered_count={result.triggered_count} "
            f"sent_count={result.sent_count} "
            f"dedup_skipped_count={result.dedup_skipped_count} "
            f"error_count={result.error_count} "
            f"error={result.error or ''}"
        )


def strategy_scan(args: argparse.Namespace) -> None:
    scanner = build_strategy_scanner()
    result = scanner.scan(timeframe=args.timeframe, limit=args.limit)
    print(
        "[strategy:scan] "
        f"scanned_symbols={result.scanned_symbols} "
        f"scanned_strategies={result.scanned_strategies} "
        f"triggered_signals={result.triggered_signals} "
        f"errors={result.errors}"
    )


def sync_instruments(args: argparse.Namespace) -> None:
    allowed_sources = {
        "tw": {"all", "twse", "tpex"},
        "us": {"all", "nasdaq", "other"},
    }
    if args.source not in allowed_sources[args.market]:
        raise SystemExit(
            f"source={args.source} is not valid for market={args.market}"
        )
    service = (
        build_instrument_sync_service()
        if args.market == "tw"
        else build_us_instrument_sync_service()
    )
    results = service.sync(
        source=args.source,
        dry_run=args.dry_run,
    )
    for result in results:
        print(
            "[instrument-sync] "
            f"market={args.market.upper()} source={result.source} status={result.status} "
            f"rows_seen={result.rows_seen} rows_inserted={result.rows_inserted} "
            f"rows_updated={result.rows_updated} error_count={result.error_count} "
            f"message={result.message or ''}"
        )


async def scheduler_main() -> None:
    settings = load_settings()
    service = build_service()

    def refresh_snapshots() -> None:
        tracked = service.repository.fetch_tracked_instruments()
        requests = [
            *default_requests("snapshot"),
            *tracked_instrument_requests(tracked, "quote"),
            *tracked_instrument_requests(tracked, "intraday"),
        ]
        summaries = service.ingest_many(_dedupe_requests(requests))
        print(
            f"[scheduler:snapshot] tracked_count={len(tracked)} "
            f"success_count={len(summaries)}"
        )

    def refresh_daily() -> None:
        tracked = service.repository.fetch_tracked_instruments()
        requests = [
            *default_requests("daily"),
            *tracked_instrument_requests(tracked, "daily"),
        ]
        summaries = service.ingest_many(_dedupe_requests(requests))
        print(
            f"[scheduler:daily] tracked_count={len(tracked)} "
            f"success_count={len(summaries)}"
        )

    def scan_notifications() -> None:
        result = build_notification_service().scan_and_notify(timeframe="1d", limit=200)
        print(
            "[scheduler:notification] "
            f"triggered_events={result.triggered_events} "
            f"delivered_events={result.delivered_events} "
            f"dry_run={result.dry_run}"
        )

    def scan_strategies() -> None:
        result = build_strategy_scanner().scan(timeframe="1d", limit=120)
        print(
            "[scheduler:strategy] "
            f"scanned_symbols={result.scanned_symbols} "
            f"scanned_strategies={result.scanned_strategies} "
            f"triggered_signals={result.triggered_signals} "
            f"errors={result.errors}"
        )

    def sync_taiwan_instruments() -> None:
        results = build_instrument_sync_service().sync(source="all", dry_run=False)
        for result in results:
            print(
                "[scheduler:instrument-sync] "
                f"source={result.source} status={result.status} "
                f"rows_seen={result.rows_seen} rows_inserted={result.rows_inserted} "
                f"rows_updated={result.rows_updated} error_count={result.error_count}"
            )

    def sync_us_instruments() -> None:
        results = build_us_instrument_sync_service().sync(source="all", dry_run=False)
        for result in results:
            print(
                "[scheduler:instrument-sync] "
                f"market=US source={result.source} status={result.status} "
                f"rows_seen={result.rows_seen} rows_inserted={result.rows_inserted} "
                f"rows_updated={result.rows_updated} error_count={result.error_count}"
            )

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
    scheduler.add_job(heartbeat, "interval", seconds=30, id="heartbeat")
    if settings.worker_automation_enabled:
        scheduler.add_job(
            refresh_snapshots,
            "interval",
            minutes=settings.quote_refresh_minutes,
            id="refresh_snapshots",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            scan_strategies,
            "interval",
            minutes=15,
            id="scan_strategies",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            refresh_daily,
            "cron",
            hour=settings.daily_refresh_hour_utc,
            minute=0,
            id="refresh_daily",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            scan_notifications,
            "cron",
            hour=22,
            minute=0,
            id="scan_notifications",
            max_instances=1,
            coalesce=True,
        )
        register_telegram_jobs(scheduler)
        register_instrument_sync_jobs(
            scheduler,
            sync_taiwan_instruments,
            sync_us_instruments,
        )
    scheduler.start()
    print("[scheduler] timezone=Asia/Taipei")
    if settings.worker_automation_enabled:
        print("[scheduler] automation enabled")
        print("[scheduler] telegram and instrument sync jobs registered")
    else:
        print(
            "[scheduler] automation disabled; "
            "set WORKER_AUTOMATION_ENABLED=true to register background jobs"
        )
    heartbeat()

    try:
        while running:
            await asyncio.sleep(1)
    finally:
        scheduler.shutdown(wait=False)
        READY_FILE.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trading Dashboard worker")
    subparsers = parser.add_subparsers(dest="command")

    run_once_parser = subparsers.add_parser("run-once", help="Ingest one symbol/timeframe")
    run_once_parser.add_argument("--provider", choices=["yfinance", "binance"])
    run_once_parser.add_argument("--symbol")
    run_once_parser.add_argument("--all-symbols", action="store_true")
    run_once_parser.add_argument("--timeframe", required=True, choices=["1d", "1h"])
    run_once_parser.add_argument("--period")
    run_once_parser.add_argument("--limit", type=int, default=200)
    run_once_parser.set_defaults(func=run_once)

    run_batch_parser = subparsers.add_parser("run-batch", help="Ingest the default universe")
    run_batch_parser.add_argument("--mode", choices=["snapshot", "daily"], default="snapshot")
    run_batch_parser.set_defaults(func=run_batch)

    notify_parser = subparsers.add_parser("notify-scan", help="Scan signals and send notifications")
    notify_parser.add_argument("--timeframe", choices=["1d", "1h"], default="1d")
    notify_parser.add_argument("--limit", type=int, default=200)
    notify_parser.add_argument("--dry-run", action="store_true", help="Keep dry-run mode (default)")
    notify_parser.add_argument("--send", action="store_true", help="Send real notifications")
    notify_parser.set_defaults(func=notify_scan)

    smoke_parser = subparsers.add_parser("telegram-smoke", help="Send one Telegram smoke-test message")
    smoke_parser.add_argument("--dry-run", action="store_true", help="Keep dry-run mode (default)")
    smoke_parser.add_argument("--send", action="store_true", help="Send a real Telegram smoke-test message")
    smoke_parser.set_defaults(func=telegram_smoke)

    telegram_job_parser = subparsers.add_parser("telegram-job", help="Run one scheduled Telegram job now")
    telegram_job_parser.add_argument("job", choices=["morning", "midday", "closing"])
    telegram_job_parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode")
    telegram_job_parser.add_argument("--send", action="store_true", help="Force real Telegram delivery")
    telegram_job_parser.set_defaults(func=telegram_job)

    alert_parser = subparsers.add_parser("alert-check", help="Run Telegram market alert checks now")
    alert_parser.add_argument("alert", choices=["all", "market", "twii", "vix", "fg", "price", "signal"])
    alert_parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode")
    alert_parser.add_argument("--send", action="store_true", help="Force real Telegram delivery")
    alert_parser.set_defaults(func=alert_check)

    strategy_parser = subparsers.add_parser("strategy-scan", help="Scan active quant strategies")
    strategy_parser.add_argument("--timeframe", choices=["1d", "1h"], default="1d")
    strategy_parser.add_argument("--limit", type=int, default=120)
    strategy_parser.set_defaults(func=strategy_scan)

    instrument_parser = subparsers.add_parser(
        "sync-instruments",
        help="Synchronize the Taiwan listed-company catalog",
    )
    instrument_parser.add_argument(
        "--market",
        choices=["tw", "us"],
        default="tw",
    )
    instrument_parser.add_argument(
        "--source",
        choices=["all", "twse", "tpex", "nasdaq", "other"],
        default="all",
    )
    instrument_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and normalize without writing to PostgreSQL",
    )
    instrument_parser.set_defaults(func=sync_instruments)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        asyncio.run(scheduler_main())


if __name__ == "__main__":
    main()
