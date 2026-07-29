from __future__ import annotations

from datetime import date
from time import monotonic
from typing import Any

import httpx
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1", tags=["institutional"])

TWSE_FLOW_URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"
CACHE_TTL_SECONDS = 1800

_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_LAST_VALID: dict[str, dict[str, Any]] = {}


def _cached(key: tuple[str, str]) -> dict[str, Any] | None:
    cached = _CACHE.get(key)
    if cached and cached[0] > monotonic():
        return cached[1]
    return None


def _store_cache(key: tuple[str, str], value: dict[str, Any]) -> dict[str, Any]:
    _CACHE[key] = (monotonic() + CACHE_TTL_SECONDS, value)
    return value


def _parse_amount(value: Any) -> int:
    text = str(value or "").replace(",", "").strip()
    if not text or text == "--":
        return 0
    return int(float(text))


def _find_column(fields: list[str], *keywords: str) -> int:
    normalized = [field.replace(" ", "") for field in fields]
    for index, field in enumerate(normalized):
        if all(keyword in field for keyword in keywords):
            return index
    raise ValueError(f"TWSE response missing column: {'/'.join(keywords)}")


def _blank_flow() -> dict[str, dict[str, int]]:
    return {
        "foreign": {"buy": 0, "sell": 0, "net": 0},
        "trust": {"buy": 0, "sell": 0, "net": 0},
        "dealer": {"buy": 0, "sell": 0, "net": 0},
    }


def _format_summary(data: dict[str, dict[str, int]]) -> str:
    labels = [("foreign", "外資"), ("trust", "投信"), ("dealer", "自營商")]
    parts: list[str] = []
    for key, label in labels:
        net_100m = data[key]["net"] / 100_000_000
        action = "買超" if net_100m >= 0 else "賣超"
        parts.append(f"{label}{action} {abs(net_100m):.1f} 億")
    return "，".join(parts)


def _parse_twse_date(payload: dict[str, Any]) -> str:
    for key in ("date", "dayDate", "stat", "title"):
        value = payload.get(key)
        if value:
            return str(value)
    return date.today().isoformat()


def _parse_twse_flow(payload: dict[str, Any]) -> dict[str, Any]:
    fields = [str(field) for field in payload.get("fields", [])]
    rows = payload.get("data") or []
    if not fields or not rows:
        raise ValueError("TWSE institutional flow response is empty")

    name_idx = 0
    buy_idx = _find_column(fields, "買進")
    sell_idx = _find_column(fields, "賣出")
    net_idx = _find_column(fields, "買賣", "差額")

    data = _blank_flow()
    mapping = {
        "foreign": ("外資及陸資", "外資"),
        "trust": ("投信",),
        "dealer": ("自營商",),
    }

    for row in rows:
        if not isinstance(row, list) or len(row) <= max(name_idx, buy_idx, sell_idx, net_idx):
            continue
        name = str(row[name_idx]).replace(" ", "")
        for target, aliases in mapping.items():
            if any(alias in name for alias in aliases):
                data[target]["buy"] += _parse_amount(row[buy_idx])
                data[target]["sell"] += _parse_amount(row[sell_idx])
                data[target]["net"] += _parse_amount(row[net_idx])
                break

    if all(item["buy"] == 0 and item["sell"] == 0 and item["net"] == 0 for item in data.values()):
        raise ValueError("TWSE institutional flow has no usable rows")

    return {
        "updated_at": _parse_twse_date(payload),
        "source": "TWSE",
        "data": data,
        "summary": _format_summary(data),
        "error_message": None,
    }


async def _fetch_twse_flow() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=12, headers={"User-Agent": "TRADING-DASHBOARD/1.0"}) as client:
        response = await client.get(
            TWSE_FLOW_URL,
            params={"type": "day", "dayDate": "", "response": "json"},
        )
        response.raise_for_status()
    payload = response.json()
    return _parse_twse_flow(payload)


def _unavailable_flow(error_message: str) -> dict[str, Any]:
    return {
        "updated_at": None,
        "source": "unavailable",
        "data": _blank_flow(),
        "summary": "三大法人資料暫時無法取得",
        "error_message": error_message,
    }


@router.get("/institutional/flow")
async def get_institutional_flow_v2(market: str = Query("TAIEX")) -> dict[str, Any]:
    normalized_market = market.strip().upper() or "TAIEX"
    key = ("institutional_flow", normalized_market)
    cached = _cached(key)
    if cached:
        return cached

    if normalized_market != "TAIEX":
        return _store_cache(key, _unavailable_flow("Only TAIEX institutional flow is supported"))

    try:
        result = await _fetch_twse_flow()
        _LAST_VALID[normalized_market] = result
        return _store_cache(key, result)
    except Exception as exc:
        fallback = _LAST_VALID.get(normalized_market)
        if fallback:
            result = {**fallback, "source": "TWSE-fallback", "error_message": str(exc)}
        else:
            result = _unavailable_flow(str(exc))
        return _store_cache(key, result)


@router.get("/institutional")
async def get_institutional_flow(scope: str = Query("tw")) -> dict[str, Any]:
    if scope == "us":
        return {
            "foreign": None,
            "investment_trust": None,
            "dealer": None,
            "unit": "億元",
            "date": None,
            "error_message": "美股法人資料即將支援",
        }

    flow = await get_institutional_flow_v2()
    data = flow["data"]
    return {
        "foreign": round(data["foreign"]["net"] / 100_000_000, 2),
        "investment_trust": round(data["trust"]["net"] / 100_000_000, 2),
        "dealer": round(data["dealer"]["net"] / 100_000_000, 2),
        "unit": "億元",
        "date": flow["updated_at"],
        "error_message": flow.get("error_message"),
    }
