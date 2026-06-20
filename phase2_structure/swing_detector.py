"""
Phase 2.2–2.3 — Swing High / Low Detection.
"""
from typing import List, Dict, Optional
from config.settings import SWING_LOOKBACK


def detect_swing_highs(candles: List[dict], n: int = SWING_LOOKBACK) -> List[Dict]:
    """
    Returns list of swing high candles with index and price.
    A swing high: high > all N candles left and right.
    """
    result = []
    for i in range(n, len(candles) - n):
        c = candles[i]
        if all(c["high"] > candles[i - j]["high"] for j in range(1, n + 1)) and \
           all(c["high"] > candles[i + j]["high"] for j in range(1, n + 1)):
            result.append({"index": i, "price": c["high"], "time": c["open_time"], "type": "swing_high"})
    return result


def detect_swing_lows(candles: List[dict], n: int = SWING_LOOKBACK) -> List[Dict]:
    """
    Returns list of swing low candles with index and price.
    A swing low: low < all N candles left and right.
    """
    result = []
    for i in range(n, len(candles) - n):
        c = candles[i]
        if all(c["low"] < candles[i - j]["low"] for j in range(1, n + 1)) and \
           all(c["low"] < candles[i + j]["low"] for j in range(1, n + 1)):
            result.append({"index": i, "price": c["low"], "time": c["open_time"], "type": "swing_low"})
    return result


def detect_swings(candles: List[dict], n: int = SWING_LOOKBACK) -> Dict:
    """Combined swing detection."""
    return {
        "highs": detect_swing_highs(candles, n),
        "lows": detect_swing_lows(candles, n),
    }
