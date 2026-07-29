from datetime import datetime, timezone
from typing import Any


def api_response(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "data": data,
        "meta": meta or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
