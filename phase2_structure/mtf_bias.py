"""
Phase 2.10 — Multi-Timeframe Bias Engine.
Combines H1 bias + M15 structure + M5 entry context.
"""
from typing import Dict, Optional
from utils.logger import logger


class MTFBias:
    """
    Combines structure from multiple timeframes to produce a directional bias.
    Rule:
        H1 UP + M15 UP → LONG only
        H1 DOWN + M15 DOWN → SHORT only
        Mismatch → NEUTRAL
    """

    def __init__(self):
        self._biases: Dict[str, str] = {}   # tf -> "UP" | "DOWN" | "RANGE"

    def update(self, timeframe: str, trend: str):
        self._biases[timeframe] = trend
        logger.debug(f"MTF bias updated: {timeframe}={trend}")

    def get_bias(self) -> str:
        h1 = self._biases.get("1h", "RANGE")
        m15 = self._biases.get("15m", "RANGE")
        m5 = self._biases.get("5m", "RANGE")

        if h1 == "UP" and m15 == "UP":
            return "LONG"
        if h1 == "DOWN" and m15 == "DOWN":
            return "SHORT"
        return "NEUTRAL"

    def is_long_allowed(self) -> bool:
        return self.get_bias() == "LONG"

    def is_short_allowed(self) -> bool:
        return self.get_bias() == "SHORT"

    @property
    def biases(self) -> Dict[str, str]:
        return self._biases.copy()
