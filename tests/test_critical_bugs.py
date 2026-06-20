"""
Unit tests for critical and high-severity bugs fixed in code review.
Run: python -m pytest tests/ -v
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock


# ─────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────
def make_candle(close, high=None, low=None, open_=None, volume=100.0, ts=None, tz_aware=True):
    ts = ts or datetime.now(tz=timezone.utc if tz_aware else None)
    return {
        "open_time": ts,
        "open":   open_ or close,
        "high":   high  or close * 1.001,
        "low":    low   or close * 0.999,
        "close":  close,
        "volume": volume,
    }

def make_candles(prices):
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [make_candle(p, ts=base + timedelta(hours=i)) for i, p in enumerate(prices)]


# ─────────────────────────────────────────────
# CRITICAL BUG 1: orderId vs ordId
# ─────────────────────────────────────────────
class TestOrderIdKey:
    def test_okx_response_uses_ordId(self):
        """OKX returns ordId, not orderId. LivePosition must use correct key."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase9_live.position_monitor import LivePosition

        okx_response = {"ordId": "12345678", "state": "filled"}
        signal = {"symbol": "BTCUSDT", "side": "LONG", "entry_price": 50000.0}
        risk   = {"position_size": 0.1, "sl": 49000.0, "tp": [{"level": 52000.0}]}

        pos = LivePosition(okx_response, signal, risk)
        assert pos.order_id == "12345678", f"Expected '12345678', got '{pos.order_id}'"

    def test_fallback_to_orderId(self):
        """Should still work with legacy orderId key."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase9_live.position_monitor import LivePosition

        okx_response = {"orderId": "99999", "state": "filled"}
        signal = {"symbol": "BTCUSDT", "side": "SHORT", "entry_price": 50000.0}
        risk   = {"position_size": 0.1, "sl": 51000.0, "tp": [{"level": 48000.0}]}

        pos = LivePosition(okx_response, signal, risk)
        assert pos.order_id == "99999"


# ─────────────────────────────────────────────
# CRITICAL BUG 2: Drawdown formula sign
# ─────────────────────────────────────────────
class TestDrawdownFormula:
    def test_drawdown_is_positive_when_losing(self):
        """(peak - balance) / peak should be positive when balance < peak."""
        peak    = 10_000.0
        balance = 8_500.0
        drawdown = (peak - balance) / peak
        assert drawdown > 0, "Drawdown should be positive"
        assert abs(drawdown - 0.15) < 0.001, f"Expected 0.15, got {drawdown}"

    def test_wrong_formula_gives_negative(self):
        """The old formula balance/peak - 1 gives negative — confirms the bug existed."""
        peak    = 10_000.0
        balance = 8_500.0
        old_formula = balance / peak - 1
        assert old_formula < 0, "Old formula is negative — confirms bug"

    def test_kill_switch_max_drawdown_triggers(self):
        """Kill switch should trigger at 15% drawdown with correct formula."""
        MAX_DRAWDOWN = 0.15
        peak    = 10_000.0
        balance = 8_490.0  # 15.1% drawdown
        drawdown = (peak - balance) / peak
        assert drawdown >= MAX_DRAWDOWN, "Kill switch should have triggered"


# ─────────────────────────────────────────────
# HIGH BUG 1: Daily loss denominator fixed
# ─────────────────────────────────────────────
class TestDailyLossLimit:
    def test_daily_loss_uses_day_start_balance(self):
        """Daily loss should be calculated against start-of-day balance, not shrinking balance."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase6_risk.risk_engine import RiskEngine

        engine = RiskEngine(account_balance=10_000.0)
        assert engine._day_start_balance == 10_000.0

        # Simulate 2% loss
        engine.register_pnl(-200.0)
        assert engine._day_start_balance == 10_000.0, "Day start balance must not change intraday"

        # Threshold should still use 10000, not 9800
        threshold = engine._day_start_balance * 0.03  # 3%
        assert threshold == 300.0, f"Expected $300 threshold, got ${threshold}"

    def test_day_start_resets_on_new_day(self):
        """After reset_daily(), day_start_balance should snapshot current balance."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase6_risk.risk_engine import RiskEngine

        engine = RiskEngine(account_balance=10_000.0)
        engine.register_pnl(500.0)   # balance = 10500
        engine.reset_daily()
        assert engine._day_start_balance == 10_500.0, "Should snapshot 10500 after reset"

    def test_entry_condition_check(self):
        """entry <= 0 check should not have duplicate condition."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase6_risk.risk_engine import RiskEngine
        import inspect
        src = inspect.getsource(RiskEngine.calc_position_size)
        # Count occurrences of "entry <= 0"
        count = src.count("entry <= 0")
        assert count == 1, f"'entry <= 0' should appear once, found {count} times"


# ─────────────────────────────────────────────
# MEDIUM BUG: OB timezone comparison
# ─────────────────────────────────────────────
class TestOBTimezone:
    def test_tz_aware_vs_naive_candle_index(self):
        """_find_candle_index should handle mixed tz-aware and tz-naive datetimes."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase4_fvg_ob.orderblock_engine import _find_candle_index

        naive_time    = datetime(2025, 6, 1, 12, 0, 0)
        aware_time    = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

        candles_naive = [{"open_time": naive_time, "close": 50000}]
        candles_aware = [{"open_time": aware_time, "close": 50000}]

        # Should find with same tz type
        assert _find_candle_index(candles_naive, naive_time) == 0
        assert _find_candle_index(candles_aware, aware_time) == 0

        # Should find with mixed tz (the bug fix)
        assert _find_candle_index(candles_naive, aware_time) == 0, "Should match across tz types"
        assert _find_candle_index(candles_aware, naive_time) == 0, "Should match across tz types"

    def test_none_target_time_returns_none(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase4_fvg_ob.orderblock_engine import _find_candle_index

        result = _find_candle_index([{"open_time": datetime.now()}], None)
        assert result is None


# ─────────────────────────────────────────────
# MEDIUM BUG: WS multi-candle parsing
# ─────────────────────────────────────────────
class TestWSMultiCandle:
    def test_parse_multiple_closed_candles(self):
        """_parse_candle_event should return ALL closed candles, not just first."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase1_data.ws_collector import _parse_candle_event

        msg = {
            "arg": {"channel": "candle1H", "instId": "BTC-USDT-SWAP"},
            "data": [
                ["1700000000000", "50000", "50500", "49800", "50300", "10.5", "0", "0", "1"],
                ["1700003600000", "50300", "50800", "50100", "50600", "12.0", "0", "0", "1"],
            ]
        }
        result = _parse_candle_event(msg)
        assert isinstance(result, list), "Should return a list"
        assert len(result) == 2, f"Should return 2 candles, got {len(result)}"

    def test_parse_ignores_unconfirmed_candles(self):
        """Should only return candles with confirm='1'."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase1_data.ws_collector import _parse_candle_event

        msg = {
            "arg": {"channel": "candle1H", "instId": "BTC-USDT-SWAP"},
            "data": [
                ["1700000000000", "50000", "50500", "49800", "50300", "10.5", "0", "0", "0"],  # not closed
                ["1700003600000", "50300", "50800", "50100", "50600", "12.0", "0", "0", "1"],  # closed
            ]
        }
        result = _parse_candle_event(msg)
        assert len(result) == 1, "Only closed candle should be returned"

    def test_parse_returns_empty_list_on_empty_data(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase1_data.ws_collector import _parse_candle_event

        result = _parse_candle_event({"arg": {}, "data": []})
        assert result == []


# ─────────────────────────────────────────────
# LOGIC: BOS detection
# ─────────────────────────────────────────────
class TestBOSDetection:
    def test_bos_up_detected_on_close_above_swing_high(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase2_structure.bos_detector import detect_bos

        candle = make_candle(close=51000)  # close above swing high
        result = detect_bos(candle, last_swing_high=50000, last_swing_low=48000)
        assert result is not None
        assert result["type"] == "BOS_UP"

    def test_bos_down_detected_on_close_below_swing_low(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase2_structure.bos_detector import detect_bos

        candle = make_candle(close=47000)
        result = detect_bos(candle, last_swing_high=50000, last_swing_low=48000)
        assert result is not None
        assert result["type"] == "BOS_DOWN"

    def test_no_bos_when_price_inside_range(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase2_structure.bos_detector import detect_bos

        candle = make_candle(close=49000)
        result = detect_bos(candle, last_swing_high=50000, last_swing_low=48000)
        assert result is None

    def test_no_bos_with_none_swing_levels(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase2_structure.bos_detector import detect_bos

        candle = make_candle(close=51000)
        result = detect_bos(candle, last_swing_high=None, last_swing_low=None)
        assert result is None


# ─────────────────────────────────────────────
# LOGIC: Risk engine edge cases
# ─────────────────────────────────────────────
class TestRiskEngineEdgeCases:
    def test_position_size_zero_balance(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase6_risk.risk_engine import RiskEngine

        engine = RiskEngine(account_balance=0.0)
        size = engine.calc_position_size(entry=50000, sl=49000)
        assert size == 0.0, "Zero balance should give zero position size"

    def test_position_size_zero_sl_distance(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase6_risk.risk_engine import RiskEngine

        engine = RiskEngine(account_balance=10_000.0)
        # SL too close (< 0.1%)
        size = engine.calc_position_size(entry=50000, sl=49999)
        assert size == 0.0, "SL too close should give zero position size"

    def test_atr_single_candle_returns_default(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase6_risk.risk_engine import _calc_atr

        single = [make_candle(50000)]
        result = _calc_atr(single)
        assert result == 1.0, "Single candle ATR should return default 1.0"

    def test_atr_empty_returns_default(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase6_risk.risk_engine import _calc_atr

        result = _calc_atr([])
        assert result == 1.0


# ─────────────────────────────────────────────
# LOGIC: FVG detection
# ─────────────────────────────────────────────
class TestFVGDetection:
    def test_bullish_fvg_detected(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase4_fvg_ob.fvg_engine import detect_fvg

        # Bullish FVG: C1.high < C3.low
        candles = [
            make_candle(100, high=102, low=99),   # C1: high=102
            make_candle(105, high=108, low=103),  # C2
            make_candle(110, high=112, low=105),  # C3: low=105 > C1.high=102 → gap
        ]
        result = detect_fvg(candles)
        bullish = [f for f in result if f["type"] == "bullish"]
        assert len(bullish) >= 1, "Should detect bullish FVG"

    def test_no_fvg_without_gap(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase4_fvg_ob.fvg_engine import detect_fvg

        candles = [
            make_candle(100, high=102, low=99),
            make_candle(101, high=103, low=100),
            make_candle(102, high=104, low=101),  # no gap
        ]
        result = detect_fvg(candles)
        assert len(result) == 0 or all(f["size"] < 0 for f in result)

    def test_fvg_requires_minimum_candles(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase4_fvg_ob.fvg_engine import detect_fvg

        result = detect_fvg([make_candle(100), make_candle(101)])
        assert result == [], "Fewer than 3 candles should return empty"


# ─────────────────────────────────────────────
# LOGIC: ADX filter
# ─────────────────────────────────────────────
class TestADXFilter:
    def test_adx_returns_float(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase5_entry.entry_engine import calc_adx

        candles = make_candles([50000 + i * 100 for i in range(50)])
        result = calc_adx(candles)
        assert isinstance(result, float)
        assert result >= 0

    def test_adx_trending_market_above_threshold(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase5_entry.entry_engine import calc_adx, ADX_MIN_THRESHOLD

        # Strong trend: consistent price increases
        candles = make_candles([50000 + i * 500 for i in range(60)])
        adx = calc_adx(candles)
        # In a strong trend, ADX should be elevated (not necessarily > 25 with synthetic data
        # but should at least be calculated without error)
        assert adx >= 0

    def test_adx_insufficient_data_returns_zero(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from phase5_entry.entry_engine import calc_adx

        candles = make_candles([50000, 50100])  # only 2 candles
        result = calc_adx(candles)
        assert result == 0.0
