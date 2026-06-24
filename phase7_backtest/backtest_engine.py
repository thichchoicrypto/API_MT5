"""
Phase 7 — Event-Driven Backtest Engine (Forex / OANDA).
Simulates all 9 strategy phases on historical candle data.

Forex adaptations vs OKX version:
  - risk.evaluate() takes symbol as 2nd argument
  - _calc_pnl uses spread cost instead of exchange fees
  - No funding rates

Backtest ↔ Live alignment:
  CHG-BT-001  LIMIT simulation: không fill ngay, đợi giá chạm midpoint
              ở candle sau. Giống live place_order(LIMIT) → chờ MT5 khớp.
  CHG-BT-002  Same-candle re-entry blocked: sau khi đóng trade trên candle N
              không mở ngay candle N (live: close là tick event, signal
              chỉ fire candle N+1).
  CHG-BT-003  Structure-based LIMIT cancellation (per limit_order_logic.md):
              • Rule 1 — price closes beyond SL → structure_broken
              • Rule 3 — price closes through entry zone → ob_invalidated
              Time-based (LIMIT_ORDER_TIMEOUT_CANDLES) chỉ là safety fallback.
  CHG-BT-004  Opposite-direction entries allowed while LIMIT pending:
              • LIMIT pending chỉ block same-side (giống Live: có thể giữ 2 vị thế)
              • LIMIT age luôn tăng mỗi candle, kể cả khi đang có open trade
              • Không cho đặt 2 LIMIT đồng thời → skip LIMIT nếu đã có pending

Note: order_type DB column là VARCHAR(10) — dùng "LMT_FILL" (8 ký tự)
cho LIMIT đã khớp, không dùng "LIMIT_FILLED" (12 ký tự) để tránh truncate.
"""
import random
from typing import List, Dict, Optional, Callable
from datetime import datetime
from utils.logger import logger
from config.settings import LIMIT_ORDER_TIMEOUT_CANDLES
from phase2_structure.structure_engine import StructureEngine
from phase2_structure.mtf_bias import MTFBias
from phase3_liquidity.liquidity_engine import build_liquidity_zones
from phase3_liquidity.sweep_detector import detect_sweep
from phase3_liquidity.choch_detector import detect_choch, StructureShiftTracker
from phase3_liquidity.liquidity_confluence import evaluate_confluence
from phase4_fvg_ob.fvg_engine import detect_fvg, update_fvg_fills
from phase4_fvg_ob.orderblock_engine import detect_all_obs, update_ob_mitigation
from phase4_fvg_ob.zone_builder import find_confluence_zones, build_entry_zone
from phase5_entry.entry_engine import EntryEngine
from phase6_risk.risk_engine import RiskEngine


# Forex: no exchange fees — cost is spread (already in mid price approximation)
# We add a small spread cost at entry for realism: ~1 pip per trade
TAKER_FEE    = 0.0      # no taker fee for Forex
MAKER_FEE    = 0.0      # no maker fee for Forex
SLIPPAGE_PCT = 0.00005  # ~0.5 pip slippage on 1.0 price → ~$5 per standard lot
SPREAD_COST_PCT = 0.00010  # ~1 pip spread cost at entry


class BacktestTrade:
    def __init__(self, signal: Dict, risk: Dict, entry_price: float, candle_time: datetime):
        self.signal = signal
        self.risk = risk
        self.entry_price = entry_price
        self.candle_time = candle_time
        self.side = signal["side"]
        self.sl = risk["sl"]
        self.tps = risk["tp"]
        self.position_size = risk["position_size"]
        self.exit_price: Optional[float] = None
        self.exit_time: Optional[datetime] = None
        self.pnl: float = 0.0
        self.status: str = "OPEN"   # OPEN / TP / SL / BE / CLOSED
        self.be_set: bool = False
        self.tp_index: int = 0
        self.peak_price: float = entry_price   # track best price after entry (for trailing)

    def to_dict(self) -> Dict:
        return {
            "side": self.side,
            "entry": self.entry_price,
            "exit": self.exit_price,
            "sl": self.sl,
            "tp1": self.tps[0]["level"] if self.tps else None,
            "pnl": round(self.pnl, 4),
            "status": self.status,
            "entry_time": str(self.candle_time),
            "exit_time": str(self.exit_time),
        }


class BacktestEngine:
    def __init__(self, symbol: str, timeframe: str,
                 initial_balance: float = 10_000.0,
                 slippage: float = SLIPPAGE_PCT,
                 candles_15m: Optional[List[dict]] = None,
                 candles_1h: Optional[List[dict]] = None,
                 enable_tracker: bool = False,
                 news_filter=None):
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_balance = initial_balance
        self.slippage = slippage
        self.enable_tracker = enable_tracker
        self._news_filter = news_filter   # NewsFilter instance hoặc None
        self._tracker_records: List[Dict] = []   # collect tracking records

        # Entry timeframe engine
        self._structure = StructureEngine(symbol, timeframe)
        self._entry_engine = EntryEngine(symbol, timeframe)
        self._risk = RiskEngine(initial_balance, symbol=symbol)
        self._shift_tracker = StructureShiftTracker()

        # MTF: proper multi-timeframe structure engines
        self._candles_15m = candles_15m or []
        self._candles_1h  = candles_1h  or []
        self._struct_15m_engine = StructureEngine(symbol, "15m") if candles_15m else None
        self._struct_1h_engine  = StructureEngine(symbol, "1h")  if candles_1h  else None
        self._struct_15m: Dict = {}
        self._struct_1h:  Dict = {}
        self._idx_15m: int = 0
        self._idx_1h:  int = 0

        # CHG-BT-006: Cho phép max 2 concurrent trades (AGGRESSIVE profile max_open_positions=2)
        # Thay single _open_trade bằng list _open_trades
        self._open_trades: List[BacktestTrade] = []
        MAX_OPEN_POSITIONS = 2  # từ AGGRESSIVE profile
        self._max_open = MAX_OPEN_POSITIONS
        # CHG-BT-001: LIMIT pending state
        # Khi entry_type == "LIMIT", không fill ngay — lưu vào đây,
        # fill ở candle sau khi giá chạm midpoint.
        self._pending_entry: Optional[Dict] = None
        self._trades: List[BacktestTrade] = []
        self._equity: List[Dict] = []
        self._fvgs: List[Dict] = []
        self._obs: List[Dict] = []

        # TTL memory: giữ sweep/CHoCH N candles sau khi detect
        # Tại sao cần TTL?
        #   Sweep/CHoCH thường xảy ra 1-3 candles trước entry signal thật sự.
        #   Không có TTL → layer 3 chỉ pass đúng candle detect → quá strict, bỏ qua nhiều signal tốt.
        #   TTL=20 → sweep/choch detect cách đây <= 20 candles vẫn là context hợp lệ.
        # Live engine có TTL state tương tự (per-symbol dict thay vì single value).
        self._last_sweep: Optional[Dict] = None
        self._last_choch: Optional[Dict] = None
        self._sweep_ttl: int = 0
        self._choch_ttl: int = 0
        self._EVENT_TTL = 20  # 20 candles × 15m = 5 giờ (hợp lý cho context)

    def _advance_mtf(self, current_time):
        """Advance 15m and 1h structure engines up to current_time.

        TẠI SAO CẦN ADVANCE RIÊNG (không dùng cùng 1 structure engine)?
        Backtest chạy candle-by-candle trên entry TF (ví dụ 15m).
        Nhưng để có MTF bias, cần biết 1h trend TẠI THỜI ĐIỂM current candle.
        → Advance 1h engine đến đúng timestamp → lấy trend 1h tại thời điểm đó.
        Không được advance 1h engine vượt quá current_time (look-ahead bias).

        Logic advance: chỉ process 1h candle khi open_time + 1h <= current_time
        (candle đó đã ĐÓNG trước current time — không dùng candle đang hình thành)
        """
        from datetime import timedelta

        # Advance 15m
        if self._struct_15m_engine:
            while self._idx_15m < len(self._candles_15m):
                c = self._candles_15m[self._idx_15m]
                if c["open_time"] + timedelta(minutes=15) <= current_time:
                    w = self._candles_15m[max(0, self._idx_15m - 100): self._idx_15m + 1]
                    self._struct_15m = self._struct_15m_engine.update(w)
                    self._idx_15m += 1
                else:
                    break

        # Advance 1h
        if self._struct_1h_engine:
            while self._idx_1h < len(self._candles_1h):
                c = self._candles_1h[self._idx_1h]
                if c["open_time"] + timedelta(hours=1) <= current_time:
                    w = self._candles_1h[max(0, self._idx_1h - 100): self._idx_1h + 1]
                    self._struct_1h = self._struct_1h_engine.update(w)
                    self._idx_1h += 1
                else:
                    break

    def _get_mtf_bias(self, entry_trend: str = "RANGE") -> str:
        """
        Phase 2.10: H1 → Bias, M15 → Structure confirmation.
        Returns LONG / SHORT / NEUTRAL.
        - 5m/15m entry: use real H1 data for bias
        - 1h entry: use own trend as bias (no higher TF needed)
        """
        if self._struct_1h:
            h1_trend = self._struct_1h.get("trend", "RANGE")
            if h1_trend in ("UP", "UPTREND"):
                return "LONG"
            if h1_trend in ("DOWN", "DOWNTREND"):
                return "SHORT"
        if self._struct_15m:
            m15_trend = self._struct_15m.get("trend", "RANGE")
            if m15_trend in ("UP", "UPTREND"):
                return "LONG"
            if m15_trend in ("DOWN", "DOWNTREND"):
                return "SHORT"
        # Fallback: use entry TF own trend (for 1h entries)
        if entry_trend in ("UP", "UPTREND"):
            return "LONG"
        if entry_trend in ("DOWN", "DOWNTREND"):
            return "SHORT"
        return "NEUTRAL"

    def run(self, candles: List[dict], warmup: int = 50) -> Dict:
        """
        Phase 7.4: Event-driven loop — one candle at a time.
        Uses proper MTF: 1h bias + 15m structure + entry TF signals.
        """
        logger.info(f"Backtest started: {self.symbol} {self.timeframe} — {len(candles)} candles")

        balance = self.initial_balance
        self._equity = [{"time": candles[0]["open_time"], "balance": balance}]
        _last_day = None

        for i in range(warmup, len(candles)):
            window = candles[max(0, i - 200): i + 1]
            current = candles[i]

            # Advance MTF engines to current candle time
            self._advance_mtf(current["open_time"])

            # Reset daily limits at start of each new trading day
            current_day = current["open_time"].date()
            if _last_day is None or current_day != _last_day:
                self._risk.reset_daily()
                _last_day = current_day

            # Update structure
            struct = self._structure.update(window)

            # Liquidity zones from swing highs/lows
            swing_highs = [s for s in struct.get("structure", []) if s.get("type") == "swing_high"]
            swing_lows  = [s for s in struct.get("structure", []) if s.get("type") == "swing_low"]
            liq_zones = build_liquidity_zones(swing_highs, swing_lows)

            # Detect sweep / choch on current candle
            new_sweep = detect_sweep(current, struct.get("last_swing_high"), struct.get("last_swing_low"))
            last_bos  = struct["bos_events"][-1] if struct.get("bos_events") else None
            new_choch = detect_choch(struct.get("trend", "RANGE"), last_bos)
            shift     = self._shift_tracker.process(new_choch, last_bos, current["close"])

            # Update persistent state with TTL
            if new_sweep:
                self._last_sweep = new_sweep
                self._sweep_ttl  = self._EVENT_TTL
            elif self._sweep_ttl > 0:
                self._sweep_ttl -= 1
            else:
                self._last_sweep = None

            if new_choch:
                self._last_choch = new_choch
                self._choch_ttl  = self._EVENT_TTL
            elif self._choch_ttl > 0:
                self._choch_ttl -= 1
            else:
                self._last_choch = None

            # MTF bias: real H1 for 5m/15m, own trend for 1h
            trend = struct.get("trend", "RANGE")
            mtf_bias = self._get_mtf_bias(entry_trend=trend)

            liq_output = {
                "liq_zones": liq_zones,
                "last_sweep": self._last_sweep,
                "last_choch": self._last_choch,
                "structure_shift": shift,
                "mtf_bias": mtf_bias,
            }

            # FVG + OB (pass symbol for per-symbol ATR ratio / OB lookback)
            self._fvgs = detect_fvg(window[-30:], symbol=self.symbol)
            self._fvgs = update_fvg_fills(self._fvgs, current)
            self._obs = detect_all_obs(window[-50:], struct.get("bos_events", []), symbol=self.symbol)
            self._obs = update_ob_mitigation(self._obs, current)
            confluence = find_confluence_zones(self._fvgs, self._obs)

            current_price = current["close"]
            from phase4_fvg_ob.fvg_engine import _calc_atr
            atr = _calc_atr(window)

            # ── CHG-BT-001/003/004: Check pending LIMIT order ───────────────────
            # Fill khi: LONG → low <= midpoint | SHORT → high >= midpoint
            # CHG-BT-003 (limit_order_logic.md): hủy theo structure, không theo time:
            #   Rule 1: close < sl (LONG) / close > sl (SHORT) → structure_broken
            #   Rule 3: close < zone_low (LONG) / close > zone_high (SHORT) → ob_invalidated
            # LIMIT_ORDER_TIMEOUT_CANDLES chỉ là safety fallback.
            # CHG-BT-004a: age tăng mỗi candle, kể cả khi có open trade.
            if self._pending_entry is not None:
                self._pending_entry["age"] += 1

            if self._pending_entry is not None and len(self._open_trades) < self._max_open:
                pe  = self._pending_entry
                mid = pe["entry_price"]
                sl  = pe["risk_out"]["sl"]

                filled = (
                    (pe["side"] == "LONG"  and current["low"]  <= mid) or
                    (pe["side"] == "SHORT" and current["high"] >= mid)
                )
                structure_broken = (
                    (pe["side"] == "LONG"  and current["close"] < sl) or
                    (pe["side"] == "SHORT" and current["close"] > sl)
                )
                zone_low  = pe.get("zone_low")
                zone_high = pe.get("zone_high")
                ob_invalidated = (
                    (pe["side"] == "LONG"  and zone_low  is not None and current["close"] < zone_low) or
                    (pe["side"] == "SHORT" and zone_high is not None and current["close"] > zone_high)
                )
                timed_out = pe["age"] >= LIMIT_ORDER_TIMEOUT_CANDLES

                cancel_reason: Optional[str] = None

                if filled:
                    self._open_trades.append(BacktestTrade(
                        pe["signal"], pe["risk_out"], mid, pe["signal_time"]
                    ))
                    if self.enable_tracker and pe.get("tracker"):
                        pe["tracker"]["order_placed"] = True
                        pe["tracker"]["entry_price"]  = mid
                        pe["tracker"]["stop_reason"]  = None
                        pe["tracker"]["order_type"]   = "LMT_FILL"  # VARCHAR(10) safe
                        self._tracker_records.append(pe["tracker"])
                    self._pending_entry = None
                elif structure_broken:
                    cancel_reason = "struct_break"
                elif ob_invalidated:
                    cancel_reason = "ob_invalid"
                elif timed_out:
                    cancel_reason = "lmt_timeout"

                if cancel_reason:
                    logger.debug(
                        f"[{self.symbol}] LIMIT cancelled ({cancel_reason}) "
                        f"age={pe['age']}"
                    )
                    if self.enable_tracker and pe.get("tracker"):
                        pe["tracker"]["order_placed"] = False
                        pe["tracker"]["stop_reason"]  = cancel_reason
                        self._tracker_records.append(pe["tracker"])
                    self._pending_entry = None

            # ── CHG-BT-002: Update open trades + _just_closed flag ──────────────
            # _just_closed ngăn re-entry cùng candle — giống live (close = tick event,
            # signal mới chỉ fire candle tiếp theo).
            _just_closed = False
            for trade in list(self._open_trades):
                pnl = self._update_trade(trade, current)
                if pnl is not None:
                    balance += pnl
                    self._risk.register_pnl(pnl)
                    self._equity.append({"time": current["open_time"], "balance": balance})
                    self._open_trades.remove(trade)
                    _just_closed = True

            # News filter — skip signal nếu gần high-impact event
            if self._news_filter and self._news_filter.is_high_impact_window(current["open_time"]):
                continue

            # ── Check for new entry ───────────────────────────────────────────────
            # Điều kiện: không trade mở, candle này chưa đóng trade (CHG-BT-002),
            # risk engine cho phép.
            # CHG-BT-004b: Nếu LIMIT pending cho side X, vẫn cho phép check side Y
            # (opposite direction MARKET — giống Live cho phép 2 vị thế).
            _pending_side = self._pending_entry["side"] if self._pending_entry else None
            if (len(self._open_trades) < self._max_open and not _just_closed and self._risk.trading_enabled):
                for side in ("LONG", "SHORT"):
                    if _pending_side is not None and side == _pending_side:
                        continue  # CHG-BT-004b: skip — cùng direction với pending LIMIT
                    entry_zone = build_entry_zone(side, self._fvgs, self._obs, confluence,
                                                  current_price=current_price, atr=atr)

                    # ── Build base tracker record ──────────────────────
                    last_bos = struct["bos_events"][-1] if struct.get("bos_events") else None
                    tracker = {
                        "symbol":          self.symbol,
                        "timeframe":       self.timeframe,
                        "candle_time":     current["open_time"],
                        "side":            side,
                        "trend":           struct.get("trend"),
                        "last_swing_high": struct.get("last_swing_high"),
                        "last_swing_low":  struct.get("last_swing_low"),
                        "bos_type":        last_bos["type"] if last_bos else None,
                        "sweep_type":      liq_output["last_sweep"]["type"] if liq_output.get("last_sweep") else None,
                        "choch_type":      liq_output["last_choch"]["type"] if liq_output.get("last_choch") else None,
                        "mtf_bias":        liq_output.get("mtf_bias"),
                        "zone_type":       entry_zone["source"] if entry_zone else None,
                        "zone_low":        entry_zone["low"] if entry_zone else None,
                        "zone_high":       entry_zone["high"] if entry_zone else None,
                    }

                    if entry_zone is None:
                        tracker["stop_reason"] = "no_zone"
                        if self.enable_tracker:
                            self._tracker_records.append(tracker)
                        continue

                    risk_out = self._risk.evaluate(side, self.symbol, entry_zone["midpoint"], window, struct, liq_zones)
                    if risk_out is None:
                        tracker["stop_reason"] = "risk_rejected"
                        tracker["l6_risk"] = False
                        if self.enable_tracker:
                            self._tracker_records.append(tracker)
                        continue

                    tracker.update({
                        "l6_risk":    True,
                        "sl":         risk_out.get("sl"),
                        "tp1":        risk_out["tp"][0]["level"] if risk_out.get("tp") else None,
                        "rr":         risk_out.get("rr"),
                    })

                    signal = self._entry_engine.evaluate(window, struct, liq_output, entry_zone, risk_out)

                    # Pick up layer debug from entry engine
                    dbg = self._entry_engine.last_eval_debug
                    tracker.update({
                        "l1_trend":      dbg.get("l1_trend"),
                        "l2_zone_touch": dbg.get("l2_zone_touch"),
                        "l3_liquidity":  dbg.get("l3_liquidity"),
                        "l4_volume":     dbg.get("l4_volume"),
                        "l5_trigger":    dbg.get("l5_trigger"),
                        "stop_reason":   dbg.get("stop_reason"),
                    })

                    all_pass = (
                        dbg.get("l1_trend") is True and
                        dbg.get("l2_zone_touch") is True and
                        dbg.get("l3_liquidity") is True and
                        dbg.get("l4_volume") is True and
                        dbg.get("l5_trigger") is not None and
                        tracker.get("l6_risk") is True
                    )
                    tracker["eligible"] = all_pass

                    if signal:
                        if not risk_out.get("position_size") or risk_out["position_size"] <= 0:
                            tracker["stop_reason"] = "zero_size"
                            if self.enable_tracker:
                                self._tracker_records.append(tracker)
                            continue

                        raw_price  = entry_zone["midpoint"]
                        slip       = raw_price * self.slippage * (1 if side == "LONG" else -1)
                        entry_price = raw_price + slip
                        entry_type  = signal.get("entry_type", "MARKET")

                        if entry_type == "LIMIT":
                            # CHG-BT-004c: Không đặt 2 LIMIT đồng thời
                            # (pending_side đã được filter ở trên nên đây là opposite side,
                            # nhưng vẫn check phòng edge case)
                            if self._pending_entry is not None:
                                tracker["stop_reason"] = "lmt_already_pending"
                                if self.enable_tracker:
                                    self._tracker_records.append(tracker)
                                break
                            # CHG-BT-001: LIMIT — không fill ngay, đặt pending
                            self._pending_entry = {
                                "signal":      signal,
                                "risk_out":    risk_out,
                                "entry_price": entry_price,
                                "side":        side,
                                "age":         0,
                                "signal_time": current["open_time"],
                                "zone_low":    entry_zone["low"],   # CHG-BT-003
                                "zone_high":   entry_zone["high"],  # CHG-BT-003
                                "tracker":     None,
                            }
                            tracker.update({
                                "signal_side":  side,
                                "order_placed": False,
                                "order_type":   "LIMIT",
                                "entry_price":  entry_price,
                                "stop_reason":  "lmt_pending",
                                "eligible":     True,
                            })
                            # Không append ngay — append khi fill/cancel
                            self._pending_entry["tracker"] = dict(tracker)
                        else:
                            # MARKET — fill ngay
                            self._open_trades.append(BacktestTrade(signal, risk_out, entry_price, current["open_time"]))
                            tracker.update({
                                "signal_side":  side,
                                "order_placed": True,
                                "order_type":   "MARKET",
                                "entry_price":  entry_price,
                                "stop_reason":  None,
                                "eligible":     True,
                            })
                            if self.enable_tracker:
                                self._tracker_records.append(tracker)

                        break
                    else:
                        if self.enable_tracker:
                            self._tracker_records.append(tracker)

        # Close any remaining open trades at last price
        for trade in self._open_trades:
            last = candles[-1]
            trade.exit_price = last["close"]
            trade.exit_time = last["open_time"]
            trade.status = "CLOSED"
            pnl = self._calc_pnl(trade)
            trade.pnl = pnl
            self._trades.append(trade)
        self._open_trades.clear()

        # Discard unfilled LIMIT pending khi hết data
        if self._pending_entry is not None:
            if self.enable_tracker and self._pending_entry.get("tracker"):
                t = self._pending_entry["tracker"]
                t["order_placed"] = False
                t["stop_reason"]  = "lmt_eob"
                self._tracker_records.append(t)
            self._pending_entry = None

        # Update tracker records with trade outcomes
        if self.enable_tracker:
            self._fill_tracker_outcomes()

        results = self._compute_results()
        return results

    def _fill_tracker_outcomes(self):
        """Match closed trades to tracker records and fill outcome columns."""
        for trade in self._trades:
            for rec in self._tracker_records:
                if (rec.get("order_placed") and
                    rec.get("symbol") == trade.signal.get("symbol", self.symbol) and
                    rec.get("candle_time") == trade.candle_time and
                    rec.get("side") == trade.side):
                    rec["trade_closed"] = True
                    rec["exit_price"]   = trade.exit_price
                    rec["pnl"]          = round(trade.pnl, 4)
                    rec["exit_reason"]  = trade.status
                    break

    def _update_trade(self, trade: BacktestTrade, candle: dict) -> Optional[float]:
        """Check if SL or TP hit on this candle. Return PnL if closed, else None."""
        side = trade.side
        sl = trade.sl
        tps = trade.tps

        entry = trade.entry_price
        sl_dist = abs(entry - sl)

        if side == "LONG":
            # Track peak price (for trailing stop after BE)
            if candle["high"] > trade.peak_price:
                trade.peak_price = candle["high"]

            # Breakeven: move SL to entry at 1R
            # 0.7R was too aggressive — XAUUSD pullbacks often touch entry after 0.7R
            # causing TP trades to exit at BE instead of reaching 2R.
            if not trade.be_set and candle["high"] >= entry + sl_dist:
                trade.sl = entry
                trade.be_set = True
                sl = trade.sl

            # Trailing stop: after BE (1R), when peak reaches 1.3R → trail SL to peak - 0.4R
            # 1.3R activation: sweet spot — captures reversal without early-exiting TP runs
            if trade.be_set and trade.peak_price >= entry + sl_dist * 1.3:
                trail_level = trade.peak_price - sl_dist * 0.4
                if trail_level > trade.sl:
                    trade.sl = trail_level
                    sl = trade.sl

            # TP hit first — check before SL to prioritise full target
            if tps and candle["high"] >= tps[trade.tp_index]["level"]:
                trade.exit_price = tps[trade.tp_index]["level"]
                trade.exit_time  = candle["open_time"]
                trade.status = "TP"
                trade.pnl = self._calc_pnl(trade)
                self._trades.append(trade)
                return trade.pnl

            # SL hit (original SL, BE at entry, or trailing stop above entry)
            if candle["low"] <= sl:
                trade.exit_price = sl
                trade.exit_time  = candle["open_time"]
                if sl > entry:
                    trade.status = "TP"   # trailing stop above entry = profit
                elif trade.be_set and sl == entry:
                    trade.status = "BE"
                else:
                    trade.status = "SL"
                trade.pnl = self._calc_pnl(trade)
                self._trades.append(trade)
                return trade.pnl

        elif side == "SHORT":
            # Track peak price (SHORT: favorable direction is DOWN, track lowest)
            if candle["low"] < trade.peak_price:
                trade.peak_price = candle["low"]

            # Breakeven at 1R
            if not trade.be_set and candle["low"] <= entry - sl_dist:
                trade.sl = entry
                trade.be_set = True
                sl = trade.sl

            # Trailing stop: after BE (1R), when peak reaches 1.3R → trail SL to peak + 0.4R
            if trade.be_set and trade.peak_price <= entry - sl_dist * 1.3:
                trail_level = trade.peak_price + sl_dist * 0.4
                if trail_level < trade.sl:
                    trade.sl = trail_level
                    sl = trade.sl

            # TP hit first (full 2R)
            if tps and candle["low"] <= tps[trade.tp_index]["level"]:
                trade.exit_price = tps[trade.tp_index]["level"]
                trade.exit_time  = candle["open_time"]
                trade.status = "TP"
                trade.pnl = self._calc_pnl(trade)
                self._trades.append(trade)
                return trade.pnl

            # SL hit (original, BE, or trailing stop below entry)
            if candle["high"] >= sl:
                trade.exit_price = sl
                trade.exit_time  = candle["open_time"]
                if sl < entry:
                    trade.status = "TP"   # trailing stop below entry = profit
                elif trade.be_set and sl == entry:
                    trade.status = "BE"
                else:
                    trade.status = "SL"
                trade.pnl = self._calc_pnl(trade)
                self._trades.append(trade)
                return trade.pnl

        return None

    def _calc_pnl(self, trade: BacktestTrade) -> float:
        """Phase 7.8: Forex PnL.
        No exchange fees — cost is bid/ask spread at entry (~1 pip).
        Full exit at TP (2R) or SL/BE. No partial exit.

        USD-quote pairs (EURUSD, GBPUSD, XAUUSD …):
          gross = price_change × units   (already in USD)
          spread_cost = entry × SPREAD_COST_PCT × units

        Non-USD-quote pairs (USDJPY, EURJPY, USDCAD …):
          price_change is in quote currency → convert: gross = price_change × units / entry
          spread_cost = SPREAD_COST_PCT × units   (~1 pip in USD terms)
        """
        if trade.exit_price is None:
            return 0.0
        symbol = trade.signal.get("symbol", "EURUSD")
        direction = 1 if trade.side == "LONG" else -1
        price_change = (trade.exit_price - trade.entry_price) * direction

        _USD_QUOTE = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "EURGBP", "XAUUSD", "XAGUSD"}
        if symbol not in _USD_QUOTE and trade.entry_price > 0:
            gross = price_change * trade.position_size / trade.entry_price
            spread_cost = SPREAD_COST_PCT * trade.position_size
        else:
            gross = price_change * trade.position_size
            spread_cost = trade.entry_price * SPREAD_COST_PCT * trade.position_size

        return round(gross - spread_cost, 4)

    def _compute_results(self) -> Dict:
        """Phase 7.10: Performance metrics."""
        from phase7_backtest.performance_metrics import compute_metrics
        return compute_metrics(self._trades, self.initial_balance, self._equity)

    @property
    def trades(self) -> List[BacktestTrade]:
        return self._trades

    @property
    def equity_curve(self) -> List[Dict]:
        return self._equity
