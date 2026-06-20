"""
Unit tests — Phase 2: Swing detection, BOS, Market Structure.
"""
import pytest
from datetime import datetime, timezone

from phase2_structure.swing_detector import detect_swing_highs, detect_swing_lows, detect_swings
from phase2_structure.bos_detector import detect_bos, StructureStateMachine
from phase2_structure.market_structure import classify_structure, _label_points, _determine_trend
from phase2_structure.structure_engine import StructureEngine


def _candle(o, h, l, c, t=None):
    return {
        "open": o, "high": h, "low": l, "close": c, "volume": 1.0,
        "open_time": t or datetime(2024, 1, 1, tzinfo=timezone.utc),
        "symbol": "BTCUSDT", "timeframe": "1h",
    }


def _candles_uptrend(n=20, base=100.0, step=1.0):
    """Simple ascending candles."""
    result = []
    for i in range(n):
        p = base + i * step
        from datetime import timedelta
        t = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
        result.append(_candle(p, p + 0.5, p - 0.5, p + 0.3, t))
    return result


# ─────────────────────────────────────────────
# Swing Detector
# ─────────────────────────────────────────────

class TestSwingDetector:
    def test_swing_high_basic(self):
        """Peak in middle should be detected."""
        candles = [_candle(10, h, 9, 10) for h in [10, 10, 15, 10, 10]]
        highs = detect_swing_highs(candles, n=1)
        assert len(highs) == 1
        assert highs[0]["price"] == 15
        assert highs[0]["type"] == "swing_high"

    def test_swing_low_basic(self):
        """Valley in middle should be detected."""
        candles = [_candle(10, 11, l, 10) for l in [9, 9, 5, 9, 9]]
        lows = detect_swing_lows(candles, n=1)
        assert len(lows) == 1
        assert lows[0]["price"] == 5

    def test_no_swings_flat(self):
        """All-same candles → no swing."""
        candles = [_candle(10, 10, 10, 10)] * 10
        assert detect_swing_highs(candles, n=2) == []
        assert detect_swing_lows(candles, n=2) == []

    def test_too_few_candles(self):
        """Less than 2n+1 candles → empty."""
        candles = [_candle(10, 11, 9, 10)] * 3
        assert detect_swing_highs(candles, n=2) == []

    def test_multiple_swings(self):
        """Multiple peaks and valleys detected."""
        highs_vals = [10, 10, 20, 10, 10, 10, 25, 10, 10]
        candles = [_candle(h - 1, h, h - 2, h - 0.5) for h in highs_vals]
        highs = detect_swing_highs(candles, n=1)
        prices = [h["price"] for h in highs]
        assert 20 in prices
        assert 25 in prices

    def test_detect_swings_combined(self):
        result = detect_swings([_candle(10, h, l, 10)
                                 for h, l in [(11,9),(11,9),(15,9),(11,9),(11,9)]], n=1)
        assert "highs" in result
        assert "lows" in result


# ─────────────────────────────────────────────
# BOS Detector
# ─────────────────────────────────────────────

class TestBOSDetector:
    def test_bos_up(self):
        candle = _candle(100, 105, 98, 101)
        bos = detect_bos(candle, last_swing_high=100.0, last_swing_low=90.0)
        assert bos is not None
        assert bos["type"] == "BOS_UP"

    def test_bos_down(self):
        candle = _candle(100, 102, 88, 89)
        bos = detect_bos(candle, last_swing_high=110.0, last_swing_low=90.0)
        assert bos is not None
        assert bos["type"] == "BOS_DOWN"

    def test_no_bos_inside(self):
        candle = _candle(100, 102, 98, 101)
        bos = detect_bos(candle, last_swing_high=110.0, last_swing_low=90.0)
        assert bos is None

    def test_bos_missing_swings(self):
        candle = _candle(100, 105, 98, 101)
        assert detect_bos(candle, None, None) is None
        assert detect_bos(candle, 100.0, None) is None
        assert detect_bos(candle, None, 90.0) is None

    def test_state_machine_transitions(self):
        sm = StructureStateMachine()
        assert sm.state == "RANGE"
        sm.process_bos({"type": "BOS_UP", "price": 100, "time": None, "swing_level": 95})
        assert sm.state == "UPTREND"
        sm.process_bos({"type": "BOS_DOWN", "price": 90, "time": None, "swing_level": 95})
        assert sm.state == "DOWNTREND"
        sm.process_bos(None)
        assert sm.state == "DOWNTREND"  # no change on None


# ─────────────────────────────────────────────
# Market Structure
# ─────────────────────────────────────────────

class TestMarketStructure:
    def _make_swings(self, prices, kind="high"):
        return [{"price": p, "type": f"swing_{kind}",
                  "index": i, "time": datetime(2024, 1, i+1, tzinfo=timezone.utc)}
                for i, p in enumerate(prices)]

    def test_uptrend_detection(self):
        highs = self._make_swings([100, 110, 120], "high")
        lows = self._make_swings([90, 95, 100], "low")
        result = classify_structure(highs, lows)
        assert result["trend"] == "UP"

    def test_downtrend_detection(self):
        highs = self._make_swings([120, 110, 100], "high")
        lows = self._make_swings([100, 95, 90], "low")
        result = classify_structure(highs, lows)
        assert result["trend"] == "DOWN"

    def test_range_detection(self):
        highs = self._make_swings([100, 110, 105], "high")
        lows = self._make_swings([90, 88, 92], "low")
        result = classify_structure(highs, lows)
        assert result["trend"] == "RANGE"

    def test_too_few_points(self):
        highs = self._make_swings([100], "high")
        lows = self._make_swings([90], "low")
        result = classify_structure(highs, lows)
        assert result["trend"] == "RANGE"

    def test_empty_swings(self):
        result = classify_structure([], [])
        assert result["trend"] == "RANGE"


# ─────────────────────────────────────────────
# StructureEngine (integration)
# ─────────────────────────────────────────────

class TestStructureEngine:
    def test_update_returns_dict(self):
        engine = StructureEngine("BTCUSDT", "1h")
        candles = _candles_uptrend(20)
        out = engine.update(candles)
        assert isinstance(out, dict)
        assert "trend" in out
        assert "last_swing_high" in out
        assert "last_swing_low" in out

    def test_too_few_candles_returns_empty(self):
        engine = StructureEngine("BTCUSDT", "1h", swing_n=5)
        out = engine.update([_candle(100, 101, 99, 100)] * 3)
        assert out["trend"] == "RANGE"
        assert out["last_swing_high"] is None

    def test_bos_deduplication(self):
        """Same BOS price twice should not duplicate events."""
        engine = StructureEngine("BTCUSDT", "1h")
        candles = _candles_uptrend(50)
        engine.update(candles)
        n = len(engine._bos_events)
        engine.update(candles)  # same candles again
        assert len(engine._bos_events) == n  # should not grow

    def test_bos_events_capped_at_20(self):
        """BOS event list should not exceed 20."""
        engine = StructureEngine("BTCUSDT", "1h")
        from datetime import timedelta
        candles = []
        base = 100.0
        for i in range(100):
            t = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
            # Alternating up-down to force many BOS events
            price = base + (i % 2) * 20
            candles.append(_candle(price, price + 1, price - 1, price, t))
            if len(candles) >= 10:
                engine.update(candles)
        assert len(engine._bos_events) <= 20
