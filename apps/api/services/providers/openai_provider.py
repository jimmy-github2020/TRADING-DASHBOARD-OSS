from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any

from services.ai_provider import (
    DISCLAIMER,
    AiBriefResult,
    is_configured_api_key,
    normalize_brief_payload,
    not_configured_result,
)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o"
SYSTEM_PROMPT = (
    "你是一位專業台灣股市分析師。\n"
    "根據以下結構化市場數據，產出今日盤面摘要。\n"
    "必須包含：\n"
    "1. 市場方向判斷（bullish / bearish / neutral）\n"
    "2. 三個關鍵重點（key_points）\n"
    "3. 完整摘要（summary，200字以內）\n"
    "嚴格禁止給出具體個股買賣建議。\n"
    f"結尾必須加：「{DISCLAIMER}」\n"
    "回傳 JSON 格式：\n"
    "{\n"
    '  "direction": "bullish"|"bearish"|"neutral",\n'
    '  "summary": "...",\n'
    '  "key_points": ["...", "...", "..."]\n'
    "}"
)


def _normalize_result(payload: dict[str, Any]) -> AiBriefResult:
    return normalize_brief_payload("openai", payload)


def _call_openai(api_key: str, context: dict) -> AiBriefResult:
    body = {
        "model": OPENAI_MODEL,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))

    choices = payload.get("choices") or []
    content = choices[0].get("message", {}).get("content", "{}") if choices else "{}"
    return _normalize_result(json.loads(content))


async def generate_openai_brief(context: dict) -> AiBriefResult:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not is_configured_api_key(api_key, {"sk-...", "YOUR_OPENAI_API_KEY"}):
        return not_configured_result("openai", "OPENAI_API_KEY")
    try:
        return await asyncio.to_thread(_call_openai, api_key, context)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return AiBriefResult(
            provider="openai",
            status="error",
            direction=None,
            summary=None,
            key_points=[],
            error=str(exc),
        )
