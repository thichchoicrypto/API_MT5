"""
Phase 2.4–2.8 — Market Structure: HH/HL/LH/LL, Trend State, Structure Memory.
"""
from typing import List, Dict, Optional
from utils.logger import logger


def classify_structure(swing_highs: List[Dict], swing_lows: List[Dict]) -> Dict:
    """
    Phase 2.4: Label each swing as HH, LH (highs) or HL, LL (lows).
    Phase 2.5: Determine trend from pattern.
    Returns structure dict with labelled points and trend.
    """
    labelled_highs = _label_points(swing_highs, "high")
    labelled_lows = _label_points(swing_lows, "low")
    trend = _determine_trend(labelled_highs, labelled_lows)
    return {
        "highs": labelled_highs,
        "lows": labelled_lows,
        "trend": trend,
    }


def _label_points(points: List[Dict], kind: str) -> List[Dict]:
    """Label consecutive swings as HH/LH or HL/LL."""
    if len(points) < 2:
        return points[:]
    labelled = [points[0].copy()]
    labelled[0]["label"] = "HH" if kind == "high" else "HL"  # first is baseline

    for i in range(1, len(points)):
        prev = points[i - 1]["price"]
        curr = points[i]["price"]
        p = points[i].copy()
        if kind == "high":
            p["label"] = "HH" if curr > prev else "LH"
        else:
            p["label"] = "HL" if curr > prev else "LL"
        labelled.append(p)
    return labelled


def _determine_trend(labelled_highs: List[Dict], labelled_lows: List[Dict]) -> str:
    """
    Phase 2.5: Simple rule — 2 HH + 2 HL = UP, 2 LH + 2 LL = DOWN, else RANGE.

    Tại sao cần 2 điểm liên tiếp (không phải 1)?
    1 HH đơn lẻ có thể là noise. 2 HH liên tiếp xác nhận xu hướng đang hình thành.
    Đây là định nghĩa cơ bản nhất của Dow Theory: higher highs + higher lows = uptrend.
    """
    if len(labelled_highs) < 2 or len(labelled_lows) < 2:
        return "RANGE"

    recent_highs = labelled_highs[-2:]
    recent_lows = labelled_lows[-2:]

    up_highs = all(h["label"] == "HH" for h in recent_highs)
    up_lows = all(l["label"] == "HL" for l in recent_lows)
    dn_highs = all(h["label"] == "LH" for h in recent_highs)
    dn_lows = all(l["label"] == "LL" for l in recent_lows)

    if up_highs and up_lows:
        return "UP"
    if dn_highs and dn_lows:
        return "DOWN"
    return "RANGE"


# ─────────────────────────────────────────────────────────────────
# Structure Memory (Phase 2.8)
# ─────────────────────────────────────────────────────────────────
class StructureMemory:
    """Tracks rolling market structure state per symbol/timeframe."""

    def __init__(self):
        self._state: Dict = {
            "last_swing_high": None,
            "last_swing_low": None,
            "trend": "RANGE",
            "last_bos": None,
            "highs": [],
            "lows": [],
        }

    def update(self, structure: Dict, bos_events: List[Dict]):
        self._state["highs"] = structure["highs"]
        self._state["lows"] = structure["lows"]
        self._state["trend"] = structure["trend"]

        if structure["highs"]:
            self._state["last_swing_high"] = structure["highs"][-1]["price"]
        if structure["lows"]:
            self._state["last_swing_low"] = structure["lows"][-1]["price"]
        if bos_events:
            self._state["last_bos"] = bos_events[-1]

    @property
    def state(self) -> Dict:
        return self._state.copy()

    @property
    def trend(self) -> str:
        return self._state["trend"]

    @property
    def last_swing_high(self) -> Optional[float]:
        return self._state["last_swing_high"]

    @property
    def last_swing_low(self) -> Optional[float]:
        return self._state["last_swing_low"]
