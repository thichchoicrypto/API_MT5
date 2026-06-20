"""
Phase 8.10–8.11 — Position Lifecycle Manager + Real-time PnL Engine.
"""
from datetime import datetime, timezone
from typing import List, Dict, Optional
from utils.logger import logger


TAKER_FEE = 0.0  # Forex: no exchange fee — cost is spread (already in fill price)


class PaperPortfolio:
    def __init__(self, initial_balance: float):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.peak_balance = initial_balance
        self.open_positions: List[Dict] = []
        self.closed_positions: List[Dict] = []
        self.daily_pnl: float = 0.0
        self.trading_enabled: bool = True

    def open_position(self, order: Dict, fill_price: float) -> Optional[Dict]:
        pos = {
            "id": order["id"],
            "symbol": order["symbol"],
            "side": order["side"],
            "entry": fill_price,
            "size": order["size"],
            "sl": order.get("sl"),
            "tp": order.get("tp", []),
            "tp_index": 0,
            "status": "OPEN",
            "unrealized_pnl": 0.0,
            "opened_at": datetime.now(tz=timezone.utc),
            "be_set": False,
            "current_price": fill_price,
        }
        self.open_positions.append(pos)
        return pos

    def update_positions(self, candle: dict) -> List[Dict]:
        """Update each open position against the new candle. Return list of closed positions."""
        newly_closed = []

        for pos in list(self.open_positions):
            if pos["symbol"] != candle["symbol"]:
                continue

            price = candle["close"]
            pos["current_price"] = price

            # Unrealized PnL
            direction = 1 if pos["side"] == "LONG" else -1
            pos["unrealized_pnl"] = (price - pos["entry"]) * direction * pos["size"]

            # SL check
            sl = pos.get("sl")
            if sl:
                if pos["side"] == "LONG" and candle["low"] <= sl:
                    pnl = self._close(pos, sl, "SL")
                    newly_closed.append(pos)
                    continue
                elif pos["side"] == "SHORT" and candle["high"] >= sl:
                    pnl = self._close(pos, sl, "SL")
                    newly_closed.append(pos)
                    continue

            # TP check
            tps = pos.get("tp", [])
            ti = pos["tp_index"]
            if tps and ti < len(tps):
                tp_level = tps[ti]["level"]
                if pos["side"] == "LONG" and candle["high"] >= tp_level:
                    pnl = self._close(pos, tp_level, f"TP{ti+1}")
                    newly_closed.append(pos)
                    continue
                elif pos["side"] == "SHORT" and candle["low"] <= tp_level:
                    pnl = self._close(pos, tp_level, f"TP{ti+1}")
                    newly_closed.append(pos)
                    continue

            # Breakeven
            if not pos["be_set"] and sl:
                r1 = abs(pos["entry"] - sl)
                if pos["side"] == "LONG" and price >= pos["entry"] + r1:
                    pos["sl"] = pos["entry"]
                    pos["be_set"] = True
                    logger.info(f"[Paper] BE set for {pos['symbol']} {pos['side']}")
                elif pos["side"] == "SHORT" and price <= pos["entry"] - r1:
                    pos["sl"] = pos["entry"]
                    pos["be_set"] = True

        # Remove closed from open
        for cp in newly_closed:
            if cp in self.open_positions:
                self.open_positions.remove(cp)

        return newly_closed

    def _close(self, pos: Dict, exit_price: float, status: str) -> float:
        direction = 1 if pos["side"] == "LONG" else -1
        gross = (exit_price - pos["entry"]) * direction * pos["size"]
        fee = (pos["entry"] + exit_price) * pos["size"] * TAKER_FEE
        pnl = gross - fee

        pos["exit"] = exit_price
        pos["pnl"] = round(pnl, 4)
        pos["status"] = status
        pos["closed_at"] = datetime.now(tz=timezone.utc)

        self.balance += pnl
        self.daily_pnl += pnl
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance

        self.closed_positions.append(pos.copy())
        return pnl

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p["unrealized_pnl"] for p in self.open_positions)

    @property
    def equity(self) -> float:
        return self.balance + self.total_unrealized_pnl

    @property
    def drawdown(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.balance) / self.peak_balance

    @property
    def daily_pnl_pct(self) -> float:
        return self.daily_pnl / self.initial_balance

    def get_metrics(self) -> Dict:
        trades = self.closed_positions
        if not trades:
            return {"balance": self.balance, "trades": 0}
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) <= 0]
        pnls = [t.get("pnl", 0) for t in trades]
        return {
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "total_trades": len(trades),
            "winrate": round(len(wins) / len(trades), 4) if trades else 0,
            "net_pnl": round(sum(pnls), 2),
            "max_drawdown": round(self.drawdown, 4),
            "open_positions": len(self.open_positions),
            "daily_pnl": round(self.daily_pnl, 2),
        }
