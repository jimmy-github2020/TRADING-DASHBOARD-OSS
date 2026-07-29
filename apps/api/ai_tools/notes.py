from __future__ import annotations

from datetime import date as date_type


async def get_daily_notes(date: str | None = None) -> dict:
    try:
        note_date = date or date_type.today().isoformat()
        return {"date": note_date, "notes": [], "error": None}
    except Exception as exc:
        return {"date": date or date_type.today().isoformat(), "notes": [], "error": str(exc)}
