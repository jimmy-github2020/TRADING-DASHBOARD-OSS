from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any

from services.ai_provider import AiBriefResult, is_configured_api_key, normalize_brief_payload, not_configured_result
from services.providers.openai_provider import DISCLAIMER, SYSTEM_PROMPT

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar-pro"


def _extract_json(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        clean = clean.removeprefix("json").strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        clean = clean[start : end + 1]
    return json.loads(clean)


def _normalize_result(payload: dict[str, Any]) -> AiBriefResult:
    return normalize_brief_payload("perplexity", payload)


def _call_perplexity(api_key: str, context: dict) -> AiBriefResult:
    body = {
        "model": PERPLEXITY_MODEL,
        "temperature": 0.3,
        "search_recency_filter": "day",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "請只輸出可由 json.loads 解析的 JSON，不要 Markdown code fence。\n\n"
                    + json.dumps(context, ensure_ascii=False)
                ),
            },
        ],
    }
    request = urllib.request.Request(
        PERPLEXITY_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))

    choices = payload.get("choices") or []
    content = choices[0].get("message", {}).get("content", "") if choices else ""
    try:
        parsed = _extract_json(content)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Failed to parse response as JSON") from exc
    return _normalize_result(parsed)


async def generate_perplexity_brief(context: dict) -> AiBriefResult:
    api_key = os.getenv("PERPLEXITY_API_KEY", "").strip()
    if not is_configured_api_key(api_key, {"pplx-...", "YOUR_PERPLEXITY_API_KEY"}):
        return not_configured_result("perplexity", "PERPLEXITY_API_KEY")
    try:
        return await asyncio.to_thread(_call_perplexity, api_key, context)
    except ValueError as exc:
        return AiBriefResult(
            provider="perplexity",
            status="error",
            direction=None,
            summary=None,
            key_points=[],
            error=str(exc),
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return AiBriefResult(
            provider="perplexity",
            status="error",
            direction=None,
            summary=None,
            key_points=[],
            error=str(exc),
        )
