from __future__ import annotations

from dataclasses import dataclass
from html import escape
import time
import requests

from config import Settings
from models import SignalEvent
from repository import MarketRepository
from universe import ALL_SYMBOLS
from signals import scan_signal_events


@dataclass(frozen=True)
class NotificationResult:
    scanned_symbols: int
    triggered_events: int
    delivered_events: int
    skipped_cooldown: int
    dry_run: bool


class NotificationService:
    TELEGRAM_RETRY_DELAYS = (2, 5, 10)

    def __init__(self, repository: MarketRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def scan_and_notify(
        self,
        timeframe: str = "1d",
        limit: int = 200,
        dry_run: bool | None = None,
    ) -> NotificationResult:
        should_dry_run = self.settings.notification_dry_run if dry_run is None else dry_run
        triggered = 0
        delivered = 0
        skipped = 0

        with self.repository.connect() as conn:
            for spec in ALL_SYMBOLS:
                candles = self.repository.fetch_recent_candles(
                    conn,
                    spec.provider,
                    spec.symbol,
                    timeframe,
                    limit,
                )
                events = scan_signal_events(candles)
                triggered += len(events)

                for event in events:
                    if self.repository.is_notification_in_cooldown(
                        conn,
                        event,
                        self.settings.notification_cooldown_hours,
                    ):
                        skipped += 1
                        continue

                    for channel in ("line", "telegram"):
                        status, error = self._deliver(event, channel, should_dry_run)
                        self.repository.record_notification_event(
                            conn,
                            event,
                            channel,
                            status,
                            error_message=error,
                        )
                        if status in ("sent", "dry_run"):
                            delivered += 1
                conn.commit()

        return NotificationResult(
            scanned_symbols=len(ALL_SYMBOLS),
            triggered_events=triggered,
            delivered_events=delivered,
            skipped_cooldown=skipped,
            dry_run=should_dry_run,
        )

    def send_telegram_smoke_test(self, dry_run: bool = True) -> tuple[str, str | None]:
        event = SignalEvent(
            event_type="smoke_test",
            symbol="SYSTEM",
            provider="telegram",
            timeframe="manual",
            title="Trading Dashboard Telegram 測試通知",
            message="🤖 Trading Dashboard Telegram 測試通知\n系統連線正常。",
            payload={"source": "telegram_smoke_test"},
        )
        status, error = self._deliver(event, "telegram", dry_run)
        with self.repository.connect() as conn:
            self.repository.record_notification_event(
                conn,
                event,
                "telegram",
                status,
                error_message=error,
            )
            conn.commit()
        return status, error

    def _deliver(self, event: SignalEvent, channel: str, dry_run: bool) -> tuple[str, str | None]:
        if dry_run:
            print(f"[notification:dry-run] channel={channel} symbol={event.symbol} event={event.event_type}")
            return "dry_run", None

        if channel == "line":
            return self._send_line(event)
        if channel == "telegram":
            return self._send_telegram(event)
        return "error", f"Unsupported channel: {channel}"

    def _send_line(self, event: SignalEvent) -> tuple[str, str | None]:
        if not self.settings.line_channel_access_token or not self.settings.line_user_id:
            return "error", "LINE_CHANNEL_ACCESS_TOKEN or LINE_USER_ID is missing"

        response = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={
                "Authorization": f"Bearer {self.settings.line_channel_access_token}",
                "Content-Type": "application/json",
            },
            json={
                "to": self.settings.line_user_id,
                "messages": [{"type": "text", "text": f"{event.title}\n{event.message}"}],
            },
            timeout=20,
        )
        if response.ok:
            return "sent", None
        return "error", response.text[:1000]

    def _send_telegram(self, event: SignalEvent) -> tuple[str, str | None]:
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            return "error", "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing"

        text = f"<b>{escape(event.title)}</b>\n{escape(event.message)}"
        last_error: str | None = None
        total_attempts = len(self.TELEGRAM_RETRY_DELAYS) + 1
        for attempt in range(total_attempts):
            try:
                response = requests.post(
                    f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage",
                    json={
                        "chat_id": self.settings.telegram_chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                    timeout=20,
                )
                if response.ok:
                    return "sent", None
                last_error = response.text[:1000]
            except requests.RequestException as exc:
                last_error = str(exc)[:1000]

            if attempt < len(self.TELEGRAM_RETRY_DELAYS):
                time.sleep(self.TELEGRAM_RETRY_DELAYS[attempt])

        return "error", last_error or "Telegram send failed"
