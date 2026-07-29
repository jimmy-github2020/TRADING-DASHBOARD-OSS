from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import time
from zoneinfo import ZoneInfo

import redis
import requests


RETRY_DELAYS_SECONDS = (1, 2, 4)
DEFAULT_DEDUP_TTL_SECONDS = 4 * 60 * 60
TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class TelegramSendResult:
    status: str
    error: str | None = None
    skipped: bool = False


def send_message(
    *,
    bot_token: str,
    chat_id: str,
    html: str,
    dry_run: bool,
    notification_type: str,
    redis_url: str | None = None,
    dedup_ttl_seconds: int | None = None,
) -> TelegramSendResult:
    mode = "dry-run" if dry_run else "send"
    if dry_run:
        print(f"[telegram:dry-run] mode={mode} chat_id={chat_id or '-'} type={notification_type} preview={html[:120]}")
        return TelegramSendResult(status="dry_run")

    if not bot_token or not chat_id:
        return TelegramSendResult(status="failed", error="TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing")

    ttl_seconds = dedup_ttl_seconds or _dedup_ttl(notification_type)
    dedup_key = _dedup_key(notification_type)
    redis_client = _connect_redis(redis_url)
    reserved_dedup = False
    if redis_client is not None:
        reserved_dedup = should_send_notification(redis_client, dedup_key, ttl_seconds)
        if not reserved_dedup:
            return TelegramSendResult(status="sent", skipped=True)

    last_error: str | None = None
    total_attempts = len(RETRY_DELAYS_SECONDS) + 1
    for attempt_index in range(total_attempts):
        attempt = attempt_index + 1
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": html,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            if response.ok:
                print(
                    f"[telegram:send] mode={mode} chat_id={_mask_chat_id(chat_id)} "
                    f"type={notification_type} attempt={attempt} final_success=True"
                )
                return TelegramSendResult(status="sent")

            last_error = _error_summary(response)
            if not _is_retryable_status(response.status_code):
                print(
                    f"[telegram:send] mode={mode} chat_id={_mask_chat_id(chat_id)} "
                    f"type={notification_type} attempt={attempt} final_success=False retryable=False error={last_error}"
                )
                _release_dedup_on_failure(redis_client, dedup_key, reserved_dedup)
                return TelegramSendResult(status="failed", error=last_error)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            if not _is_retryable_exception(exc):
                _release_dedup_on_failure(redis_client, dedup_key, reserved_dedup)
                return TelegramSendResult(status="failed", error=last_error)

        if attempt_index < len(RETRY_DELAYS_SECONDS):
            delay = RETRY_DELAYS_SECONDS[attempt_index]
            print(
                f"[telegram:retry] mode={mode} chat_id={_mask_chat_id(chat_id)} type={notification_type} "
                f"attempt={attempt} next_delay={delay}s error={last_error}"
            )
            time.sleep(delay)

    print(
        f"[telegram:send] mode={mode} chat_id={_mask_chat_id(chat_id)} "
        f"type={notification_type} attempts={total_attempts} final_success=False error={last_error or 'Telegram send failed'}"
    )
    _release_dedup_on_failure(redis_client, dedup_key, reserved_dedup)
    return TelegramSendResult(status="failed", error=last_error or "Telegram send failed")


def should_send_notification(client: redis.Redis, dedup_key: str, ttl_seconds: int) -> bool:
    try:
        created = bool(client.set(dedup_key, "1", nx=True, ex=ttl_seconds))
        print(f"[telegram:dedup] key={dedup_key} skipped={not created} ttl_seconds={ttl_seconds}")
        return created
    except redis.RedisError as exc:
        print(f"[telegram:redis-warning] dedup unavailable; sending allowed. key={dedup_key} error={exc}")
        return True


def _dedup_key(notification_type: str) -> str:
    today = datetime.now(TAIPEI).strftime("%Y-%m-%d")
    return f"telegram:sent:{notification_type}:{today}"


def _dedup_ttl(notification_type: str) -> int:
    if notification_type.startswith(("price_alert:", "signal_")):
        return 24 * 60 * 60
    if notification_type in {"morning_brief", "midday_flash", "closing_report"}:
        return 2 * 60 * 60
    return DEFAULT_DEDUP_TTL_SECONDS


def _connect_redis(redis_url: str | None) -> redis.Redis | None:
    if not redis_url:
        return None
    try:
        client = redis.Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return client
    except redis.RedisError as exc:
        print(f"[telegram:redis-warning] Redis unavailable; sending allowed. error={exc}")
        return None


def _release_dedup_on_failure(client: redis.Redis | None, dedup_key: str, reserved: bool) -> None:
    if client is None or not reserved:
        return
    try:
        client.delete(dedup_key)
    except redis.RedisError as exc:
        print(f"[telegram:redis-warning] failed to release dedup key={dedup_key} error={exc}")


def _error_summary(response: requests.Response) -> str:
    body = (response.text or "").replace("\n", " ")[:300]
    return f"HTTP {response.status_code}: {body}"


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _is_retryable_exception(exc: requests.RequestException) -> bool:
    response = getattr(exc, "response", None)
    if response is None:
        return isinstance(exc, (requests.Timeout, requests.ConnectionError))
    return _is_retryable_status(response.status_code)


def _mask_chat_id(chat_id: str) -> str:
    value = str(chat_id)
    if len(value) <= 4:
        return "****"
    return f"***{value[-4:]}"
