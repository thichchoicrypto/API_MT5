"""
Phase 2.6–2.7 — Break of Structure (BOS) + Structure State Machine.
"""
from typing import Optional, List, Dict


def detect_bos(candle: dict,
               last_swing_high: Optional[float],
               last_swing_low: Optional[float]) -> Optional[Dict]:
    """
    Phase 2.6: Detect BOS_UP or BOS_DOWN.
    Returns event dict or None.
    """
    if last_swing_high is None or last_swing_low is None:
        return None

    close = candle["close"]
    if close > last_swing_high:
        return {
            "type": "BOS_UP",
            "price": close,
            "swing_level": last_swing_high,
            "time": candle["open_time"],
        }
    if close < last_swing_low:
        return {
            "type": "BOS_DOWN",
            "price": close,
            "swing_level": last_swing_low,
            "time": candle["open_time"],
        }
    return None


class StructureStateMachine:
    """
    Phase 2.7: Maintains UPTREND / DOWNTREND / RANGE state via BOS events.
    """
    STATES = ("UPTREND", "DOWNTREND", "RANGE")

    def __init__(self):
        self.state: str = "RANGE"
        self.events: List[Dict] = []

    def process_bos(self, bos_event: Optional[Dict]) -> str:
        if bos_event is None:
            return self.state
        if bos_event["type"] == "BOS_UP":
            self.state = "UPTREND"
        elif bos_event["type"] == "BOS_DOWN":
            self.state = "DOWNTREND"
        self.events.append(bos_event)
        return self.state
