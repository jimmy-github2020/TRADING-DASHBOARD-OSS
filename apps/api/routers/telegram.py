from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from config import load_settings
from services.telegram_handler import handle_command


router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])
root_router = APIRouter(tags=["telegram"])


@router.post("/webhook")
@root_router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = load_settings()
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")

    try:
        update = await request.json()
    except Exception:
        return {"ok": True, "handled": False, "reason": "invalid_json"}

    message = update.get("message") if isinstance(update, dict) else None
    if not isinstance(message, dict):
        return {"ok": True, "handled": False, "reason": "no_message"}

    chat = message.get("chat")
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    text = message.get("text")
    if chat_id is None or not isinstance(text, str):
        return {"ok": True, "handled": False, "reason": "no_text_command"}

    try:
        result = await handle_command(
            database_url=settings.database_url,
            bot_token=settings.telegram_bot_token,
            chat_id=chat_id,
            text=text,
        )
    except Exception as exc:
        print(f"[telegram:webhook:error] chat_id={chat_id} error={exc}")
        return {"ok": True, "handled": False, "error": str(exc)}

    return {
        "ok": True,
        "handled": True,
        "command": result.command,
        "reply_sent": result.sent,
        "error": result.error,
    }
