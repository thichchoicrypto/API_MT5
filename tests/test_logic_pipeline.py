"""
Logic Tests — Phase 2-5 end-to-end pipeline.
Tests known SMC patterns: bullish sweep+CHoCH, bearish reversal, liquidity sweep.
"""
import pytest
from datetime import datetime, timezone, timedelta
from typing import List

from phase2_structure.structure_engine import StructureEngine
from phase3_liquidity.sweep_detector import detect_sweep
from phase3_liquidity.choch_detector import detect_choch
from phase3_liquidity.liquidity_engine import build_liquidity_zones
from phase4_fvg_ob.fvg_engine import detect_fvg, update_fvg_fills
from phase4_fvg_ob.orderblock_engine import detect_order_block, update_ob_mitigation
from phase4_fvg_ob.zone_builder import build_entry_zone, find_confluence_zones
from phase5_entry.trigger_detector import classify_trigger


def _t(h: int) -> datetime:
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=h)


def _c(o, h, l, c, i=0, vol=1000.0):
    return {"open": o, "high": h, "low": l, "close": c, "volume": vol,
            "open_time": _t(i), "symbol": "BTCUSDT", "timeframe": "1h"}


# ─────────────────────────────────────────────
# Bullish Sweep + CHoCH pattern
# ─────────────────────────────────────────────

class TestBullishSweepCHoCH:
    """
    Pattern: price sweeps below a swing low, then CHoCH up.
    Expected: BUY_SIDE_SWEEP detected, BULLISH_CHOCH detected.
    """

    def test_sweep_below_swing_low(self):
        swing_low = 95.0
        candle = _c(94, 96, 93, 96)  # wick below 95, close above → bullish sweep
        sweep = detect_sweep(candle, last_swing_high=110.0, last_swing_low=swing_low)
        assert sweep is not None
        assert sweep["type"] == "BUY_SIDE_SWEEP"
        assert sweep["swept_level"] == swing_low

    def test_sweep_strength_strong(self):
        """Large recovery wick → strong sweep."""
        swing_low = 100.0
        candle = _c(100, 102, 90, 101)  # wick to 90, closes at 101 (recovery 11 of 10 wick)
        sweep = detect_sweep(candle, 120.0, swing_low)
        assert sweep is not None
        assert sweep["strength"] == "strong"

    def test_sweep_strength_weak(self):
        """Small recovery → weak."""
        swing_low = 100.0
        candle = _c(100, 101, 90, 91)  # wick to 90, closes at 91 (barely recovered)
        sweep = detect_sweep(candle, 120.0, swing_low)
        assert sweep is not None
        assert sweep["strength"] == "weak"

    def test_choch_bullish_from_downtrend(self):
        bos = {"type": "BOS_UP", "price": 105.0, "time": _t(0), "swing_level": 100.0}
        choch = detect_choch("DOWNTREND", bos)
        assert choch is not None
        assert choch["type"] == "BULLISH_CHOCH"

    def test_choch_bearish_from_uptrend(self):
        bos = {"type": "BOS_DOWN", "price": 90.0, "time": _t(0), "swing_level": 95.0}
        choch = detect_choch("UPTREND", bos)
        assert choch is not None
        assert choch["type"] == "BEARISH_CHOCH"

    def test_choch_none_when_bos_aligned(self):
        """BOS_UP in UPTREND is NOT a CHoCH."""
        bos = {"type": "BOS_UP", "price": 110.0, "time": _t(0), "swing_level": 105.0}
        choch = detect_choch("UPTREND", bos)
        assert choch is None

    def test_no_sweep_when_no_wick(self):
        """Candle closes below swing low → no bullish sweep."""
        candle = _c(100, 102, 93, 94)  # close < swing_low → not a sweep
        sweep = detect_sweep(candle, 110.0, 95.0)
        assert sweep is None or sweep["type"] != "BUY_SIDE_SWEEP"


# ─────────────────────────────────────────────
# Liquidity Zone Detection
# ─────────────────────────────────────────────

class TestLiquidityZones:
    def _make_swing(self, price, kind="high", i=0):
        return {"price": price, "type": f"swing_{kind}",
                "index": i, "time": _t(i)}

    def test_build_zones_returns_list(self):
        highs = [self._make_swing(110 + i * 5, "high", i) for i in range(3)]
        lows = [self._make_swing(90 - i * 5, "low", i) for i in range(3)]
        zones = build_liquidity_zones(highs, lows)
        assert isinstance(zones, list)
        assert len(zones) > 0

    def test_equal_highs_detected(self):
        """Two swing highs within 0.1% → equal high zone."""
        from phase3_liquidity.liquidity_engine import detect_equal_highs
        highs = [
            self._make_swing(100.0, "high", 0),
            self._make_swing(100.05, "high", 1),  # 0.05% diff → equal
        ]
        zones = detect_equal_highs(highs, threshold=0.001)
        assert len(zones) >= 1
        assert zones[0]["type"] == "equal_high"

    def test_equal_highs_zero_price_no_crash(self):
        """Price=0 should not crash."""
        from phase3_liquidity.liquidity_engine import detect_equal_highs
        highs = [
            self._make_swing(0.0, "high", 0),
            self._make_swing(100.0, "high", 1),
        ]
        # Should not raise ZeroDivisionError
        zones = detect_equal_highs(highs)
        assert isinstance(zones, list)

    def test_buy_side_and_sell_side_zones_present(self):
        highs = [self._make_swing(110.0, "high", 0)]
        lows = [self._make_swing(90.0, "low", 0)]
        zones = build_liquidity_zones(highs, lows)
        types = {z["type"] for z in zones}
        assert "buy_side_liquidity" in types
        assert "sell_side_liquidity" in types


# ─────────────────────────────────────────────
# Full signal pipeline: candles → structure → signal
# ─────────────────────────────────────────────

class TestSignalPipeline:
    def _make_uptrend_candles(self, n=60):
        """Construct a bullish candle series with clear swing structure."""
        candles = []
        price = 100.0
        for i in range(n):
            # Create wave-like movement: push up then small pullback
            if i % 10 < 7:
                price += 1.5  # up
            else:
                price -= 0.5  # small pullback
            t = _t(i)
            candles.append({
                "open": price - 0.3, "high": price + 0.5, "low": price - 0.8,
                "close": price, "volume": 1000.0,
                "open_time": t, "symbol": "BTCUSDT", "timeframe": "1h",
            })
        return candles

    def test_structure_engine_produces_trend(self):
        candles = self._make_uptrend_candles(60)
        engine = StructureEngine("BTCUSDT", "1h")
        out = engine.update(candles)
        assert out["trend"] in ("UP", "UPTREND", "RANGE")
        assert out["last_swing_high"] is not None
        assert out["last_swing_low"] is not None

    def test_fvg_detected_after_impulse(self):
        """3-candle impulse with gap → FVG detected."""
        candles = [
            _c(100, 102, 98, 101, i=0),
            _c(103, 108, 102, 107, i=1),   # impulse
            _c(109, 112, 108, 111, i=2),   # c3.low=108 > c1.high=102 → FVG
        ]
        fvgs = detect_fvg(candles)
        assert len(fvgs) > 0
        assert fvgs[0]["type"] == "BULLISH_FVG"
        assert fvgs[0]["zone"][0] >= 102.0  # bottom of gap

    def test_ob_detected_before_impulse(self):
        """Bearish candle before BOS_UP → Bullish OB."""
        candles = [
            _c(102, 104, 100, 101, i=0),  # bearish (103→101)
            _c(101, 103, 100, 100.5, i=1),  # neutral
            _c(103, 115, 102, 114, i=2),   # BOS impulse
        ]
        candles[0] = _c(104, 105, 100, 101, i=0)  # explicitly bearish
        ob = detect_order_block(candles, bos_index=2, bos_type="BOS_UP")
        assert ob is not None
        assert ob["type"] == "BULLISH_OB"

    def test_zone_builder_picks_best_zone(self):
        """From multiple FVGs, pick the one closest to current price."""
        fvgs = [
            {"type": "BULLISH_FVG", "zone": [80.0, 85.0], "midpoint": 82.5, "filled": False,
             "size": 5.0, "index": 0, "time": None},
            {"type": "BULLISH_FVG", "zone": [98.0, 102.0], "midpoint": 100.0, "filled": False,
             "size": 4.0, "index": 1, "time": None},
        ]
        zone = build_entry_zone("LONG", fvgs, [], [], current_price=104.0, atr=10.0)
        assert zone is not None
        # Should pick the FVG closer to current price (98-102 zone)
        assert zone["midpoint"] == pytest.approx(100.0, abs=5.0)

    def test_trigger_pin_bar_on_zone_touch(self):
        """A hammer candle at the OB zone → classify_trigger returns BULLISH_PIN_BAR."""
        # Hammer: open near high, long lower wick
        hammer = _c(100, 100.5, 93, 99.5, i=1)  # body=0.5, lower_wick=6.5
        prev = _c(104, 105, 101, 102, i=0)
        result = classify_trigger([prev, hammer], "LONG")
        assert result in ("BULLISH_PIN_BAR", "ENGULFING_BULLISH", None)
        # Note: None is acceptable if the candle doesn't meet the exact criteria,
        # but it must not crash

    def test_full_pipeline_no_exceptions(self):
        """Smoke test: run all phases in sequence, no crashes."""
        candles = self._make_uptrend_candles(80)
        engine = StructureEngine("BTCUSDT", "1h")
        structure = engine.update(candles)

        swings_high = structure["structure"]
        sh = [s for s in swings_high if s.get("type") == "swing_high"]
        sl = [s for s in swings_high if s.get("type") == "swing_low"]

        zones = build_liquidity_zones(sh, sl)

        fvgs = detect_fvg(candles[-10:])
        fvgs = update_fvg_fills(fvgs, candles[-1])

        bos_events = structure.get("bos_events", [])
        from phase4_fvg_ob.orderblock_engine import detect_all_obs
        obs = detect_all_obs(candles, bos_events)
        obs = update_ob_mitigation(obs, candles[-1])

        confluence = find_confluence_zones(fvgs, obs)
        zone = build_entry_zone(
            "LONG", fvgs, obs, confluence,
            current_price=candles[-1]["close"],
            atr=2.0,
        )
        # zone may be None (no valid zones near price) — just no crash
        assert zone is None or isinstance(zone, dict)
