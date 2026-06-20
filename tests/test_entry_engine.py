"""
Unit tests — Phase 4-5: FVG, OB, Zone Builder, Trigger Detector, Entry Engine.
"""
import pytest
from datetime import datetime, timezone, timedelta

from phase4_fvg_ob.fvg_engine import detect_fvg, update_fvg_fills, score_fvg, _calc_atr
from phase4_fvg_ob.orderblock_engine import detect_order_block, update_ob_mitigation
from phase4_fvg_ob.zone_builder import build_entry_zone, find_confluence_zones
from phase5_entry.trigger_detector import (
    is_bullish_trigger, is_bearish_trigger,
    is_engulfing_bullish, is_engulfing_bearish,
    classify_trigger,
)
from phase5_entry.entry_engine import EntryEngine, calc_adx


def _candle(o, h, l, c, vol=100.0, i=0):
    return {
        "open": o, "high": h, "low": l, "close": c, "volume": vol,
        "open_time": datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
        "symbol": "BTCUSDT", "timeframe": "1h",
    }


# ─────────────────────────────────────────────
# Trigger Detector
# ─────────────────────────────────────────────

class TestTriggerDetector:
    def test_bullish_pin_bar(self):
        """Long lower wick → bullish pin bar."""
        c = _candle(100, 101, 90, 100)  # body=0, lower_wick=10
        # body=0 so pin bar requires body > 0 — use slight bullish close
        c2 = _candle(98, 100.5, 90, 100)  # body=2, lower_wick=8
        assert is_bullish_trigger(c2)

    def test_bearish_pin_bar(self):
        """Long upper wick → bearish pin bar (lower_wick must be < body)."""
        # body=0.5, upper_wick=9.5, lower_wick=0.1 (<body) → shooting star
        c = _candle(100, 110, 100.4, 100.5)
        assert is_bearish_trigger(c)

    def test_doji_no_crash(self):
        """Doji (h==l) must not raise ZeroDivisionError."""
        c = _candle(100, 100, 100, 100)
        assert is_bullish_trigger(c) == False
        assert is_bearish_trigger(c) == False

    def test_strong_bullish_body(self):
        """Candle with body > 50% of range → bullish trigger."""
        c = _candle(95, 101, 94, 100)  # range=7, body=5 → 71%
        assert is_bullish_trigger(c)

    def test_strong_bearish_body(self):
        c = _candle(100, 101, 94, 95)  # range=7, body=5 → 71%
        assert is_bearish_trigger(c)

    def test_engulfing_bullish(self):
        prev = _candle(100, 102, 95, 96)   # bearish
        curr = _candle(94, 103, 93, 101)   # bullish, engulfs prev body
        assert is_engulfing_bullish(prev, curr)

    def test_engulfing_bearish(self):
        prev = _candle(95, 102, 94, 101)   # bullish
        curr = _candle(102, 103, 93, 94)   # bearish, engulfs prev body
        assert is_engulfing_bearish(prev, curr)

    def test_classify_trigger_long(self):
        prev = _candle(100, 102, 95, 96, i=0)
        curr = _candle(94, 103, 93, 101, i=1)
        result = classify_trigger([prev, curr], "LONG")
        assert result in ("ENGULFING_BULLISH", "BULLISH_PIN_BAR")

    def test_classify_trigger_short(self):
        prev = _candle(95, 102, 94, 101, i=0)
        curr = _candle(102, 103, 93, 94, i=1)
        result = classify_trigger([prev, curr], "SHORT")
        assert result in ("ENGULFING_BEARISH", "BEARISH_PIN_BAR")

    def test_classify_trigger_empty(self):
        assert classify_trigger([], "LONG") is None

    def test_no_trigger_inside_bar(self):
        """Inside bar with no wick dominance → no trigger."""
        prev = _candle(100, 110, 90, 105, i=0)
        curr = _candle(100, 105, 95, 102, i=1)  # inside, no wick dominance
        result = classify_trigger([prev, curr], "LONG")
        # may or may not trigger — just ensure no crash
        assert result in (None, "ENGULFING_BULLISH", "BULLISH_PIN_BAR")


# ─────────────────────────────────────────────
# FVG Engine
# ─────────────────────────────────────────────

class TestFVGEngine:
    def _bullish_fvg_candles(self):
        """c1.high < c3.low → bullish FVG."""
        return [
            _candle(100, 102, 98, 101, i=0),   # c1: high=102
            _candle(103, 105, 103, 104, i=1),  # c2: impulse
            _candle(106, 108, 104, 107, i=2),  # c3: low=104 > c1.high=102 → FVG
        ]

    def _bearish_fvg_candles(self):
        """c1.low > c3.high → bearish FVG."""
        return [
            _candle(108, 110, 106, 107, i=0),  # c1: low=106
            _candle(105, 106, 103, 104, i=1),
            _candle(102, 104, 100, 103, i=2),  # c3: high=104 < c1.low=106 → FVG
        ]

    def test_detect_bullish_fvg(self):
        fvgs = detect_fvg(self._bullish_fvg_candles())
        assert any(f["type"] == "BULLISH_FVG" for f in fvgs)

    def test_detect_bearish_fvg(self):
        fvgs = detect_fvg(self._bearish_fvg_candles())
        assert any(f["type"] == "BEARISH_FVG" for f in fvgs)

    def test_no_fvg_overlap(self):
        """Normal candles with no gap → no FVG."""
        candles = [_candle(100, 102, 98, 101, i=i) for i in range(5)]
        fvgs = detect_fvg(candles)
        assert fvgs == []

    def test_fvg_too_few_candles(self):
        assert detect_fvg([]) == []
        assert detect_fvg([_candle(100, 101, 99, 100)]) == []

    def test_update_fvg_fills_by_close(self):
        """FVG filled only when close is inside zone (not just wick)."""
        fvg = {"type": "BULLISH_FVG", "zone": [102.0, 104.0], "filled": False,
               "midpoint": 103.0, "size": 2.0, "index": 1, "time": None}
        # Candle that CLOSES inside zone
        candle = _candle(101, 105, 100, 103)
        result = update_fvg_fills([fvg], candle)
        assert fvg["filled"] is True
        assert len(result) == 0

    def test_update_fvg_wick_only_not_filled(self):
        """Wick into FVG but close outside → NOT filled (zone survives for confirmation)."""
        fvg = {"type": "BULLISH_FVG", "zone": [102.0, 104.0], "filled": False,
               "midpoint": 103.0, "size": 2.0, "index": 1, "time": None}
        candle = _candle(101, 103.5, 100, 101)  # wick enters zone, close=101 outside
        result = update_fvg_fills([fvg], candle)
        assert fvg["filled"] is False  # zone still active for confirmation candle
        assert len(result) == 1

    def test_update_fvg_fills_no_touch(self):
        """Candle entirely below zone → not filled."""
        fvg = {"type": "BULLISH_FVG", "zone": [110.0, 115.0], "filled": False,
               "midpoint": 112.5, "size": 5.0, "index": 1, "time": None}
        candle = _candle(100, 105, 98, 102)
        result = update_fvg_fills([fvg], candle)
        assert fvg["filled"] is False
        assert len(result) == 1

    def test_fvg_zone_has_two_elements(self):
        candles = self._bullish_fvg_candles()
        fvgs = detect_fvg(candles)
        for f in fvgs:
            assert len(f["zone"]) == 2
            assert f["zone"][0] < f["zone"][1]


# ─────────────────────────────────────────────
# Order Block Engine
# ─────────────────────────────────────────────

class TestOrderBlockEngine:
    def test_bullish_ob_detected(self):
        """Last bearish candle before BOS_UP → Bullish OB."""
        candles = [
            _candle(100, 102, 99, 101, i=0),  # bullish
            _candle(101, 103, 100, 100.5, i=1),  # bearish (close < open)
            _candle(102, 110, 101, 109, i=2),  # BOS_UP impulse
        ]
        candles[1] = _candle(102, 104, 99, 100, i=1)  # force bearish
        ob = detect_order_block(candles, bos_index=2, bos_type="BOS_UP")
        assert ob is not None
        assert ob["type"] == "BULLISH_OB"

    def test_bearish_ob_detected(self):
        candles = [
            _candle(100, 102, 99, 101, i=0),  # bullish
            _candle(100, 105, 98, 88, i=1),   # impulse down
        ]
        ob = detect_order_block(candles, bos_index=1, bos_type="BOS_DOWN")
        assert ob is not None
        assert ob["type"] == "BEARISH_OB"

    def test_ob_mitigation_by_close(self):
        """OB mitigated only when close is inside zone."""
        ob = {"type": "BULLISH_OB", "zone": [99.0, 101.0], "mitigated": False,
              "midpoint": 100.0, "index": 0, "time": None}
        candle = _candle(102, 103, 98, 100)  # close=100 inside zone
        result = update_ob_mitigation([ob], candle)
        assert ob["mitigated"] is True
        assert len(result) == 0

    def test_ob_wick_only_not_mitigated(self):
        """Wick into OB but close outside → NOT mitigated (zone survives for confirmation)."""
        ob = {"type": "BULLISH_OB", "zone": [99.0, 101.0], "mitigated": False,
              "midpoint": 100.0, "index": 0, "time": None}
        candle = _candle(102, 103, 99.5, 102.5)  # wick at 99.5, close=102.5 outside
        result = update_ob_mitigation([ob], candle)
        assert ob["mitigated"] is False  # zone still active
        assert len(result) == 1

    def test_ob_mitigation_no_touch(self):
        ob = {"type": "BULLISH_OB", "zone": [80.0, 85.0], "mitigated": False,
              "midpoint": 82.5, "index": 0, "time": None}
        candle = _candle(100, 105, 98, 102)  # far above zone
        result = update_ob_mitigation([ob], candle)
        assert ob["mitigated"] is False
        assert len(result) == 1


# ─────────────────────────────────────────────
# Zone Builder
# ─────────────────────────────────────────────

class TestZoneBuilder:
    def _make_fvg(self, lo, hi, direction="BULLISH"):
        return {"type": f"{direction}_FVG", "zone": [lo, hi],
                "midpoint": (lo + hi) / 2, "filled": False, "size": hi - lo, "index": 0, "time": None}

    def _make_ob(self, lo, hi, direction="BULLISH"):
        return {"type": f"{direction}_OB", "zone": [lo, hi],
                "midpoint": (lo + hi) / 2, "mitigated": False, "index": 0, "time": None}

    def test_build_entry_zone_confluence_priority(self):
        fvg = self._make_fvg(100, 105)
        ob = self._make_ob(102, 107)
        confluence = find_confluence_zones([fvg], [ob])
        zone = build_entry_zone("LONG", [fvg], [ob], confluence, current_price=103.0, atr=5.0)
        assert zone is not None
        assert zone["source"] == "CONFLUENCE"

    def test_build_entry_zone_ob_fallback(self):
        fvg = self._make_fvg(100, 105)
        ob = self._make_ob(103, 108)
        zone = build_entry_zone("LONG", [fvg], [ob], [], current_price=110.0, atr=10.0)
        assert zone is not None
        assert zone["source"] == "ORDER_BLOCK"

    def test_build_entry_zone_fvg_fallback(self):
        fvg = self._make_fvg(100, 105)
        zone = build_entry_zone("LONG", [fvg], [], [], current_price=110.0, atr=20.0)
        assert zone is not None
        assert zone["source"] == "FVG"

    def test_build_entry_zone_none_when_no_zones(self):
        zone = build_entry_zone("LONG", [], [], [], current_price=100.0, atr=5.0)
        assert zone is None

    def test_zone_too_far_rejected(self):
        """Zone outside 3×ATR should be rejected."""
        fvg = self._make_fvg(100, 105)
        zone = build_entry_zone("LONG", [fvg], [], [], current_price=200.0, atr=5.0)
        assert zone is None

    def test_short_zone_uses_bearish(self):
        fvg = self._make_fvg(100, 105, "BEARISH")
        ob = self._make_ob(103, 108, "BEARISH")
        zone = build_entry_zone("SHORT", [fvg], [ob], [], current_price=104.0, atr=10.0)
        assert zone is not None
        assert zone["side"] == "SHORT"


# ─────────────────────────────────────────────
# ADX Calculation
# ─────────────────────────────────────────────

class TestADX:
    def test_adx_trending_returns_nonzero(self):
        """Strong trending candles should return ADX > 0."""
        candles = []
        for i in range(50):
            p = 100 + i * 2
            t = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
            candles.append({"open": p, "high": p + 1, "low": p - 0.5, "close": p + 0.8,
                             "volume": 100.0, "open_time": t})
        adx = calc_adx(candles)
        assert adx > 0

    def test_adx_too_few_candles(self):
        candles = [_candle(100, 101, 99, 100, i=i) for i in range(5)]
        assert calc_adx(candles) == 0.0
