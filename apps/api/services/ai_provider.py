from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

BriefStatus = Literal["ok", "error", "pending", "not_configured"]
BriefDirection = Literal["bullish", "bearish", "neutral"]
DISCLAIMER = "本摘要由 AI 自動生成，僅供參考，不構成任何投資建議。"


@dataclass
class AiBriefResult:
    provider: str
    status: BriefStatus
    direction: BriefDirection | None
    summary: str | None
    key_points: list[str]
    error: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def not_configured_result(provider: str, env_name: str) -> AiBriefResult:
    return AiBriefResult(
        provider=provider,
        status="not_configured",
        direction=None,
        summary=None,
        key_points=[],
        error=f"{env_name} not configured",
    )


def is_configured_api_key(value: str, placeholders: set[str]) -> bool:
    normalized = value.strip()
    return bool(normalized) and normalized not in placeholders


def normalize_brief_payload(provider: str, payload: dict[str, Any]) -> AiBriefResult:
    direction = payload.get("direction")
    if direction not in ("bullish", "bearish", "neutral"):
        direction = "neutral"
    summary = str(payload.get("summary") or "").strip()
    if summary and DISCLAIMER not in summary:
        summary = f"{summary}\n\n{DISCLAIMER}"
    key_points_raw = payload.get("key_points")
    key_points = [str(item).strip() for item in key_points_raw if str(item).strip()] if isinstance(key_points_raw, list) else []
    return AiBriefResult(
        provider=provider,
        status="ok",
        direction=direction,
        summary=summary,
        key_points=key_points[:3],
        error=None,
    )


async def generate_brief(provider: str, context: dict) -> AiBriefResult:
    normalized_provider = provider.strip().lower()
    try:
        if normalized_provider == "openai":
            from services.providers.openai_provider import generate_openai_brief

            return await generate_openai_brief(context)
        if normalized_provider == "perplexity":
            from services.providers.perplexity_provider import generate_perplexity_brief

            return await generate_perplexity_brief(context)
        if normalized_provider == "gemini":
            from services.providers.gemini_provider import generate_gemini_brief

            return await generate_gemini_brief(context)
        return AiBriefResult(
            provider=normalized_provider,
            status="pending",
            direction=None,
            summary=None,
            key_points=[],
            error=None,
        )
    except Exception as exc:
        return AiBriefResult(
            provider=normalized_provider,
            status="error",
            direction=None,
            summary=None,
            key_points=[],
            error=str(exc),
        )
