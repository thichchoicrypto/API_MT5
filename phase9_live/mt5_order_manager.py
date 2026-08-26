"""
Phase 9 — MetaTrader5 Order Manager (Windows VPS).

Xử lý toàn bộ order lifecycle qua MetaTrader5 Python API:
  - place_order()        : MARKET / LIMIT order với SL/TP embedded
  - modify_trade_sl()    : dời SL (breakeven / trailing)
  - close_position()     : đóng một position
  - cancel_order()       : huỷ pending order
  - get_position()       : lấy position theo symbol
  - get_all_positions()  : tất cả vị thế đang mở
  - get_pending_orders() : pending orders
  - get_last_closed_trade() : trade vừa đóng
  - get_account_balance()   : số dư tài khoản
  - close_all_positions()   : đóng tất cả

Lưu ý MT5:
  - Mọi cuộc gọi MT5 là synchronous → run qua loop.run_in_executor
  - BOT_MAGIC phân biệt lệnh bot vs lệnh tay
  - SL/TP nhúng thẳng vào order request (không cần order riêng)
  - Volume tính bằng lots (1 lot = 100,000 units)
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from utils.logger import logger
from utils.telegram import telegram
from config.settings import MT5_SYMBOL_MAP, MT5_TF_MAP

BOT_MAGIC = 20250101   # magic number phân biệt lệnh bot vs lệnh tay


def _mt5():
    """Lazy import MetaTrader5."""
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        raise ImportError(
            "MetaTrader5 not installed.\n"
            "  Windows: pip install MetaTrader5\n"
            "  Mac/Linux: dùng paper mode (DATA_SOURCE=YFINANCE)"
        )


class MT5OrderManager:
    """Async wrapper cho MetaTrader5 order operations."""

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def _run(self, fn, *args):
        """Chạy synchronous MT5 call trong executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn, *args)

    # ──────────────────────────────────────────────────────────
    # PLACE ORDER
    # ──────────────────────────────────────────────────────────
    async def place_order(
        self,
        symbol:     str,
        side:       str,      # "BUY" | "SELL"
        volume:     float,    # lots (đã convert từ units bên live_engine)
        price:      float = 0.0,
        sl:         float = 0.0,
        tp:         float = 0.0,
        order_type: str   = "MARKET",
        comment:    str   = "SMC_BOT",
    ) -> Optional[int]:
        """
        Place MARKET hoặc LIMIT order.
        Trả về ticket (int) nếu thành công, None nếu thất bại.
        """
        mt5 = _mt5()
        mt5_sym = MT5_SYMBOL_MAP.get(symbol, symbol)

        def _send():
            # Normalise volume
            vol = self._normalize_volume_sync(mt5_sym, volume)

            if order_type == "MARKET":
                action    = mt5.TRADE_ACTION_DEAL
                otype     = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
                exec_price= 0.0   # broker fills at market
            else:  # LIMIT
                action    = mt5.TRADE_ACTION_PENDING
                otype     = (mt5.ORDER_TYPE_BUY_LIMIT if side == "BUY"
                             else mt5.ORDER_TYPE_SELL_LIMIT)
                exec_price= self._normalize_price_sync(mt5_sym, price)

            req = {
                "action":    action,
                "symbol":    mt5_sym,
                "volume":    vol,
                "type":      otype,
                "price":     exec_price,
                "sl":        sl,
                "tp":        tp,
                "magic":     BOT_MAGIC,
                "comment":   comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(req)
            return result

        result = await self._run(_send)
        if result is None:
            mt5 = _mt5()
            logger.error(f"place_order None: {mt5.last_error()}")
            return None
        if result.retcode != _mt5().TRADE_RETCODE_DONE:
            logger.error(
                f"place_order FAILED {symbol} {side} {volume:.2f}lots "
                f"retcode={result.retcode} | {result.comment}"
            )
            await telegram.send(
                f"❌ Order failed {symbol} {side}\n"
                f"retcode={result.retcode} {result.comment}"
            )
            return None

        ticket = result.order
        logger.info(
            f"✅ Order placed {symbol} {side} {volume:.2f}lots ticket={ticket}"
        )
        if order_type == "MARKET":
            # Không gửi Telegram ở đây — _finalize_entry sẽ gửi message đầy đủ
            pass
        # LIMIT placed message is sent by live_engine (_pending_limit_orders block)
        return ticket

    # ──────────────────────────────────────────────────────────
    # MODIFY SL (breakeven / trailing stop)
    # ──────────────────────────────────────────────────────────
    async def modify_trade_sl(
        self,
        ticket:  int,
        symbol:  str,
        new_sl:  float,
        new_tp:  Optional[float] = None,
    ) -> bool:
        mt5 = _mt5()
        mt5_sym = MT5_SYMBOL_MAP.get(symbol, symbol)

        def _modify():
            pos = mt5.positions_get(ticket=ticket)
            if not pos:
                return False
            p   = pos[0]
            req = {
                "action":   mt5.TRADE_ACTION_SLTP,
                "symbol":   mt5_sym,
                "sl":       new_sl,
                "tp":       new_tp if new_tp is not None else p.tp,
                "position": ticket,
                "magic":    BOT_MAGIC,
            }
            result = mt5.order_send(req)
            return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

        ok = await self._run(_modify)
        if ok:
            logger.info(f"SL modified ticket={ticket} new_sl={new_sl}")
        else:
            logger.error(f"modify_trade_sl FAILED ticket={ticket}")
        return ok

    # ──────────────────────────────────────────────────────────
    # CLOSE POSITION
    # ──────────────────────────────────────────────────────────
    async def close_position(
        self,
        ticket: int,
        symbol: str,
        volume: Optional[float] = None,
    ) -> bool:
        mt5 = _mt5()
        mt5_sym = MT5_SYMBOL_MAP.get(symbol, symbol)

        def _close():
            pos = mt5.positions_get(ticket=ticket)
            if not pos:
                logger.warning(f"close_position: ticket {ticket} not found")
                return False
            p   = pos[0]
            vol = volume or p.volume
            # Đóng ngược chiều
            close_type = (mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY
                          else mt5.ORDER_TYPE_BUY)
            price = (mt5.symbol_info_tick(mt5_sym).bid if close_type == mt5.ORDER_TYPE_SELL
                     else mt5.symbol_info_tick(mt5_sym).ask)
            req = {
                "action":       mt5.TRADE_ACTION_DEAL,
                "symbol":       mt5_sym,
                "volume":       vol,
                "type":         close_type,
                "position":     ticket,
                "price":        price,
                "magic":        BOT_MAGIC,
                "comment":      "SMC_CLOSE",
                "type_time":    mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(req)
            return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

        ok = await self._run(_close)
        if ok:
            logger.info(f"Position closed ticket={ticket} {symbol}")
            await telegram.send(
                f"🔒 [LIVE] Position closed {symbol}\n"
                f"  ticket : #{ticket}"
            )
        else:
            logger.error(f"close_position FAILED ticket={ticket}")
        return ok

    # ──────────────────────────────────────────────────────────
    # CANCEL PENDING ORDER
    # ──────────────────────────────────────────────────────────
    async def cancel_order(self, ticket: int) -> bool:
        mt5 = _mt5()

        def _cancel():
            req    = {"action": mt5.TRADE_ACTION_REMOVE, "order": ticket, "magic": BOT_MAGIC}
            result = mt5.order_send(req)
            return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

        ok = await self._run(_cancel)
        if ok:
            logger.info(f"Order cancelled ticket={ticket}")
        else:
            logger.error(f"cancel_order FAILED ticket={ticket}")
        return ok

    # ──────────────────────────────────────────────────────────
    # GET POSITION BY SYMBOL
    # ──────────────────────────────────────────────────────────
    async def get_position(self, symbol: str) -> Optional[Dict]:
        mt5     = _mt5()
        mt5_sym = MT5_SYMBOL_MAP.get(symbol, symbol)

        def _get():
            positions = mt5.positions_get(symbol=mt5_sym)
            if not positions:
                return None
            # Filter by magic
            bot_pos = [p for p in positions if p.magic == BOT_MAGIC]
            if not bot_pos:
                return None
            p = bot_pos[0]
            tick = mt5.symbol_info_tick(mt5_sym)
            current = (tick.bid if p.type == mt5.POSITION_TYPE_BUY
                       else tick.ask) if tick else p.price_current
            return {
                "ticket":  p.ticket,
                "symbol":  symbol,
                "side":    "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume":  p.volume,
                "entry":   p.price_open,
                "sl":      p.sl,
                "tp":      p.tp,
                "profit":  p.profit,
                "current": current,
            }

        return await self._run(_get)

    # ──────────────────────────────────────────────────────────
    # GET POSITION BY TICKET
    # ──────────────────────────────────────────────────────────
    async def get_position_by_ticket(self, ticket: int) -> Optional[Dict]:
        """Lấy position theo ticket cụ thể — dùng khi nhiều lệnh cùng symbol."""
        mt5 = _mt5()

        def _get():
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return None
            p = positions[0]
            mt5_sym = p.symbol
            tick = mt5.symbol_info_tick(mt5_sym)
            current = (tick.bid if p.type == mt5.POSITION_TYPE_BUY
                       else tick.ask) if tick else p.price_current
            return {
                "ticket":  p.ticket,
                "symbol":  mt5_sym,
                "side":    "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume":  p.volume,
                "entry":   p.price_open,
                "sl":      p.sl,
                "tp":      p.tp,
                "profit":  p.profit,
                "current": current,
            }

        return await self._run(_get)

    # ──────────────────────────────────────────────────────────
    # GET ALL POSITIONS
    # ──────────────────────────────────────────────────────────
    async def get_all_positions(self) -> List[Dict]:
        mt5 = _mt5()

        def _get():
            positions = mt5.positions_get()
            if not positions:
                return []
            result = []
            for p in positions:
                if p.magic != BOT_MAGIC:
                    continue
                tick = mt5.symbol_info_tick(p.symbol)
                current = (tick.bid if p.type == mt5.POSITION_TYPE_BUY
                           else tick.ask) if tick else p.price_current
                result.append({
                    "ticket":  p.ticket,
                    "symbol":  p.symbol,
                    "side":    "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                    "volume":  p.volume,
                    "entry":   p.price_open,
                    "sl":      p.sl,
                    "tp":      p.tp,
                    "profit":  p.profit,
                    "current": current,
                })
            return result

        return await self._run(_get)

    # ──────────────────────────────────────────────────────────
    # GET PENDING ORDERS
    # ──────────────────────────────────────────────────────────
    async def get_pending_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        mt5 = _mt5()
        mt5_sym = MT5_SYMBOL_MAP.get(symbol, symbol) if symbol else None

        def _get():
            orders = mt5.orders_get(symbol=mt5_sym) if mt5_sym else mt5.orders_get()
            if not orders:
                return []
            result = []
            for o in orders:
                if o.magic != BOT_MAGIC:
                    continue
                result.append({
                    "ticket": o.ticket,
                    "symbol": o.symbol,
                    "type":   "BUY_LIMIT" if o.type == mt5.ORDER_TYPE_BUY_LIMIT else "SELL_LIMIT",
                    "volume": o.volume_current,
                    "price":  o.price_open,
                    "sl":     o.sl,
                    "tp":     o.tp,
                })
            return result

        return await self._run(_get)

    # ──────────────────────────────────────────────────────────
    # GET LAST CLOSED TRADE
    # ──────────────────────────────────────────────────────────
    async def get_last_closed_trade(
        self, symbol: str, since: Optional[datetime] = None,
        position_id: Optional[int] = None,
    ) -> Optional[Dict]:
        mt5     = _mt5()
        mt5_sym = MT5_SYMBOL_MAP.get(symbol, symbol)

        def _get():
            now   = int(time.time())
            start = int(since.timestamp()) if since else now - 86400
            deals = mt5.history_deals_get(start, now, group=mt5_sym)
            if not deals:
                return None

            # Lấy tất cả CLOSE deals (kể cả manual close — magic=0)
            all_close_deals = sorted(
                [d for d in deals
                 if d.entry == mt5.DEAL_ENTRY_OUT],
                key=lambda d: d.time, reverse=True
            )
            if not all_close_deals:
                return None

            # Filter by position_id nếu có — tránh nhầm lệnh khi nhiều position cùng symbol
            if position_id is not None:
                bot_deals = [d for d in all_close_deals if d.position_id == position_id]
                if not bot_deals:
                    # Fallback: một số broker dùng DEAL ticket làm position_id
                    # (không phải ORDER ticket mà ta lưu)
                    # Tìm opening deal có deal.order == order_ticket → lấy deal.position_id thật
                    open_deals = [d for d in deals
                                  if d.magic == BOT_MAGIC
                                  and d.entry in (mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_INOUT)
                                  and d.order == position_id]
                    if open_deals:
                        actual_pos_id = open_deals[0].position_id
                        bot_deals = [d for d in all_close_deals if d.position_id == actual_pos_id]
                        logger.warning(
                            f"get_last_closed_trade: order_id={position_id} → "
                            f"actual position_id={actual_pos_id} (broker dùng deal ticket)"
                        )
                    if not bot_deals:
                        logger.warning(
                            f"get_last_closed_trade: position_id={position_id} không tìm "
                            f"được closing deal. Available position_ids: "
                            f"{[(d.position_id, d.price, d.time) for d in all_close_deals[:5]]}"
                        )
                        # Last resort: lấy deal mới nhất cho symbol (khi chỉ có 1 vị thế)
                        if len(all_close_deals) == 1:
                            logger.warning("get_last_closed_trade: using most recent deal as fallback")
                            bot_deals = all_close_deals
                        else:
                            return None
            else:
                bot_deals = all_close_deals

            if not bot_deals:
                return None
            d = bot_deals[0]
            # profit của 1 deal có thể chưa tính commission — sum tất cả deals cùng position
            position_profit = sum(
                x.profit for x in deals
                if x.position_id == d.position_id
            )
            return {
                "ticket":    d.position_id,
                "symbol":    symbol,
                "side":      "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL",
                "volume":    d.volume,
                "close":     d.price,
                "profit":    position_profit,  # tổng profit cả position (kể cả commission)
                "close_time": datetime.fromtimestamp(d.time, tz=timezone.utc),
            }

        return await self._run(_get)

    # ──────────────────────────────────────────────────────────
    # GET CURRENT PRICE (bid/ask midpoint)
    # ──────────────────────────────────────────────────────────
    async def get_current_price(self, symbol: str) -> Optional[float]:
        mt5     = _mt5()
        mt5_sym = MT5_SYMBOL_MAP.get(symbol, symbol)

        def _get():
            tick = mt5.symbol_info_tick(mt5_sym)
            if not tick:
                return None
            return (tick.bid + tick.ask) / 2.0

        return await self._run(_get)

    # ──────────────────────────────────────────────────────────
    # ACCOUNT BALANCE
    # ──────────────────────────────────────────────────────────
    async def get_account_balance(self) -> Optional[float]:
        mt5 = _mt5()

        def _get():
            info = mt5.account_info()
            return info.balance if info else None

        return await self._run(_get)

    async def reconnect(self) -> bool:
        """Shutdown và reinitialize MT5 Python API connection."""
        from config.settings import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH

        def _reconnect_sync():
            mt5 = _mt5()
            mt5.shutdown()
            import time; time.sleep(2)
            kwargs = {}
            if MT5_PATH:
                kwargs["path"] = MT5_PATH
            if not mt5.initialize(**kwargs):
                logger.error(f"MT5 reconnect initialize failed: {mt5.last_error()}")
                return False
            if MT5_LOGIN:
                ok = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
                if not ok:
                    logger.error(f"MT5 reconnect login failed: {mt5.last_error()}")
                    mt5.shutdown()
                    return False
            info = mt5.account_info()
            if info:
                logger.info(f"MT5 reconnected — balance={info.balance}")
                return True
            return False

        return await self._run(_reconnect_sync)

    # ──────────────────────────────────────────────────────────
    # CLOSE ALL POSITIONS
    # ──────────────────────────────────────────────────────────
    async def close_all_positions(self) -> int:
        positions = await self.get_all_positions()
        closed = 0
        for p in positions:
            ok = await self.close_position(p["ticket"], p["symbol"])
            if ok:
                closed += 1
        return closed

    # ──────────────────────────────────────────────────────────
    # INTERNAL HELPERS (sync, run inside executor)
    # ──────────────────────────────────────────────────────────
    def _normalize_volume_sync(self, mt5_sym: str, raw_lots: float) -> float:
        try:
            mt5  = _mt5()
            info = mt5.symbol_info(mt5_sym)
            if not info:
                return max(0.01, round(raw_lots, 2))
            step = info.volume_step or 0.01
            vol  = max(info.volume_min, round(raw_lots / step) * step)
            return round(vol, 2)
        except Exception:
            return max(0.01, round(raw_lots, 2))

    def _normalize_price_sync(self, mt5_sym: str, price: float) -> float:
        try:
            mt5  = _mt5()
            info = mt5.symbol_info(mt5_sym)
            if not info:
                return price
            digits = info.digits
            return round(price, digits)
        except Exception:
            return price
