from __future__ import annotations

from services.technical_analysis import get_technical_summary


async def get_technical_signals(scope: str = "tw") -> dict:
    symbol = "^GSPC" if scope == "us" else "^TWII"
    try:
        summary = await get_technical_summary(symbol=symbol)
        indicators = summary["indicators"]
        kd_signal = indicators["KD"]["signal"]
        return {
            "rsi": indicators["RSI"]["value"],
            "macd": indicators["MACD"]["value"],
            "kd_k": indicators["KD"]["k"],
            "kd_d": indicators["KD"]["d"],
            "signals": {
                "rsi": indicators["RSI"]["signal"],
                "macd": indicators["MACD"]["signal"],
                "kd": "golden_cross" if kd_signal == "bullish" else "death_cross" if kd_signal == "bearish" else "neutral",
            },
            "error": None,
        }
    except Exception as exc:
        return {
            "rsi": None,
            "macd": None,
            "kd_k": None,
            "kd_d": None,
            "signals": {"rsi": "neutral", "macd": "bearish", "kd": "neutral"},
            "error": str(exc),
        }
