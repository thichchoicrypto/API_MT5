"""
Phase 5 — Entry Engine.
Combines all Phase 2–4 outputs into actionable entry signals.
"""
from typing import Optional, Dict, List
import numpy as np
from utils.logger import logger
from config.settings import (
    VOLUME_THRESHOLD, ENTRY_CONFIRM_CANDLES, MIN_RR, MIN_RR_OVERRIDE,
    SESSION_FILTER_ENABLED, CONFIRM_REQUIRED,
)
from phase5_entry.trigger_detector import classify_trigger
from utils.session_filter import is_trading_session, session_stop_reason

# ADX threshold: below this = ranging market, skip trading
# 25 — compromise: filter hard ranging (< 20) but allow moderate trend (20-25)
ADX_MIN_THRESHOLD = 25
ADX_PERIOD = 14

# Per-symbol ADX override — tighter filter for volatile/noisy pairs
ADX_SYMBOL_OVERRIDE = {
    # GBPUSD ADX=25 làm WR drop 49%→45%, PF 1.19→1.02 — giữ nguyên 30
    "GBPUSD": 30,
    "GBPJPY": 30,   # GBP+JPY cross — double volatility
    "XAUUSD": 20,   # Gold trends at lower ADX; momentum-driven
}



def calc_adx(candles: List[dict], period: int = ADX_PERIOD) -> float:
    """
    Calculate ADX (Average Directional Index).
    ADX > 25 = trending, ADX < 25 = ranging.
    """
    if len(candles) < period * 2:
        return 0.0

    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]
    closes = [c["close"] for c in candles]

    plus_dm, minus_dm, tr_list = [], [], []

    for i in range(1, len(candles)):
        h_diff = highs[i]  - highs[i-1]
        l_diff = lows[i-1] - lows[i]

        plus_dm.append(h_diff if h_diff > l_diff and h_diff > 0 else 0.0)
        minus_dm.append(l_diff if l_diff > h_diff and l_diff > 0 else 0.0)

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i]  - closes[i-1])
        )
        tr_list.append(tr)

    def smooth(arr, p):
        s = sum(arr[:p])
        result = [s]
        for v in arr[p:]:
            s = s - s / p + v
            result.append(s)
        return result

    atr_s    = smooth(tr_list,   period)
    plus_s   = smooth(plus_dm,  period)
    minus_s  = smooth(minus_dm, period)

    dx_list = []
    for a, p, m in zip(atr_s, plus_s, minus_s):
        if a == 0:
            continue
        plus_di  = 100 * p / a
        minus_di = 100 * m / a
        denom = plus_di + minus_di
        dx_list.append(100 * abs(plus_di - minus_di) / denom if denom > 0 else 0.0)

    if not dx_list:
        return 0.0

    # Final ADX = smoothed average of DX
    adx = sum(dx_list[-period:]) / period
    return round(adx, 2)


class EntryEngine:
    """
    Phase 5.3–5.13: Entry validation stack.

    Required layers:
    1. Context  — trend + MTF bias
    2. Zone     — OB / FVG
    3. Trigger  — rejection candle
    4. Risk     — RR >= MIN_RR pre-check

    LUỒNG 2 BƯỚC (trigger + confirm):
      Candle N:   pass L1-L5 với trigger candle → lưu vào _pending[side]
      Candle N+1 đến N+3: pass L1-L4 lại → signal được emit

    Tại sao cần confirm candle?
    Trigger candle chỉ cho thấy "có thể" sắp đảo chiều.
    Confirm candle tiếp theo pass L1-L4 = xu hướng đảo chiều được xác nhận.
    Giảm false positive đáng kể so với chỉ dùng 1 candle.

    Tại sao separate pending state cho LONG và SHORT?
    Tránh trường hợp LONG trigger làm ảnh hưởng SHORT pending và ngược lại.
    """

    # Max candles to wait for confirmation before expiring a pending trigger
    # Hardcode 3 vì backtest đã validate với giá trị này (PF 2.22/3.23)
    # ENTRY_CONFIRM_CANDLES trong settings không phản ánh đúng ý nghĩa này
    # ⚠️ KHÔNG ĐỔI mà không backtest lại
    CONFIRM_WINDOW = 3

    def __init__(self, symbol: str, timeframe: str):
        self.symbol = symbol
        self.timeframe = timeframe
        # Separate pending state per side to avoid LONG/SHORT cross-contamination
        self._pending: Dict[str, Optional[Dict]] = {"LONG": None, "SHORT": None}
        self._pending_age: Dict[str, int] = {"LONG": 0, "SHORT": 0}
        # Debug info: populated after each evaluate() call
        # Keys: l1_trend, l2_zone_touch, l3_liquidity, l4_volume, l5_trigger, stop_reason
        self.last_eval_debug: Dict = {}

    def evaluate(self,
                 candles: List[dict],
                 structure_output: Dict,
                 liquidity_output: Dict,
                 entry_zone: Optional[Dict],
                 risk_output: Optional[Dict]) -> Optional[Dict]:
        """
        Main entry evaluation.
        Returns entry signal dict or None.
        """
        # Reset debug info mỗi lần evaluate
        self.last_eval_debug = {
            "l1_trend": None, "l2_zone_touch": None,
            "l3_liquidity": None, "l4_volume": None,
            "l5_trigger": None, "stop_reason": None,
        }

        if not entry_zone:
            self.last_eval_debug["stop_reason"] = "no_zone"
            return None

        side = entry_zone["side"]
        current = candles[-1]

        # ── Regime Filter: ADX (5m and 15m only) ─────────────────
        if self.timeframe in ("5m", "15m"):
            adx = calc_adx(candles)
            adx_threshold = ADX_SYMBOL_OVERRIDE.get(self.symbol, ADX_MIN_THRESHOLD)
            if adx < adx_threshold:
                logger.debug(f"[{self.symbol}] Regime filter: ADX={adx:.1f} < {adx_threshold} → skip")
                self.last_eval_debug["stop_reason"] = f"adx_low_{adx:.0f}"
                return None

        # ── Session Filter: chỉ trade trong giờ có thanh khoản cao ──
        if SESSION_FILTER_ENABLED:
            candle_time = current.get("open_time")
            if candle_time and not is_trading_session(self.symbol, candle_time):
                reason = session_stop_reason(self.symbol, candle_time) or "outside_session"
                logger.debug(f"[{self.symbol}] Session filter: {reason} → skip")
                self.last_eval_debug["stop_reason"] = f"session_{reason}"
                return None

        # Age out stale pending triggers
        if self._pending[side] is not None:
            self._pending_age[side] += 1
            if self._pending_age[side] > self.CONFIRM_WINDOW:
                self._reset_pending(side)

        # ── Layer 1: Context (trend + MTF bias) ──────────────────────
        l1 = self._check_trend_alignment(side, structure_output, liquidity_output)
        self.last_eval_debug["l1_trend"] = l1
        if not l1:
            self.last_eval_debug["stop_reason"] = "l1_trend_fail"
            return None

        # ── Layer 2: Candle touched entry zone ───────────────────────
        l2 = self._candle_touches_zone(current, side, entry_zone)
        self.last_eval_debug["l2_zone_touch"] = l2
        if not l2:
            self.last_eval_debug["stop_reason"] = "l2_zone_fail"
            return None

        # ── Layer 3: Liquidity sweep or CHoCH ────────────────────────
        l3 = self._check_liquidity_context(side, liquidity_output)
        self.last_eval_debug["l3_liquidity"] = l3
        # TEST: bỏ L3 filter — xem tác động
        # if not l3:
        #     self.last_eval_debug["stop_reason"] = "l3_liquidity_fail"
        #     return None

        # ── Layer 4: Volume filter ────────────────────────────────────
        l4 = self._check_volume(candles)
        self.last_eval_debug["l4_volume"] = l4
        # TEST: bỏ L4 filter — xem tác động
        # if not l4:
        #     self.last_eval_debug["stop_reason"] = "l4_volume_fail"
        #     return None

        # ── Layer 5: Trigger candle ───────────────────────────────────
        trigger = classify_trigger(candles, side)
        self.last_eval_debug["l5_trigger"] = trigger

        # CHG-FX-032: per-symbol confirm toggle
        need_confirm = CONFIRM_REQUIRED.get(self.symbol, True)

        if not need_confirm:
            # No confirm required — enter directly on trigger candle
            if trigger is None:
                self.last_eval_debug["stop_reason"] = "l5_no_trigger"
                return None
            orig_trigger = trigger
            self.last_eval_debug["l5_trigger"] = orig_trigger
        else:
            if self._pending[side] is None:
                if trigger is None:
                    self.last_eval_debug["stop_reason"] = "l5_no_trigger"
                    return None
                # First trigger — store and wait for confirmation
                self._pending[side] = {"trigger": trigger, "zone": entry_zone}
                self._pending_age[side] = 0
                logger.debug(f"[{self.symbol}] {side} trigger: {trigger} — awaiting confirm")
                self.last_eval_debug["stop_reason"] = "awaiting_confirm"
                return None

            # ── Confirmation candle ───────────────────────────────────────
            orig_trigger = trigger or self._pending[side]["trigger"]
            self.last_eval_debug["l5_trigger"] = orig_trigger

            # L5b: Confirmation candle direction filter.
            # MARKET entries: cần nến cùng chiều (close > open cho LONG).
            # LIMIT entries (close > midpoint): miễn L5b — chính việc price pullback về
            # midpoint sau này là confirmation đủ mạnh. Nến bearish nhưng trên zone OK.
            zone_mid = entry_zone.get("midpoint", current["close"])
            would_be_limit = (
                (side == "LONG"  and current["close"] > zone_mid) or
                (side == "SHORT" and current["close"] < zone_mid)
            )
            if not would_be_limit:
                # MARKET entry: require candle close in trade direction
                if side == "LONG" and current["close"] < current["open"]:
                    self._reset_pending(side)
                    self.last_eval_debug["stop_reason"] = "l5b_bearish_confirm"
                    return None
                if side == "SHORT" and current["close"] > current["open"]:
                    self._reset_pending(side)
                    self.last_eval_debug["stop_reason"] = "l5b_bullish_confirm"
                    return None

        # ── Layer 6: Risk pre-check ───────────────────────────────────
        _min_rr = MIN_RR_OVERRIDE.get(self.symbol, MIN_RR)  # per-symbol override
        if risk_output and risk_output.get("rr", 0) < _min_rr:
            logger.debug(f"[{self.symbol}] Rejected RR={risk_output.get('rr'):.2f} < {_min_rr}")
            self._reset_pending(side)
            self.last_eval_debug["stop_reason"] = f"l6_rr_fail_{risk_output.get('rr', 0):.1f}"
            return None

        # ── Produce signal ────────────────────────────────────────────
        signal = self._build_signal(side, entry_zone, orig_trigger, risk_output, liquidity_output,
                                    close_price=current["close"])
        self._reset_pending(side)
        self.last_eval_debug["stop_reason"] = None  # no stop — signal generated
        logger.debug(f"[{self.symbol} {self.timeframe}] ENTRY {signal['side']} conf={signal['confidence']:.2f}")
        return signal

    def _check_trend_alignment(self, side: str, structure: Dict, liquidity: Dict) -> bool:
        # mtf_bias: "LONG" / "SHORT" / "NEUTRAL"
        # Với 15m entry: bias từ 1h trend (ưu tiên), fallback về 15m trend
        # Với 1h entry: bias = chính trend 1h của nó
        mtf_bias = liquidity.get("mtf_bias", "NEUTRAL")
        trend = structure.get("trend", "RANGE")
        sweep = liquidity.get("last_sweep")
        choch = liquidity.get("last_choch")

        # Per-symbol RANGE logic:
        # XAUUSD + major FX pairs → OR (sweep OR CHOCH)
        # JPY crosses (USDJPY, EURJPY, GBPJPY) → AND (sweep AND CHOCH): stricter filter needed
        # OR logic for USDJPY caused WR to drop 51.5%→47%, DD explode to 37%, daily loss hit 17x
        _AND_SYMBOLS = {"EURJPY", "GBPJPY", "USDJPY"}  # XAUUSD dùng OR logic — gold hiếm khi có cả sweep lẫn choch
        use_or_logic = (self.symbol not in _AND_SYMBOLS)

        # Per-symbol: XAUUSD bỏ yêu cầu MTF bias — chỉ cần 15m trend đúng chiều
        _IGNORE_MTF_BIAS = {"XAUUSD", "XAGUSD"}
        ignore_bias = (self.symbol in _IGNORE_MTF_BIAS)

        if side == "LONG":
            # AND logic: cả 15m trend VÀ 1h MTF bias đều phải LONG
            # NEUTRAL bias: chỉ cần 15m trend UP (không có 1h confirmation rõ ràng)
            if ignore_bias or mtf_bias == "NEUTRAL":
                trend_ok = trend in ("UP", "UPTREND")
            else:
                trend_ok = trend in ("UP", "UPTREND") and mtf_bias == "LONG"
            range_sweep_ok = (trend == "RANGE"
                              and sweep and sweep["type"] == "BUY_SIDE_SWEEP")
            range_choch_ok = (trend == "RANGE"
                              and choch and choch["type"] == "BULLISH_CHOCH")
            range_ok = (range_sweep_ok or range_choch_ok) if use_or_logic \
                       else (range_sweep_ok and range_choch_ok)
            return trend_ok or range_ok

        if side == "SHORT":
            if ignore_bias or mtf_bias == "NEUTRAL":
                trend_ok = trend in ("DOWN", "DOWNTREND")
            else:
                trend_ok = trend in ("DOWN", "DOWNTREND") and mtf_bias == "SHORT"
            range_sweep_ok = (trend == "RANGE"
                              and sweep and sweep["type"] == "SELL_SIDE_SWEEP")
            range_choch_ok = (trend == "RANGE"
                              and choch and choch["type"] == "BEARISH_CHOCH")
            range_ok = (range_sweep_ok or range_choch_ok) if use_or_logic \
                       else (range_sweep_ok and range_choch_ok)
            return trend_ok or range_ok

        return False

    def _candle_touches_zone(self, candle: dict, side: str, entry_zone: Dict) -> bool:
        """
        Check if candle's range overlaps with entry zone.
        Uses a 0.1% buffer to account for small FVG zones.
        LONG: candle low reached into zone (pullback entry)
        SHORT: candle high reached into zone (pullback entry)
        """
        lo = entry_zone["low"]
        hi = entry_zone["high"]
        # 0.1% buffer to widen zones slightly
        buf = hi * 0.001

        if side == "LONG":
            return candle["low"] <= (hi + buf) and candle["close"] >= (lo - buf)
        else:
            return candle["high"] >= (lo - buf) and candle["close"] <= (hi + buf)

    def _price_in_zone(self, price: float, entry_zone: Dict) -> bool:
        return entry_zone["low"] <= price <= entry_zone["high"]

    def _check_liquidity_context(self, side: str, liquidity: Dict) -> bool:
        sweep = liquidity.get("last_sweep")
        choch = liquidity.get("last_choch")

        if side == "LONG":
            sweep_ok = sweep and sweep["type"] == "BUY_SIDE_SWEEP"
            choch_ok = choch and choch["type"] == "BULLISH_CHOCH"
        else:
            sweep_ok = sweep and sweep["type"] == "SELL_SIDE_SWEEP"
            choch_ok = choch and choch["type"] == "BEARISH_CHOCH"

        # CHoCH requirement for SHORT removed — testing sweep OR choch for all sides
        return bool(sweep_ok or choch_ok)

    def _check_volume(self, candles: List[dict]) -> bool:
        """
        Forex Volume Layer — dùng tick count (không phải real volume).

        MT5 Forex trả về tick_volume (tick count), không phải real volume.
        Tick count vẫn có tương quan với liquidity nhưng noisy hơn.

        Giải pháp: dùng threshold thấp hơn (0.3 thay 0.5) để tránh filter
        quá nhiều signal hợp lệ. Nếu tick count = 0 (candle thiếu data) → pass.

        Ngoài ra thêm candle body size check thay thế volume:
        Nến có body lớn (> 30% ATR) = có momentum thật → pass dù volume thấp.
        """
        if len(candles) < 20:
            return True

        current = candles[-1]
        current_vol = current["volume"]

        # Nếu tick data không có (volume=0) → dùng body size thay thế
        if current_vol == 0:
            body = abs(current["close"] - current["open"])
            highs  = [c["high"] for c in candles[-14:]]
            lows   = [c["low"]  for c in candles[-14:]]
            atr = np.mean([h - l for h, l in zip(highs, lows)])
            return body >= atr * 0.3   # body >= 30% ATR = có momentum

        recent_vol = np.mean([c["volume"] for c in candles[-20:]])
        if recent_vol <= 0:
            return True

        ratio = current_vol / recent_vol
        # Forex: dùng threshold thấp hơn 0.3 (thay 0.5) vì tick volume noisy
        forex_threshold = max(VOLUME_THRESHOLD * 0.6, 0.3)
        return ratio >= forex_threshold

    def _build_signal(self, side: str, entry_zone: Dict, trigger: str,
                      risk_output: Optional[Dict], liquidity: Dict,
                      close_price: float = 0.0) -> Dict:
        reasons = [trigger, entry_zone["source"]]
        if liquidity.get("last_sweep"):
            reasons.append(liquidity["last_sweep"]["type"])
        if liquidity.get("last_choch"):
            reasons.append(liquidity["last_choch"]["type"])

        confidence = _score_confidence(entry_zone, risk_output, liquidity)

        # LIMIT chỉ hợp lệ khi giá hiện tại CHƯA vào zone (cần pullback về midpoint):
        #   LONG:  close > midpoint → giá còn trên zone → chờ kéo về → LIMIT
        #          close <= midpoint → giá đã ở trong/dưới zone → fill ngay → MARKET
        #   SHORT: close < midpoint → giá còn dưới zone → chờ đẩy lên → LIMIT
        #          close >= midpoint → giá đã ở trong/trên zone → fill ngay → MARKET
        # Nếu đặt LIMIT khi giá đã qua midpoint, IB fill ngay nhưng bot nhận
        # "open" (paper lag) → lưu pending → poll sai → cancel oan (CHG-FX-030).
        _close = close_price
        _mid   = entry_zone["midpoint"]
        if entry_zone["source"] in ("ORDER_BLOCK", "CONFLUENCE"):
            if side == "LONG":
                entry_type = "LIMIT" if _close > _mid else "MARKET"
            else:
                entry_type = "LIMIT" if _close < _mid else "MARKET"
        else:
            entry_type = "MARKET"

        signal = {
            "side": side,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "entry_type": entry_type,
            "entry_zone": [entry_zone["low"], entry_zone["high"]],
            "entry_price": entry_zone["midpoint"],
            "confidence": confidence,
            "reason": reasons,
        }
        if risk_output:
            signal.update({
                "sl": risk_output.get("sl"),
                "tp": risk_output.get("tp", []),
                "rr": risk_output.get("rr"),
                "position_size": risk_output.get("position_size"),
            })
        return signal

    def _reset_pending(self, side: str):
        self._pending[side] = None
        self._pending_age[side] = 0


def _score_confidence(entry_zone: Dict, risk: Optional[Dict], liquidity: Dict) -> float:
    score = 0.5
    if entry_zone["source"] == "CONFLUENCE":
        score += 0.15
    elif entry_zone["source"] == "ORDER_BLOCK":
        score += 0.1
    if liquidity.get("last_sweep"):
        score += 0.1
    if liquidity.get("last_choch"):
        score += 0.1
    if risk and risk.get("rr", 0) >= 3:
        score += 0.05
    return min(round(score, 2), 1.0)
