"""
Phase 5.6 — Entry Trigger Candle Detection.
Detects pin bars, engulfing, and strong rejection wicks.
"""
from typing import Optional, Dict


def is_bullish_trigger(candle: dict) -> bool:
    """
    Phase 5.6: Bullish trigger patterns:
    - Pin bar: lower wick > 2x body
    - Bullish engulfing (requires prev candle)
    - Strong rejection wick
    """
    o = candle["open"]
    h = candle["high"]
    l = candle["low"]
    c = candle["close"]

    body = abs(c - o)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)

    # Pin bar / hammer
    if body > 0 and lower_wick >= body * 2 and upper_wick < body:
        return True

    # Bullish close with strong body
    candle_range = h - l
    if c > o and body > 0 and candle_range > 0 and body / candle_range > 0.5:
        return True

    return False


def is_bearish_trigger(candle: dict) -> bool:
    """
    Phase 5.6: Bearish trigger patterns:
    - Shooting star: upper wick > 2x body
    - Bearish engulfing
    - Strong rejection from above
    """
    o = candle["open"]
    h = candle["high"]
    l = candle["low"]
    c = candle["close"]

    body = abs(c - o)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)

    # Shooting star / hanging man
    if body > 0 and upper_wick >= body * 2 and lower_wick < body:
        return True

    # Bearish close with strong body
    candle_range = h - l
    if c < o and body > 0 and candle_range > 0 and body / candle_range > 0.5:
        return True

    return False


def is_engulfing_bullish(prev: dict, current: dict) -> bool:
    """Bullish engulfing: current bullish candle body engulfs prior bearish body."""
    if current["close"] <= current["open"]:
        return False
    if prev["close"] >= prev["open"]:
        return False
    return current["close"] > prev["open"] and current["open"] < prev["close"]


def is_engulfing_bearish(prev: dict, current: dict) -> bool:
    """Bearish engulfing: current bearish candle body engulfs prior bullish body."""
    if current["close"] >= current["open"]:
        return False
    if prev["close"] <= prev["open"]:
        return False
    return current["close"] < prev["open"] and current["open"] > prev["close"]


def classify_trigger(candles: list, side: str) -> Optional[str]:
    """
    Classify entry trigger on the last candle.
    Returns trigger type string or None.
    """
    if not candles:
        return None
    last = candles[-1]
    prev = candles[-2] if len(candles) >= 2 else None

    if side == "LONG":
        if prev and is_engulfing_bullish(prev, last):
            return "ENGULFING_BULLISH"
        if is_bullish_trigger(last):
            return "BULLISH_PIN_BAR"
    elif side == "SHORT":
        if prev and is_engulfing_bearish(prev, last):
            return "ENGULFING_BEARISH"
        if is_bearish_trigger(last):
            return "BEARISH_PIN_BAR"
    return None
