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
from config.settings import (
    LIMIT_ORDER_TIMEOUT_CANDLES,
    ADX_1H_FILTER_ENABLED, ADX_1H_MIN, ADX_1H_MIN_OVERRIDE,
    MARKET_ORDERS_ENABLED,
)
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
from phase5_entry.entry_engine import calc_adx


# ─────────────────────────────────────────────────────────────
# REALISTIC FEE MODEL — ICMarkets Raw Spread (as of 2024)
# ─────────────────────────────────────────────────────────────
# 1. Commission: $3.5/lot/side → $7/lot round-trip
#    Per unit (oz for XAU): $7 / contract_size
# 2. Spread: typical bid/ask at entry (per unit in price terms)
# 3. Slippage: entry + exit (market impact, especially on SL)
# ─────────────────────────────────────────────────────────────

TAKER_FEE    = 0.0      # no percentage taker fee for Forex (use commission below)
MAKER_FEE    = 0.0

# Slippage: applied at entry AND exit (SL fill can slip more than TP)
SLIPPAGE_PCT         = 0.00005   # entry slippage ~0.5 pip
TP_SLIPPAGE_PCT      = 0.0       # TP = limit order → fill đúng giá, không slip
SL_SLIPPAGE_PCT      = 0.0001    # SL = stop→market order → slip ~0.5pt tại $4640
EXIT_SLIPPAGE_PCT    = 0.00003   # fallback (BE, manual close)

# Spread cost at entry (bid/ask): per unit in price terms
# XAUUSD: ~$0.20/oz → at $2500 → pct = 0.20/2500 = 0.00008
# FX pairs: ~1 pip → 0.00010
SPREAD_COST_PCT = 0.00010   # default (FX pairs)

# Commission per lot ROUND-TRIP (entry + exit combined), per symbol
# ICMarkets Raw: $3.5/lot/side × 2 = $7/lot round-trip
# Contract size (units per lot): XAUUSD=100oz, XAGUSD=5000oz, FX=100000
_COMMISSION_PER_LOT_RT: dict = {
    "XAUUSD": 7.0,   # $7/lot round-trip
    "XAGUSD": 7.0,
    "EURUSD": 7.0,
    "GBPUSD": 7.0,
    "USDJPY": 7.0,
    "AUDUSD": 7.0,
    "USDCAD": 7.0,
    "USDCHF": 7.0,
}
_CONTRACT_SIZE: dict = {
    "XAUUSD": 100,      # 100 oz per lot
    "XAGUSD": 5_000,    # 5000 oz per lot
}  # FX default = 100_000

# Spread override per symbol (in price units, per unit of position)
# XAUUSD: $0.20/oz → spread_per_unit = 0.20
# FX: use SPREAD_COST_PCT × entry_price
_SPREAD_PER_UNIT: dict = {
    "XAUUSD": 0.20,   # $0.20 per oz
    "XAGUSD": 0.005,  # $0.005 per oz
}


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
        self.orig_sl_dist: float = abs(entry_price - risk["sl"])  # gốc, không đổi dù SL dời

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

        # CHG-BT-006: Concurrent trades — đọc từ settings (sync với live)
        self._open_trades: List[BacktestTrade] = []
        from config.settings import MAX_OPEN_POSITIONS as _MAX_OPEN
        self._max_open = _MAX_OPEN
        # CHG-BT-001: LIMIT pending state
        # Khi entry_type == "LIMIT", không fill ngay — lưu vào đây,
        # fill ở candle sau khi giá chạm midpoint.
        self._pending_entry: Optional[Dict] = None
        self._trades: List[BacktestTrade] = []
        self._equity: List[Dict] = []
        self._fvgs: List[Dict] = []
        self._obs: List[Dict] = []

        # Anti-Martingale: track consecutive wins
        from config.settings import (ANTI_MARTINGALE_ENABLED, ANTI_MARTINGALE_STEP,
                                     ANTI_MARTINGALE_CAP)
        self._am_enabled  = ANTI_MARTINGALE_ENABLED
        self._am_step     = ANTI_MARTINGALE_STEP
        self._am_cap      = ANTI_MARTINGALE_CAP
        self._am_wins     = 0   # consecutive win counter

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

    def _get_1h_adx(self) -> float:
        """
        Tính ADX(14) từ các nến 1h đã đóng tính đến thời điểm hiện tại.
        Dùng self._idx_1h làm boundary — chỉ dùng candles đã advance (đã đóng).
        Trả về 0.0 nếu chưa đủ data.
        """
        if not self._candles_1h or self._idx_1h < 28:   # cần ít nhất 2×period
            return 0.0
        window = self._candles_1h[max(0, self._idx_1h - 100): self._idx_1h]
        return calc_adx(window, period=14)

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
                    # Anti-Martingale: update consecutive win counter
                    if self._am_enabled:
                        if pnl > 0:
                            self._am_wins += 1
                        else:
                            self._am_wins = 0

            # News filter — skip signal nếu gần high-impact event
            if self._news_filter and self._news_filter.is_high_impact_window(current["open_time"]):
                continue

            # ── ADX 1H Regime Filter ─────────────────────────────────────────────
            # Chỉ dùng candles 1h đã đóng (advance bởi _advance_mtf ở trên).
            # Nếu ADX 1h < threshold → macro sideways → skip toàn bộ entry check.
            _adx_1h = 0.0
            if ADX_1H_FILTER_ENABLED and self._candles_1h:
                _adx_1h = self._get_1h_adx()
                _adx_1h_min = ADX_1H_MIN_OVERRIDE.get(self.symbol, ADX_1H_MIN)
                if _adx_1h > 0 and _adx_1h < _adx_1h_min:
                    logger.debug(
                        f"[{self.symbol}] ADX_1H={_adx_1h:.1f} < {_adx_1h_min} "
                        f"(macro ranging) → skip entry @ {current['open_time']}"
                    )
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
                        "balance":         round(balance, 2),
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

                    # Anti-Martingale: dynamic risk_pct
                    if self._am_enabled:
                        from config.settings import RISK_PER_TRADE_OVERRIDE, RISK_PER_TRADE
                        _base_risk = RISK_PER_TRADE_OVERRIDE.get(self.symbol, RISK_PER_TRADE)
                        _am_risk = min(_base_risk + self._am_wins * self._am_step, self._am_cap)
                        self._risk._am_override_risk = _am_risk
                    else:
                        from config.settings import RISK_PER_TRADE_OVERRIDE, RISK_PER_TRADE
                        _am_risk = RISK_PER_TRADE_OVERRIDE.get(self.symbol, RISK_PER_TRADE)
                        self._risk._am_override_risk = None
                    tracker["risk_pct"] = round(_am_risk * 100, 2)  # lưu dạng % (1.0, 1.5, 2.0...)
                    risk_out = self._risk.evaluate(side, self.symbol, entry_zone["midpoint"], window, struct, liq_zones)
                    if risk_out is None:
                        tracker["stop_reason"] = "risk_rejected"
                        tracker["l6_risk"] = False
                        if self.enable_tracker:
                            self._tracker_records.append(tracker)
                        continue

                    _sl  = risk_out.get("sl")
                    _tp1 = risk_out["tp"][0]["level"] if risk_out.get("tp") else None
                    _entry_mid = entry_zone["midpoint"]
                    _sl_dist  = round(abs(_entry_mid - _sl), 5) if _sl else None
                    _tp_dist  = round(abs(_tp1 - _entry_mid), 5) if _tp1 else None
                    _lots     = round(risk_out.get("position_size", 0) / 100, 4) if risk_out.get("position_size") else None
                    tracker.update({
                        "l6_risk":    True,
                        "sl":         _sl,
                        "tp1":        _tp1,
                        "rr":         risk_out.get("rr"),
                        "sl_dist":    _sl_dist,
                        "tp_dist":    _tp_dist,
                        "lots":       _lots,
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

                        entry_type  = signal.get("entry_type", "MARKET")

                        # MARKET disabled toàn hệ thống → skip, chỉ cho phép LIMIT
                        if entry_type == "MARKET" and not MARKET_ORDERS_ENABLED:
                            tracker["stop_reason"] = "market_disabled"
                            if self.enable_tracker:
                                self._tracker_records.append(tracker)
                            continue

                        if entry_type == "MARKET":
                            # MARKET: fill tại bar close — giống live.
                            # Live: signal fire cuối nến, MARKET order fill ở tick tiếp theo ≈ bar close.
                            # SL/TP giữ nguyên absolute prices từ risk engine (tính từ midpoint).
                            # Hệ quả: SL dist từ fill < SL dist từ midpoint → stop-out nhiều hơn.
                            # Đây là behavior ĐÚNG — MARKET orders thực tế kém LIMIT orders.
                            raw_price = current["close"]
                        else:
                            # LIMIT: fill tại zone midpoint (price phải return về midpoint).
                            # Giống live: LIMIT order chờ price chạm midpoint mới khớp.
                            raw_price = entry_zone["midpoint"]
                        slip        = raw_price * self.slippage * (1 if side == "LONG" else -1)
                        entry_price = raw_price + slip

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
        sl_dist = trade.orig_sl_dist  # dùng sl_dist gốc — tránh = 0 sau khi BE set

        tp_hit = tps and (
            (side == "LONG"  and candle["high"] >= tps[trade.tp_index]["level"]) or
            (side == "SHORT" and candle["low"]  <= tps[trade.tp_index]["level"])
        )
        sl_hit = (
            (side == "LONG"  and candle["low"]  <= sl) or
            (side == "SHORT" and candle["high"] >= sl)
        )

        # Khi cả TP và SL đều trong range 1 nến → dùng hướng nến để quyết định
        # Nến bullish (close > open): giá lên trước → LONG TP / SHORT SL wins
        # Nến bearish (close < open): giá xuống trước → LONG SL / SHORT TP wins
        # Realistic hơn so với luôn check TP trước (inflate WR)
        candle_bullish = candle["close"] >= candle["open"]
        if tp_hit and sl_hit:
            if side == "LONG":
                tp_first = candle_bullish
            else:
                tp_first = not candle_bullish
        else:
            tp_first = tp_hit

        if side == "LONG":
            if candle["high"] > trade.peak_price:
                trade.peak_price = candle["high"]
        elif side == "SHORT":
            if candle["low"] < trade.peak_price:
                trade.peak_price = candle["low"]

        if tp_first and tp_hit:
            trade.exit_price = tps[trade.tp_index]["level"]
            trade.exit_time  = candle["open_time"]
            trade.status = "TP"
            trade.pnl = self._calc_pnl(trade)
            self._trades.append(trade)
            return trade.pnl

        if sl_hit:
            trade.exit_price = sl
            trade.exit_time  = candle["open_time"]
            if (side == "LONG" and sl > entry) or (side == "SHORT" and sl < entry):
                trade.status = "TP"   # trailing stop in profit
            elif trade.be_set and sl == entry:
                trade.status = "BE"
            else:
                trade.status = "SL"
            trade.pnl = self._calc_pnl(trade)
            self._trades.append(trade)
            return trade.pnl

        if tp_hit:
            trade.exit_price = tps[trade.tp_index]["level"]
            trade.exit_time  = candle["open_time"]
            trade.status = "TP"
            trade.pnl = self._calc_pnl(trade)
            self._trades.append(trade)
            return trade.pnl

        return None

    def _calc_pnl(self, trade: BacktestTrade) -> float:
        """Phase 7.8: Forex PnL — Realistic fee model (ICMarkets Raw).

        Fees deducted:
          1. Spread at entry  : bid/ask cost (per unit, symbol-specific)
          2. Commission RT    : $7/lot round-trip (entry + exit combined)
          3. Exit slippage    : ~0.3 pip additional on exit fill

        USD-quote pairs (EURUSD, GBPUSD, XAUUSD …):
          gross = price_change × units   (already in USD)
        Non-USD-quote pairs (USDJPY, USDCAD …):
          gross = price_change × units / entry_price
        """
        if trade.exit_price is None:
            return 0.0
        symbol   = trade.signal.get("symbol", "EURUSD")
        direction = 1 if trade.side == "LONG" else -1
        units    = trade.position_size

        # ── Exit slippage: TP=limit(no slip), SL=stop→market(slip) ──
        _exit_status = getattr(trade, "status", "") or ""
        if "TP" in _exit_status:
            _slip_pct = TP_SLIPPAGE_PCT
        elif "SL" in _exit_status:
            _slip_pct = SL_SLIPPAGE_PCT
        else:
            _slip_pct = EXIT_SLIPPAGE_PCT
        exit_slip = trade.exit_price * _slip_pct * (-direction)
        adj_exit  = trade.exit_price + exit_slip

        price_change = (adj_exit - trade.entry_price) * direction

        _USD_QUOTE = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "EURGBP", "XAUUSD", "XAGUSD"}
        if symbol not in _USD_QUOTE and trade.entry_price > 0:
            gross = price_change * units / trade.entry_price
        else:
            gross = price_change * units

        # ── 1. Spread cost at entry ──────────────────────────────────
        if symbol in _SPREAD_PER_UNIT:
            # Per-unit override (XAUUSD: $0.20/oz, XAGUSD: $0.005/oz)
            spread_cost = _SPREAD_PER_UNIT[symbol] * units
        elif symbol in _USD_QUOTE:
            # USD-quote FX (EURUSD, GBPUSD...): price ≈ 1.0 → entry × pct × units ≈ $1/pip
            spread_cost = trade.entry_price * SPREAD_COST_PCT * units
        else:
            # Non-USD-quote (USDJPY, USDCAD, USDCHF...): price in foreign currency
            # spread in USD = SPREAD_COST_PCT × units (not × entry_price to avoid ×150 blowup)
            # ~1 pip USD equivalent per unit, consistent with old formula
            spread_cost = SPREAD_COST_PCT * units

        # ── 2. Commission round-trip ─────────────────────────────────
        contract = _CONTRACT_SIZE.get(symbol, 100_000)
        lots     = units / contract
        comm_rt  = _COMMISSION_PER_LOT_RT.get(symbol, 7.0) * lots

        total_cost = spread_cost + comm_rt
        return round(gross - total_cost, 4)

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
