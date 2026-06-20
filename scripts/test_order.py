"""
Test thử 1 lệnh market order CÓ SL/TP trên IBKR paper account (DUQ686904) qua
IBKROrderManager — kiểm tra end-to-end: place_order (với SL/TP child orders)
→ get_position → get_order (main + SL + TP) → close_trade → cancel SL/TP còn sót.

KHÔNG dùng tiền thật — IB_PAPER_MODE=true → port 7497 (paper trading).

Dùng clientId riêng (client_id_offset=30) để KHÔNG đụng clientId của
forex-bot.service đang chạy (live_engine dùng offset=20 → clientId=21).
An toàn chạy song song với bot đang live.

SL/TP đặt cách giá hiện tại ~50/100 pip — để KHÔNG bị khớp ngay trong lúc
test (đủ thời gian để check status rồi đóng lệnh + cancel SL/TP thủ công).

Chạy:
    cd /root/API_FOREX && source .venv/bin/activate
    python3 scripts/test_order.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import logger
from phase9_live.ibkr_order_manager import IBKROrderManager
from config.settings import IB_PAPER_MODE

SYMBOL  = "EURUSD"
UNITS   = 20_000   # minimum size (0.2 lot)
SL_PIPS = 0.0050   # 50 pip
TP_PIPS = 0.0100   # 100 pip (RR 1:2)


async def main():
    if not IB_PAPER_MODE:
        logger.error("IB_PAPER_MODE=false — script này chỉ chạy ở paper mode. Dừng.")
        return

    # client_id_offset=30 → clientId riêng, khác với bot đang chạy (offset=20)
    async with IBKROrderManager(client_id_offset=30) as om:
        price = await om.get_current_price(SYMBOL)
        logger.info(f"Current price {SYMBOL}: {price}")
        if not price:
            logger.error("Không lấy được giá hiện tại — dừng test.")
            return

        sl = round(price - SL_PIPS, 5)
        tp = round(price + TP_PIPS, 5)
        logger.info(f"SL={sl} (-{SL_PIPS}) | TP={tp} (+{TP_PIPS}) — cách giá hiện tại, không khớp ngay")

        # 1) Place a tiny market BUY order WITH SL/TP
        logger.info("=== Placing test MARKET BUY order với SL/TP ===")
        result = await om.place_order(SYMBOL, "BUY", "MARKET", UNITS,
                                        stop_loss=sl, take_profit=tp)
        logger.info(f"place_order result: {result}")
        if not result:
            logger.error("place_order failed — dừng test.")
            return

        await asyncio.sleep(2)

        # 2) Check order status — main order + SL + TP
        order_id    = result["orderId"]
        sl_order_id = result.get("sl_order_id")
        tp_order_id = result.get("tp_order_id")

        order_status = await om.get_order(SYMBOL, order_id)
        logger.info(f"get_order (main): {order_status}")

        if sl_order_id:
            sl_status = await om.get_order(SYMBOL, sl_order_id)
            logger.info(f"get_order (SL #{sl_order_id}): {sl_status}")
        if tp_order_id:
            tp_status = await om.get_order(SYMBOL, tp_order_id)
            logger.info(f"get_order (TP #{tp_order_id}): {tp_status}")

        # 3) Check position
        pos = await om.get_position(SYMBOL)
        logger.info(f"get_position result: {pos}")

        # 4) Check account balance / summary
        balance = await om.get_account_balance()
        logger.info(f"get_account_balance result: {balance}")

        # 5) Check open orders (nên thấy SL + TP đang chờ)
        open_trades = await om.get_open_trades(SYMBOL)
        logger.info(f"get_open_trades: {open_trades}")

        # 5b) Pause để check trên Client Portal (position + SL/TP orders)
        logger.info("=== Đợi 60s — check Client Portal ngay bây giờ (position + open orders SL/TP) ===")
        await asyncio.sleep(60)

        # 6) Close the test position
        if pos:
            logger.info("=== Closing test position ===")
            close_result = await om.close_trade(SYMBOL, "BUY", pos["units"])
            logger.info(f"close_trade result: {close_result}")
            await asyncio.sleep(2)

            pos_after = await om.get_position(SYMBOL)
            logger.info(f"get_position after close: {pos_after}")
        else:
            logger.warning("Không thấy position sau khi đặt lệnh — kiểm tra lại.")

        # 7) Cancel SL/TP còn sót lại (IBKR không tự cancel child order khi
        #    position đóng bằng market order riêng)
        if sl_order_id:
            ok = await om.cancel_order(sl_order_id)
            logger.info(f"cancel SL #{sl_order_id}: {ok}")
        if tp_order_id:
            ok = await om.cancel_order(tp_order_id)
            logger.info(f"cancel TP #{tp_order_id}: {ok}")

        await asyncio.sleep(1)
        open_trades_after = await om.get_open_trades(SYMBOL)
        logger.info(f"get_open_trades after cleanup: {open_trades_after}")

        # 8) Recent fills
        fills = await om.get_closed_trades(SYMBOL, count=5)
        logger.info(f"Recent fills: {fills}")


if __name__ == "__main__":
    asyncio.run(main())
