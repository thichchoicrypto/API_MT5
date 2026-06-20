"""
Phase 8 — Paper Trading Engine.
Connects live WebSocket data to strategy engine with simulated fills.
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional, Callable
from utils.logger import logger
from utils.telegram import telegram
from config.settings import PAPER_INITIAL_BALANCE, MAX_DRAWDOWN, MAX_DAILY_LOSS
from phase8_paper.fill_simulator import simulate_fill, simulate_latency
from phase8_paper.portfolio_tracker import PaperPortfolio
from phase4_fvg_ob.fvg_engine import _calc_atr


class PaperTradingEngine:
    """
    Phase 8.4: Architecture:
    Live Market Data → Strategy Engine → Paper Execution → Portfolio → Logger
    """

    def __init__(self, strategy_runner: Callable,
                 initial_balance: float = PAPER_INITIAL_BALANCE,
                 db=None):
        self.strategy_runner = strategy_runner
        self.portfolio = PaperPortfolio(initial_balance)
        self._candle_buffer: Dict[str, List[dict]] = {}
        self._pending_orders: List[Dict] = []
        self._running = False
        self._db = db   # Database instance for persisting trades

    async def preload_from_db(self, db, symbols: list, timeframes: list, limit: int = 500):
        """Preload historical candles from DB so strategy has warmup data immediately."""
        for symbol in symbols:
            for tf in timeframes:
                candles = await db.get_candles(symbol, tf, limit=limit)
                key = f"{symbol}_{tf}"
                self._candle_buffer[key] = candles
                logger.info(f"Preloaded {len(candles)} candles for {symbol} {tf}")
        logger.info("Candle buffer preloaded — strategy ready immediately")

    async def on_candle(self, candle: dict):
        """Called by WebSocket collector on each closed candle."""
        key = f"{candle['symbol']}_{candle['timeframe']}"
        if key not in self._candle_buffer:
            self._candle_buffer[key] = []
        self._candle_buffer[key].append(candle)
        # Keep last 500 candles
        if len(self._candle_buffer[key]) > 500:
            self._candle_buffer[key] = self._candle_buffer[key][-500:]

        # Process pending orders against this candle
        await self._process_pending_orders(candle)

        # Update open positions
        await self._update_positions(candle)

        # Run strategy
        await simulate_latency()
        signal = await self.strategy_runner(candle, self._candle_buffer.get(key, []))
        if signal:
            await self._place_paper_order(signal, self._candle_buffer.get(key, []))

    async def _place_paper_order(self, signal: Dict, candles: List[dict]):
        """Phase 8.6: Create virtual order."""
        if not self.portfolio.trading_enabled:
            return

        order = {
            "id": f"PAPER_{int(datetime.now().timestamp() * 1000)}",
            "symbol": signal["symbol"],
            "side": signal["side"],
            "type": signal.get("entry_type", "LIMIT"),
            "entry_zone": signal.get("entry_zone", [signal["entry_price"] * 0.999, signal["entry_price"] * 1.001]),
            "entry_price": signal.get("entry_price"),
            "sl": signal.get("sl"),
            "tp": signal.get("tp", []),
            "size": signal.get("position_size", 0),
            "signal": signal,
            "created_at": datetime.now(tz=timezone.utc),
        }
        self._pending_orders.append(order)
        logger.info(f"[Paper] Order placed: {order['side']} {order['symbol']} @ {order['entry_price']:.2f}")

    async def _process_pending_orders(self, candle: dict):
        """Try to fill pending orders against incoming candle."""
        still_pending = []
        candles = self._candle_buffer.get(f"{candle['symbol']}_{candle['timeframe']}", [candle])
        atr = _calc_atr(candles)

        for order in self._pending_orders:
            if order["symbol"] != candle["symbol"]:
                still_pending.append(order)
                continue

            fill = simulate_fill(order, candle, atr)
            if fill:
                position = self.portfolio.open_position(order, fill["fill_price"])
                if position:
                    msg = (f"📈 [Paper] ENTRY {order['side']} {order['symbol']} "
                           f"@ {fill['fill_price']:.2f} size={order['size']:.4f}")
                    logger.info(msg)
                    await telegram.send(msg)
                    # Persist to DB
                    if self._db:
                        await self._db.save_paper_trade_open(position)
            else:
                # Cancel old pending orders
                # Timeout = 3 candles — với 15m TF = 2700s, 1h TF = 10800s
                # OKX dùng 300s (5m) vì candle 1m/5m, Forex cần dài hơn
                from config.settings import ENTRY_TIMEFRAME
                _TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
                tf_sec = _TF_SECONDS.get(ENTRY_TIMEFRAME, 900)
                order_timeout = tf_sec * 3   # 3 candles
                age = (datetime.now(tz=timezone.utc) - order["created_at"]).total_seconds()
                if age < order_timeout:
                    still_pending.append(order)

        self._pending_orders = still_pending

    async def _update_positions(self, candle: dict):
        """Phase 8.10–8.11: Update open positions PnL, check SL/TP."""
        closed = self.portfolio.update_positions(candle)
        for pos in closed:
            msg = (f"{'✅' if pos['pnl'] > 0 else '❌'} [Paper] CLOSED "
                   f"{pos['side']} {pos['symbol']} | PnL: {pos['pnl']:+.2f} | "
                   f"Status: {pos['status']}")
            logger.info(msg)
            await telegram.send(msg)
            # Persist close to DB
            if self._db:
                await self._db.save_paper_trade_close(pos)

        # Phase 8.12: Risk enforcement
        if self.portfolio.daily_pnl_pct <= -MAX_DAILY_LOSS:
            self.portfolio.trading_enabled = False
            logger.warning("[Paper] Daily loss limit hit — trading paused")
            await telegram.send("⛔ [Paper] Daily loss limit reached — trading paused")

        if self.portfolio.drawdown >= MAX_DRAWDOWN:
            self.portfolio.trading_enabled = False
            logger.warning(f"[Paper] Max drawdown {self.portfolio.drawdown:.1%} hit")
            await telegram.send(f"⛔ [Paper] Max drawdown {self.portfolio.drawdown:.1%}")

    def get_metrics(self) -> Dict:
        """Phase 8.15: Paper trading metrics."""
        return self.portfolio.get_metrics()
