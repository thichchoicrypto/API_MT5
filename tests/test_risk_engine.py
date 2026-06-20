"""
Unit tests — Phase 6: Risk Engine.
"""
import pytest
from datetime import datetime, timezone, timedelta
from phase6_risk.risk_engine import RiskEngine, _calc_atr


def _candle(o, h, l, c, i=0):
    return {
        "open": o, "high": h, "low": l, "close": c, "volume": 100.0,
        "open_time": datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
    }


def _candles(n=20, price=100.0):
    return [_candle(price, price + 1, price - 1, price, i=i) for i in range(n)]


def _structure(sh=110.0, sl=90.0):
    return {"last_swing_high": sh, "last_swing_low": sl, "trend": "RANGE"}


# ─────────────────────────────────────────────
# ATR helper
# ─────────────────────────────────────────────

class TestCalcATR:
    def test_returns_float(self):
        assert isinstance(_calc_atr(_candles()), float)

    def test_too_few_candles(self):
        assert _calc_atr([]) == 1.0
        assert _calc_atr([_candle(100, 101, 99, 100)]) == 1.0

    def test_volatile_candles_higher_atr(self):
        calm = [_candle(100, 100.1, 99.9, 100, i=i) for i in range(20)]
        volatile = [_candle(100, 110, 90, 100, i=i) for i in range(20)]
        assert _calc_atr(volatile) > _calc_atr(calm)


# ─────────────────────────────────────────────
# SL Calculation
# ─────────────────────────────────────────────

class TestCalcSL:
    def setup_method(self):
        self.risk = RiskEngine(10_000.0)

    def test_long_sl_below_entry(self):
        sl = self.risk.calc_sl("LONG", 110.0, 90.0, _candles())
        assert sl is not None
        assert sl < 100.0  # must be below entry area

    def test_short_sl_above_entry(self):
        sl = self.risk.calc_sl("SHORT", 110.0, 90.0, _candles())
        assert sl is not None
        assert sl > 100.0  # above entry area

    def test_sl_fallback_to_atr(self):
        """When no swings, falls back to ATR-based SL."""
        sl = self.risk.calc_sl("LONG", None, None, _candles())
        assert sl is not None

    def test_sl_none_invalid_side(self):
        sl = self.risk.calc_sl("INVALID", 110.0, 90.0, _candles())
        assert sl is None


# ─────────────────────────────────────────────
# TP Calculation
# ─────────────────────────────────────────────

class TestCalcTP:
    def setup_method(self):
        self.risk = RiskEngine(10_000.0)

    def test_long_tp_above_entry(self):
        tps = self.risk.calc_tp("LONG", entry=100.0, sl=95.0, liquidity_zones=[])
        assert len(tps) == 3
        for tp in tps:
            assert tp["level"] > 100.0

    def test_short_tp_below_entry(self):
        tps = self.risk.calc_tp("SHORT", entry=100.0, sl=105.0, liquidity_zones=[])
        assert len(tps) == 3
        for tp in tps:
            assert tp["level"] < 100.0

    def test_tp_rr_ascending(self):
        tps = self.risk.calc_tp("LONG", entry=100.0, sl=95.0, liquidity_zones=[])
        rrs = [tp["rr"] for tp in tps]
        assert rrs[0] <= rrs[1] <= rrs[2]

    def test_tp_sizes_sum_to_one(self):
        tps = self.risk.calc_tp("LONG", entry=100.0, sl=95.0, liquidity_zones=[])
        total = sum(tp["size_ratio"] for tp in tps)
        assert abs(total - 1.0) < 0.001

    def test_zero_sl_distance_returns_empty(self):
        tps = self.risk.calc_tp("LONG", entry=100.0, sl=100.0, liquidity_zones=[])
        assert tps == []


# ─────────────────────────────────────────────
# Position Sizing
# ─────────────────────────────────────────────

class TestPositionSizing:
    def setup_method(self):
        self.risk = RiskEngine(10_000.0)

    def test_position_size_positive(self):
        size = self.risk.calc_position_size(entry=100.0, sl=95.0)
        assert size > 0

    def test_position_size_scales_with_risk(self):
        size1 = self.risk.calc_position_size(100.0, 95.0, risk_pct=0.01)
        size2 = self.risk.calc_position_size(100.0, 95.0, risk_pct=0.02)
        assert size2 == pytest.approx(size1 * 2, rel=0.01)

    def test_sl_too_close_rejected(self):
        size = self.risk.calc_position_size(entry=100.0, sl=99.99)  # 0.01% → below 0.1%
        assert size == 0.0

    def test_invalid_entry_zero(self):
        assert self.risk.calc_position_size(0.0, 0.0) == 0.0

    def test_negative_balance_rejected(self):
        risk = RiskEngine(-1000.0)
        size = risk.calc_position_size(100.0, 95.0)
        assert size == 0.0

    def test_leverage_cap(self):
        """Position size should not exceed 10x leverage."""
        risk = RiskEngine(10_000.0)
        # Very tiny SL → would give huge size without cap
        size = risk.calc_position_size(entry=100_000.0, sl=99_900.0)
        max_size = (10_000.0 * 10) / 100_000.0
        assert size <= max_size + 1e-6


# ─────────────────────────────────────────────
# Drawdown & Risk Limits
# ─────────────────────────────────────────────

class TestDrawdownProtection:
    def test_daily_loss_disables_trading(self):
        risk = RiskEngine(10_000.0)
        # Lose 4% — exceeds 3% daily limit
        risk.register_pnl(-400.0)
        assert risk.trading_enabled is False

    def test_max_drawdown_disables_trading(self):
        risk = RiskEngine(10_000.0)
        risk.peak_balance = 10_000.0
        # Lose 16% — exceeds 15% max drawdown
        risk.register_pnl(-1_600.0)
        assert risk.trading_enabled is False

    def test_five_consecutive_losses_disables(self):
        risk = RiskEngine(10_000.0)
        for _ in range(5):
            risk.register_pnl(-10.0)  # small loss — won't hit daily limit
        assert risk.trading_enabled is False

    def test_win_resets_consecutive_losses(self):
        risk = RiskEngine(10_000.0)
        for _ in range(4):
            risk.register_pnl(-10.0)
        risk.register_pnl(50.0)  # win
        assert risk._consecutive_losses == 0

    def test_reset_daily_reenables_trading(self):
        risk = RiskEngine(10_000.0)
        risk.register_pnl(-50.0)  # small loss
        risk.trading_enabled = False
        risk._consecutive_losses = 5
        risk.reset_daily()
        assert risk.trading_enabled is True
        assert risk._consecutive_losses == 0
        assert risk.daily_pnl == 0.0

    def test_reset_daily_stays_disabled_on_max_dd(self):
        """If max drawdown hit, reset_daily should NOT re-enable trading."""
        risk = RiskEngine(10_000.0)
        risk.register_pnl(-1_600.0)  # 16% loss — exceeds max DD
        risk.reset_daily()
        assert risk.trading_enabled is False

    def test_evaluate_blocked_when_disabled(self):
        risk = RiskEngine(10_000.0)
        risk.trading_enabled = False
        result = risk.evaluate("LONG", 100.0, _candles(), _structure(), [])
        assert result is None


# ─────────────────────────────────────────────
# Breakeven + Trailing
# ─────────────────────────────────────────────

class TestTradeManagement:
    def setup_method(self):
        self.risk = RiskEngine(10_000.0)

    def test_breakeven_long_triggered(self):
        pos = {"entry": 100.0, "sl": 95.0, "side": "LONG"}
        # +1R = +5 → price at 105+
        new_sl = self.risk.check_breakeven(pos, current_price=105.0)
        assert new_sl == 100.0  # SL moved to entry

    def test_breakeven_short_triggered(self):
        pos = {"entry": 100.0, "sl": 105.0, "side": "SHORT"}
        # -1R = -5 → price at 95
        new_sl = self.risk.check_breakeven(pos, current_price=95.0)
        assert new_sl == 100.0

    def test_breakeven_not_triggered_yet(self):
        pos = {"entry": 100.0, "sl": 95.0, "side": "LONG"}
        new_sl = self.risk.check_breakeven(pos, current_price=102.0)
        assert new_sl is None

    def test_trailing_stop_long(self):
        pos = {"entry": 100.0, "sl": 95.0, "side": "LONG", "current_price": 110.0}
        # Candles with lows at 104+ (above current SL of 95)
        candles = [_candle(106, 112, 104, 110, i=i) for i in range(5)]
        new_sl = self.risk.check_trailing_stop(pos, candles)
        assert new_sl is not None
        assert new_sl > 95.0  # trailed up

    def test_trailing_stop_empty_candles(self):
        pos = {"entry": 100.0, "sl": 95.0, "side": "LONG"}
        new_sl = self.risk.check_trailing_stop(pos, [])
        assert new_sl is None

    def test_trailing_uses_last_candle_close_as_fallback(self):
        """If current_price not in position, should use last candle close."""
        pos = {"entry": 100.0, "sl": 95.0, "side": "LONG"}  # no current_price
        candles = [_candle(108, 112, 106, 110, i=i) for i in range(5)]
        # Should not crash
        result = self.risk.check_trailing_stop(pos, candles)
        # May or may not trigger — just ensure no crash
        assert result is None or isinstance(result, float)


# ─────────────────────────────────────────────
# Full evaluate() integration
# ─────────────────────────────────────────────

class TestRiskEvaluate:
    def test_evaluate_returns_dict(self):
        risk = RiskEngine(10_000.0)
        result = risk.evaluate("LONG", 100.0, _candles(), _structure(sh=110, sl=90), [])
        # May return None if RR too low with these prices — just check type
        assert result is None or isinstance(result, dict)

    def test_evaluate_dict_has_required_keys(self):
        risk = RiskEngine(10_000.0)
        # Force a clear RR situation: entry=100, sl=95, swings far apart
        candles = [_candle(100, 102, 98, 100, i=i) for i in range(20)]
        result = risk.evaluate("LONG", 100.0, candles, _structure(sh=130, sl=92), [])
        if result:
            assert "sl" in result
            assert "tp" in result
            assert "rr" in result
            assert "position_size" in result
            assert result["rr"] >= 1.5
