from __future__ import annotations

import asyncio
import json
import os

from services.ai_provider import AiBriefResult, normalize_brief_payload, not_configured_result
from services.providers.openai_provider import SYSTEM_PROMPT
from services.providers.perplexity_provider import _extract_json

GEMINI_MODEL = "gemini-2.5-flash"


def _call_gemini(api_key: str, context: dict) -> AiBriefResult:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", GEMINI_MODEL).strip() or GEMINI_MODEL
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            "temperature": 0.3,
            "response_mime_type": "application/json",
        },
    )
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        "請只輸出可由 json.loads 解析的 JSON，不要 Markdown code fence。\n\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )
    response = model.generate_content(prompt)
    content = getattr(response, "text", "") or ""
    parsed = _extract_json(content)
    return normalize_brief_payload("gemini", parsed)


async def generate_gemini_brief(context: dict) -> AiBriefResult:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return not_configured_result("gemini", "GEMINI_API_KEY")
    try:
        return await asyncio.to_thread(_call_gemini, api_key, context)
    except Exception as exc:
        return AiBriefResult(
            provider="gemini",
            status="error",
            direction=None,
            summary=None,
            key_points=[],
            error=str(exc),
        )
