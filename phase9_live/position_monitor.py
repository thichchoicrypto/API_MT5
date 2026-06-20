"""
Phase 9.6 — Live Position Manager.
Tracks entry, SL, TP, unrealized PnL, funding fees.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional
from utils.logger import logger
from config.settings import SL_BUFFER


class LivePosition:
    def __init__(self, order_result: Dict, signal: Dict, risk: Dict):
        self.order_id    = str(order_result.get("ordId", order_result.get("orderId", "")))
        self.symbol      = signal["symbol"]
        self.side        = signal["side"]
        self.candle_time = signal.get("candle_time")   # timestamp candle tạo signal
        self.entry       = float(order_result.get("price", signal["entry_price"]) or signal["entry_price"])
        self.size = risk["position_size"]
        self.sl = risk["sl"]
        self.tp = risk["tp"]
        self.tp_index = 0
        self.be_set = False
        self.opened_at = datetime.now(tz=timezone.utc)
        self.unrealized_pnl: float = 0.0
        self.funding_fees: float = 0.0
        self.current_price: float = self.entry

    @classmethod
    def restore_from_db(cls, row: dict) -> Optional["LivePosition"]:
        """
        Restore LivePosition từ live_trades DB row sau khi bot restart.
        tp được reconstruct từ tp1 level (mất TP2/TP3 — acceptable).
        candle_time = None vì không lưu trong live_trades.
        """
        try:
            entry = float(row.get("entry_price") or 0)
            size  = float(row.get("size") or 0)
            sl    = float(row.get("sl") or 0)
            tp1   = float(row.get("tp") or 0)

            if entry <= 0 or size <= 0:
                return None

            pos = cls.__new__(cls)
            pos.order_id    = str(row.get("order_id", ""))
            pos.symbol      = row["symbol"]
            pos.side        = row["side"]
            pos.candle_time = None   # không có trong live_trades
            pos.entry       = entry
            pos.size        = size
            pos.sl          = sl
            pos.tp          = [{"level": tp1, "rr": 2.0, "size_ratio": 1.0}] if tp1 > 0 else []
            pos.tp_index    = 0
            pos.be_set      = False  # conservative default
            pos.opened_at   = row.get("opened_at") or datetime.now(tz=timezone.utc)
            pos.unrealized_pnl  = 0.0
            pos.funding_fees    = 0.0
            pos.current_price   = entry
            return pos
        except Exception as e:
            logger.error(f"restore_from_db error: {e} | row={row}")
            return None

    def update_pnl(self, mark_price: float):
        """Phase 9.9: Real-time PnL."""
        direction = 1 if self.side == "LONG" else -1
        self.unrealized_pnl = (mark_price - self.entry) * direction * self.size
        self.current_price = mark_price  # needed by risk_engine.check_trailing_stop

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry": self.entry,
            "size": self.size,
            "sl": self.sl,
            "tp": [t["level"] for t in self.tp],
            "unrealized_pnl": round(self.unrealized_pnl, 4),
            "opened_at": str(self.opened_at),
        }


class LivePositionMonitor:
    def __init__(self, order_manager):
        self.order_manager = order_manager
        self.open_positions: Dict[str, LivePosition] = {}

    def track(self, order_result: Dict, signal: Dict, risk: Dict):
        pos = LivePosition(order_result, signal, risk)
        self.open_positions[pos.symbol] = pos
        logger.info(f"[Live] Tracking position: {pos.symbol} {pos.side} @ {pos.entry}")

    def restore(self, pos: "LivePosition"):
        """Restore một position đã được reconstruct từ DB."""
        self.open_positions[pos.symbol] = pos
        logger.info(f"[Live] Restored position: {pos.symbol} {pos.side} @ {pos.entry} (order_id={pos.order_id})")

    def remove(self, symbol: str):
        if symbol in self.open_positions:
            del self.open_positions[symbol]

    def get_summary(self) -> List[Dict]:
        return [p.to_dict() for p in self.open_positions.values()]
