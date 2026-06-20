"""
Phase 2 — Main Structure Engine.
Orchestrates swing detection, HH/HL labelling, BOS, state machine, and MTF bias.
"""
from typing import List, Dict
from phase2_structure.swing_detector import detect_swings
from phase2_structure.market_structure import classify_structure, StructureMemory
from phase2_structure.bos_detector import detect_bos, StructureStateMachine
from phase2_structure.mtf_bias import MTFBias
from utils.logger import logger


class StructureEngine:
    """
    Per-symbol, per-timeframe structure engine.
    Call update(candles) whenever new candles are available.
    """

    def __init__(self, symbol: str, timeframe: str, swing_n: int = 2):
        self.symbol = symbol
        self.timeframe = timeframe
        self.swing_n = swing_n

        self.memory = StructureMemory()
        self.state_machine = StructureStateMachine()
        self._bos_events: List[Dict] = []

    def update(self, candles: List[dict], silent: bool = False) -> Dict:
        """
        Process candles and return current structure state.
        Returns dict matching Phase 2.12 output format.
        silent=True: suppress DEBUG logs (dùng khi warmup để tránh spam log)
        """
        if len(candles) < self.swing_n * 2 + 1:
            return self._empty_output()

        swings = detect_swings(candles, self.swing_n)
        structure = classify_structure(swings["highs"], swings["lows"])

        # Detect BOS on the last candle — with deduplication
        last = candles[-1]
        bos = detect_bos(last, self.memory.last_swing_high, self.memory.last_swing_low)
        if bos and self._is_new_bos(bos):
            self._bos_events.append(bos)
            # Keep only last 20 BOS events to prevent O(n²) blowup
            if len(self._bos_events) > 20:
                self._bos_events = self._bos_events[-20:]
            self.state_machine.process_bos(bos)
            if not silent:
                logger.debug(f"[{self.symbol} {self.timeframe}] BOS: {bos['type']} @ {bos['price']}")

        self.memory.update(structure, self._bos_events)

        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "trend": self.memory.trend,
            "structure": structure["highs"] + structure["lows"],
            "last_swing_high": self.memory.last_swing_high,
            "last_swing_low": self.memory.last_swing_low,
            "bos_events": self._bos_events[-10:],   # last 10
            "state": self.state_machine.state,
        }

    def _is_new_bos(self, bos: Dict) -> bool:
        """Deduplicate: skip BOS if same type AND price within 0.05% of last BOS."""
        if not self._bos_events:
            return True
        last = self._bos_events[-1]
        if last["type"] != bos["type"]:
            return True
        price_diff = abs(bos["price"] - last["price"]) / last["price"]
        return price_diff > 0.0005   # must move 0.05% for a new BOS event

    def _empty_output(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "trend": "RANGE",
            "structure": [],
            "last_swing_high": None,
            "last_swing_low": None,
            "bos_events": [],
            "state": "RANGE",
        }
