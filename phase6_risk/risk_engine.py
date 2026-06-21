"""
Phase 6 — Forex Risk Engine.
SL/TP calculation, position sizing (OANDA units), pip value, drawdown protection.

KEY FOREX DIFFERENCES vs OKX:
  1. Position size in "units" (OANDA), not contracts
     - 1 standard lot = 100,000 units
     - OANDA supports fractional units (e.g., 50,000 = 0.5 lot)
  2. PnL calculation uses pip value per pair, not USD/contract
     - EUR/USD: 1 pip = $10 per standard lot (for USD account)
     - USD/JPY: 1 pip = ~$6.25 per standard lot (varies with USDJPY rate)
     - XAU/USD: 1 pip = $1 per 100 units
  3. SL buffer in pips (absolute), not percentage
  4. No funding rates
  5. Market hours: Mon-Fri only (weekend position risk)
"""
from typing import List, Optional, Dict
import numpy as np
from utils.logger import logger
from config.settings import (
    RISK_PER_TRADE, MAX_DAILY_LOSS, MAX_DRAWDOWN,
    MIN_RR, SL_BUFFER, MAX_LEVERAGE, PIP_SIZE
)


def get_pip_size(symbol: str) -> float:
    """Return the pip size for a Forex symbol."""
    return PIP_SIZE.get(symbol, 0.0001)


def calc_pip_value_usd(symbol: str, lot_size: float, account_ccy: str = "USD") -> float:
    """
    Calculate pip value in USD per lot for major pairs with USD account.
    For simplicity, returns approximate value (exact value requires live quote for cross pairs).

    Rules:
      - Pair ends in USD (EURUSD, GBPUSD, AUDUSD, NZDUSD): pip_value = pip_size × lot_size × 1
      - Pair starts with USD (USDJPY, USDCAD, USDCHF): pip_value = pip_size × lot_size / quote_rate
        (approximated as 1/rate; use ~1.0 simplification unless live rate available)
      - XAU/USD: 1 pip ($0.01) × units/100 per standard lot
    """
    pip = get_pip_size(symbol)
    if symbol in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "EURGBP"):
        # Quote currency = USD: pip value = pip × lot
        return pip * lot_size
    elif symbol in ("USDJPY", "USDCAD", "USDCHF"):
        # Quote currency ≠ USD: approximate pip value (simplified without live cross rate)
        # USDJPY at ~150: 0.01 × 100000 / 150 ≈ $6.67 per standard lot
        # Use 1.0 as approximation — live engine should update with real rate
        return pip * lot_size  # simplified; override in live engine with actual cross rate
    elif symbol == "XAUUSD":
        return 0.01 * lot_size / 100.0  # Gold: $0.01 per pip per 100 units
    else:
        return pip * lot_size


class ForexRiskEngine:
    """
    Forex Risk Engine — OANDA units-based position sizing.
    Replaces OKX RiskEngine for Forex project.
    """

    def __init__(self, account_balance: float = 10_000.0):
        self.account_balance = account_balance
        self.daily_pnl: float = 0.0
        self.peak_balance: float = account_balance
        self._day_start_balance: float = account_balance
        self.trading_enabled: bool = True
        self._consecutive_losses: int = 0

    # ─────────────────────────────────────────
    # SL CALCULATION
    # ─────────────────────────────────────────
    def calc_sl(self, side: str, symbol: str,
                last_swing_high: Optional[float],
                last_swing_low: Optional[float],
                candles: List[dict],
                entry: Optional[float] = None) -> Optional[float]:
        """
        SL = beyond swing level by SL_BUFFER pips.
        Falls back to 2×ATR if no swing available.

        SL_BUFFER in settings is a ratio (0.0003 = 0.03%).
        For Forex, we convert to pip-based buffer:
          buffer_pips = max(3 pips, 0.03% of price)

        Khi entry được cung cấp: nếu swing-based SL rơi sai phía entry
        (vd SHORT mà sl <= entry, do last_swing_high < entry zone midpoint),
        tự động fallback sang ATR-based SL để đảm bảo SL luôn hợp lệ.
        """
        pip = get_pip_size(symbol)
        atr = _calc_atr(candles)

        if side == "LONG":
            level = last_swing_low
            if level:
                buffer = max(5 * pip, level * SL_BUFFER)
                sl = round(level - buffer, 6)
            else:
                sl = round(candles[-1]["close"] - atr * 2, 6)
            if entry is not None and sl >= entry:
                logger.debug(f"calc_sl LONG [{symbol}]: swing sl={sl:.6f} >= entry={entry:.6f} — fallback ATR")
                sl = round(entry - atr * 2, 6)
            return sl

        elif side == "SHORT":
            level = last_swing_high
            if level:
                buffer = max(5 * pip, level * SL_BUFFER)
                sl = round(level + buffer, 6)
            else:
                sl = round(candles[-1]["close"] + atr * 2, 6)
            if entry is not None and sl <= entry:
                logger.debug(f"calc_sl SHORT [{symbol}]: swing sl={sl:.6f} <= entry={entry:.6f} — fallback ATR")
                sl = round(entry + atr * 2, 6)
            return sl

        return None

    # ─────────────────────────────────────────
    # TP CALCULATION
    # ─────────────────────────────────────────
    def calc_tp(self, side: str, entry: float, sl: float,
                liquidity_zones: List[Dict]) -> List[Dict]:
        """
        Multi-level TP: TP1=2R, TP2=2.5R or liquidity, TP3=4R or liquidity.
        Split: 50% / 30% / 20%.
        """
        sl_dist = abs(entry - sl)
        if sl_dist <= 0:
            return []

        tps = []
        sizes = [0.5, 0.3, 0.2]

        tp1 = entry + sl_dist * 2.0 if side == "LONG" else entry - sl_dist * 2.0
        tps.append({"level": round(tp1, 6), "rr": 2.0, "size_ratio": sizes[0]})

        liq_tps = _find_liquidity_targets(side, entry, liquidity_zones)
        liq2 = next((lvl for lvl in liq_tps
                     if abs(lvl - entry) / sl_dist >= 2.0), None)
        if liq2:
            tps.append({"level": round(liq2, 6),
                        "rr": round(abs(liq2 - entry) / sl_dist, 2),
                        "size_ratio": sizes[1]})
        else:
            tp2 = entry + sl_dist * 2.5 if side == "LONG" else entry - sl_dist * 2.5
            tps.append({"level": round(tp2, 6), "rr": 2.5, "size_ratio": sizes[1]})

        liq3 = next((lvl for lvl in liq_tps
                     if abs(lvl - entry) / sl_dist >= 3.5), None)
        if liq3:
            tps.append({"level": round(liq3, 6),
                        "rr": round(abs(liq3 - entry) / sl_dist, 2),
                        "size_ratio": sizes[2]})
        else:
            tp3 = entry + sl_dist * 4.0 if side == "LONG" else entry - sl_dist * 4.0
            tps.append({"level": round(tp3, 6), "rr": 4.0, "size_ratio": sizes[2]})

        return tps

    # ─────────────────────────────────────────
    # POSITION SIZING — OANDA UNITS
    # ─────────────────────────────────────────
    def calc_position_size(self, symbol: str, entry: float, sl: float,
                            risk_pct: float = RISK_PER_TRADE) -> float:
        """
        Position size in OANDA units.

        Formula:
          risk_amount = account_balance × risk_pct
          sl_pips = |entry - sl| / pip_size
          pip_value_per_unit = pip_size × 1   (for USD-quote pairs like EURUSD)
          units = risk_amount / (sl_pips × pip_value_per_unit)

        Simplified for USD-account, USD-quote pairs:
          units = risk_amount / |entry - sl|

        This is identical to OKX formula — works because OANDA units are
        directly priced in the quote currency (USD for most majors).

        Safety:
          - Minimum SL distance = 3 pips
          - Maximum units = account × MAX_LEVERAGE / entry
          - Round to nearest unit
        """
        if sl <= 0 or entry <= 0 or self.account_balance <= 0:
            return 0.0

        pip = get_pip_size(symbol)
        sl_distance = abs(entry - sl)
        min_sl = 3 * pip

        if sl_distance < min_sl:
            logger.debug(f"[{symbol}] SL too close ({sl_distance:.6f} < {min_sl:.6f}) → reject")
            return 0.0

        risk_amount = self.account_balance * risk_pct
        units = risk_amount / sl_distance

        # Cap: no more than MAX_LEVERAGE × balance notional
        max_units = (self.account_balance * MAX_LEVERAGE) / entry
        units = min(units, max_units)

        return round(units)  # OANDA accepts integer units

    # ─────────────────────────────────────────
    # FULL RISK EVALUATION
    # ─────────────────────────────────────────
    def evaluate(self, side: str, symbol: str, entry: float,
                 candles: List[dict],
                 structure_output: Dict,
                 liquidity_zones: List[Dict]) -> Optional[Dict]:
        """
        Full risk evaluation. Returns None if any risk filter fails.
        Returns dict with sl, tp, position_size, rr.
        """
        if not self.trading_enabled:
            logger.warning("Trading disabled by risk engine")
            return None

        sl = self.calc_sl(side, symbol,
                          structure_output.get("last_swing_high"),
                          structure_output.get("last_swing_low"),
                          candles,
                          entry=entry)
        if sl is None:
            return None

        tps = self.calc_tp(side, entry, sl, liquidity_zones)
        if not tps:
            return None

        position_size = self.calc_position_size(symbol, entry, sl)
        if position_size <= 0:
            return None

        sl_dist = abs(entry - sl)
        rr = abs(tps[0]["level"] - entry) / sl_dist if sl_dist > 0 else 0

        if rr < MIN_RR:
            logger.debug(f"[{symbol}] RR={rr:.2f} < {MIN_RR} → reject")
            return None

        atr = _calc_atr(candles)
        if sl_dist > atr * 4:
            logger.debug(f"[{symbol}] SL too wide ({sl_dist:.6f} > {atr*4:.6f}) → reject")
            return None

        return {
            "sl":            round(sl, 6),
            "tp":            tps,
            "risk":          RISK_PER_TRADE,
            "position_size": position_size,
            "rr":            round(rr, 2),
            "management": {
                "breakeven_at_1r": True,
                "trailing":        True,
            }
        }

    # ─────────────────────────────────────────
    # TRADE MANAGEMENT
    # ─────────────────────────────────────────
    def check_breakeven(self, position: Dict, current_price: float) -> Optional[float]:
        """Move SL to breakeven when price reaches 1R."""
        entry = position["entry"]
        sl    = position["sl"]
        side  = position["side"]
        r1    = abs(entry - sl)
        if side == "LONG" and current_price >= entry + r1:
            return entry
        if side == "SHORT" and current_price <= entry - r1:
            return entry
        return None

    def check_trailing_stop(self, position: Dict, candles: List[dict]) -> Optional[float]:
        """Trail SL behind recent swing lows (LONG) or highs (SHORT)."""
        if not candles:
            return None
        side       = position["side"]
        current_sl = position["sl"]
        current_price = position.get("current_price") or candles[-1]["close"]
        symbol = position.get("symbol", "EURUSD")
        pip    = get_pip_size(symbol)

        if side == "LONG":
            recent_lows = [c["low"] for c in candles[-5:]]
            new_hl = min(recent_lows)
            buffer = max(5 * pip, new_hl * SL_BUFFER)
            new_sl = new_hl - buffer
            if new_sl > current_sl and new_sl < current_price:
                return round(new_sl, 6)

        elif side == "SHORT":
            recent_highs = [c["high"] for c in candles[-5:]]
            new_lh = max(recent_highs)
            buffer = max(5 * pip, new_lh * SL_BUFFER)
            new_sl = new_lh + buffer
            if new_sl < current_sl and new_sl > current_price:
                return round(new_sl, 6)

        return None

    # ─────────────────────────────────────────
    # PnL CALCULATION
    # ─────────────────────────────────────────
    def calc_pnl(self, symbol: str, side: str, entry: float,
                  exit_price: float, units: float) -> float:
        """
        Calculate PnL in USD for a closed Forex position.

        For USD-quote pairs (EURUSD, GBPUSD, AUDUSD, NZDUSD):
          pnl = (exit - entry) × units   [LONG]
          pnl = (entry - exit) × units   [SHORT]

        For USD-base pairs (USDJPY, USDCAD): same formula approximation.
        Exact cross-pair PnL requires the live quote rate.
        """
        price_change = exit_price - entry
        if side == "SHORT":
            price_change = -price_change
        return round(price_change * units, 4)

    # ─────────────────────────────────────────
    # DRAWDOWN PROTECTION
    # ─────────────────────────────────────────
    def register_pnl(self, pnl: float):
        self.daily_pnl += pnl
        self.account_balance += pnl
        if self.account_balance > self.peak_balance:
            self.peak_balance = self.account_balance

        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        if self.daily_pnl <= -self._day_start_balance * MAX_DAILY_LOSS:
            logger.warning(f"Daily loss limit hit ({self.daily_pnl:.2f}) — disabling trading")
            self.trading_enabled = False

        drawdown = (self.peak_balance - self.account_balance) / self.peak_balance
        if drawdown >= MAX_DRAWDOWN:
            logger.warning(f"Max drawdown {drawdown:.1%} hit — disabling trading")
            self.trading_enabled = False

        if self._consecutive_losses >= 5:
            logger.warning("5 consecutive losses — pausing trading")
            self.trading_enabled = False

    def reset_daily(self):
        self.daily_pnl = 0.0
        self._consecutive_losses = 0
        self._day_start_balance = self.account_balance
        drawdown = (self.peak_balance - self.account_balance) / self.peak_balance
        if drawdown < MAX_DRAWDOWN:
            self.trading_enabled = True


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _calc_atr(candles: List[dict], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.001
    trs = []
    for i in range(1, min(period + 1, len(candles))):
        c, p = candles[i], candles[i - 1]
        tr = max(c["high"] - c["low"],
                 abs(c["high"] - p["close"]),
                 abs(c["low"] - p["close"]))
        trs.append(tr)
    return float(np.mean(trs)) if trs else 0.001


def _find_liquidity_targets(side: str, entry: float,
                             liquidity_zones: List[Dict]) -> List[float]:
    targets = []
    for zone in liquidity_zones:
        price = zone.get("price", sum(zone.get("price_zone", [0, 0])) / 2)
        if side == "LONG" and price > entry and zone["type"] == "buy_side_liquidity":
            targets.append(price)
        elif side == "SHORT" and price < entry and zone["type"] == "sell_side_liquidity":
            targets.append(price)
    targets.sort(key=lambda p: abs(p - entry))
    return targets


# Alias for compatibility with phases 7-9 that import RiskEngine
RiskEngine = ForexRiskEngine
