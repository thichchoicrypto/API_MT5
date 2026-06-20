"""
Dọn dẹp toàn bộ (Conv 11, 2026-06-15) — đưa account về flat sau khi
test_orders_batch.py crash 2 lần liên tiếp không cleanup, để lại:
  - GBPUSD: 40000 units long (2x20000 từ 2 run)
  - AUDUSD: 40000 units long (2x20000 từ 2 run)
  - USDCAD/NZDUSD: 0 position nhưng 2x3 order LIMIT+SL+TP còn pending

Tất cả order đều do clientId=31 (offset=30) đặt -> connect đúng client này
để cancel có hiệu lực ngay, không cần Master Client ID.

Chạy:
    cd /root/API_FOREX && source .venv/bin/activate
    python3 scripts/cleanup_full_20260615.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import logger
from phase9_live.mt5_order_manager import MT5OrderManager


async def main():
    om = MT5OrderManager()
        # 1) Đóng position GBPUSD / AUDUSD về flat
        for symbol in ("GBPUSD", "AUDUSD"):
            pos = await om.get_position(symbol)
            logger.info(f"[before] {symbol} position: {pos}")
            if pos and pos["units"] > 0:
                side = "BUY" if pos["long_units"] > 0 else "SELL"
                result = await om.close_trade(symbol, side, pos["units"])
                logger.info(f"close {symbol} result: {result}")

        await asyncio.sleep(2)

        # 2) Cancel toàn bộ order còn open (SL/TP còn sót sau khi close +
        #    LIMIT entry/SL/TP của USDCAD/NZDUSD chưa fill)
        open_trades = await om.get_open_trades()
        logger.info(f"open_trades trước cancel: {open_trades}")
        for t in open_trades:
            ok = await om.cancel_order(t["orderId"])
            logger.info(f"cancel #{t['orderId']} ({t['symbol']} {t['order_type']}): {ok}")

        await asyncio.sleep(2)

        # 3) Snapshot cuối
        logger.info("=== FINAL STATE ===")
        for symbol in ("GBPUSD", "AUDUSD", "USDCAD", "NZDUSD"):
            pos = await om.get_position(symbol)
            logger.info(f"[after] {symbol} position: {pos}")
        open_trades_after = await om.get_open_trades()
        logger.info(f"open_trades sau cancel: {open_trades_after}")


if __name__ == "__main__":
    asyncio.run(main())
