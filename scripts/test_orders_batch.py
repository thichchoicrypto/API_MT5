"""
Test mở 4 lệnh CÓ SL/TP trên IBKR paper account để kiểm tra dashboard:
  - 2 lệnh MARKET (BUY) → fill ngay, ra position + SL/TP trong "Open orders"
  - 2 lệnh LIMIT (BUY, đặt cách giá hiện tại để KHÔNG fill ngay) → chỉ ra
    "Open orders" (entry LMT + SL/TP), không có position

Giữ nguyên trong 2 phút để check trên dashboard (Position đang mở: giá hiện
tại/PnL/leverage/SL/TP, và Open orders: 4 lệnh entry LIMIT + SL/TP), sau đó
tự cleanup: đóng 2 position MARKET + cancel toàn bộ order còn lại (LIMIT
entry + SL/TP chưa khớp).

KHÔNG dùng tiền thật — IB_PAPER_MODE=true → port 7497 (paper trading).
Dùng clientId riêng (client_id_offset=30), giống test_order.py — KHÔNG chạy
song song với test_order.py / cancel_orphan_orders.py (cùng clientId).

Chạy:
    cd /root/API_FOREX && source .venv/bin/activate
    python3 scripts/test_orders_batch.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import logger
from phase9_live.ibkr_order_manager import IBKROrderManager
from config.settings import IB_PAPER_MODE

UNITS = 20_000   # minimum size (0.2 lot)

SL_PIPS    = 0.0050   # 50 pip
TP_PIPS    = 0.0100   # 100 pip (RR 1:2)
LIMIT_OFF  = 0.0020   # entry LIMIT cách giá hiện tại 20 pip (BUY → đặt dưới giá)

# 2 lệnh MARKET (fill ngay → có position)
MARKET_SYMBOLS = ["GBPUSD", "AUDUSD"]
# 2 lệnh LIMIT (đặt cách giá → chỉ nằm trong open orders, chưa fill)
LIMIT_SYMBOLS  = ["USDCAD", "NZDUSD"]

WAIT_SECONDS = 120   # 2 phút


async def place_market(om, symbol):
    price = await om.get_current_price(symbol)
    if not price:
        logger.error(f"[{symbol}] Không lấy được giá — skip.")
        return None
    sl = round(price - SL_PIPS, 5)
    tp = round(price + TP_PIPS, 5)
    logger.info(f"[{symbol}] MARKET BUY @ ~{price} | SL={sl} TP={tp}")
    result = await om.place_order(symbol, "BUY", "MARKET", UNITS,
                                    stop_loss=sl, take_profit=tp)
    logger.info(f"[{symbol}] place_order (MARKET) result: {result}")
    return result


async def place_limit(om, symbol):
    price = await om.get_current_price(symbol)
    if not price:
        logger.error(f"[{symbol}] Không lấy được giá — skip.")
        return None
    entry = round(price - LIMIT_OFF, 5)
    sl    = round(entry - SL_PIPS, 5)
    tp    = round(entry + TP_PIPS, 5)
    logger.info(f"[{symbol}] LIMIT BUY @ {entry} (giá hiện tại ~{price}) | SL={sl} TP={tp}")
    result = await om.place_order(symbol, "BUY", "LIMIT", UNITS, price=entry,
                                    stop_loss=sl, take_profit=tp)
    logger.info(f"[{symbol}] place_order (LIMIT) result: {result}")
    return result


async def main():
    if not IB_PAPER_MODE:
        logger.error("IB_PAPER_MODE=false — script này chỉ chạy ở paper mode. Dừng.")
        return

    async with IBKROrderManager(client_id_offset=30) as om:
        results = {}

        logger.info("=== Đặt 2 lệnh MARKET (có SL/TP) ===")
        for sym in MARKET_SYMBOLS:
            results[sym] = await place_market(om, sym)

        logger.info("=== Đặt 2 lệnh LIMIT (có SL/TP, chưa fill) ===")
        for sym in LIMIT_SYMBOLS:
            results[sym] = await place_limit(om, sym)

        # Ghi nhớ TOÀN BỘ orderId do CHÍNH script này đặt (entry + SL + TP).
        # Dùng để cleanup chỉ cancel đúng các order này — KHÔNG cancel theo
        # toàn bộ get_open_trades() (giờ thấy cross-client do
        # reqAllOpenOrders), tránh cancel nhầm order của dashboard/client khác
        # (đã từng xảy ra với order #160 của dashboard).
        placed_order_ids = set()
        for res in results.values():
            if not res:
                continue
            for key in ("orderId", "sl_order_id", "tp_order_id"):
                oid = res.get(key)
                if oid:
                    placed_order_ids.add(str(oid))
        logger.info(f"placed_order_ids (của script này): {placed_order_ids}")

        await asyncio.sleep(2)

        logger.info("=== Snapshot ngay sau khi đặt ===")
        for sym in MARKET_SYMBOLS:
            pos = await om.get_position(sym)
            logger.info(f"[{sym}] position: {pos}")
        open_trades = await om.get_open_trades()
        logger.info(f"open_trades: {open_trades}")

        logger.info(f"=== Đợi {WAIT_SECONDS}s — check dashboard ngay bây giờ ===")
        await asyncio.sleep(WAIT_SECONDS)

        logger.info("=== Cleanup: đóng position MARKET + cancel order còn lại ===")

        # 1) Đóng 2 position MARKET
        for sym in MARKET_SYMBOLS:
            pos = await om.get_position(sym)
            if pos:
                close_result = await om.close_trade(sym, pos["side"], pos["units"])
                logger.info(f"[{sym}] close_trade result: {close_result}")
                await asyncio.sleep(1)
            else:
                logger.warning(f"[{sym}] Không thấy position để đóng.")

        await asyncio.sleep(2)

        # 2) Cancel order còn lại — CHỈ trong số orderId do CHÍNH script này
        #    đặt (placed_order_ids). get_open_trades() giờ trả về order của
        #    MỌI clientId (do reqAllOpenOrders trong CHG-FX-019) nên KHÔNG
        #    lặp qua toàn bộ open_trades để cancel — tránh cancel nhầm order
        #    của dashboard/client khác (đã từng xảy ra với order #160).
        #    (SL/TP của MARKET có thể đã bị OCA auto-cancel khi close_trade
        #    fill; LIMIT entry + SL/TP của LIMIT_SYMBOLS thì chưa khớp nên
        #    vẫn còn open.)
        open_trades = await om.get_open_trades()
        logger.info(f"open_trades trước cleanup (mọi client): {open_trades}")
        for t in open_trades:
            if t["orderId"] not in placed_order_ids:
                logger.info(f"skip #{t['orderId']} ({t['symbol']} {t['order_type']}) — không do script này đặt")
                continue
            ok = await om.cancel_order(t["orderId"])
            logger.info(f"cancel #{t['orderId']} ({t['symbol']} {t['order_type']}): {ok}")
            await asyncio.sleep(0.3)

        await asyncio.sleep(1)
        open_trades_after = await om.get_open_trades()
        logger.info(f"open_trades sau cleanup: {open_trades_after}")

        for sym in MARKET_SYMBOLS:
            pos_after = await om.get_position(sym)
            logger.info(f"[{sym}] position sau cleanup: {pos_after}")


if __name__ == "__main__":
    asyncio.run(main())
