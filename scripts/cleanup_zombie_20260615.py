"""
Dọn dẹp 1 lần (Conv 11, 2026-06-15): cancel 8 order zombie còn sót lại từ
round-2 của test_orders_batch.py (process bị crash giữa lúc IB Gateway
restart) + đóng AUDUSD position về flat nếu còn mở.

Connect bằng clientId offset=30 (giống test_orders_batch.py) để cancel có
hiệu lực (orders do chính clientId này đặt).

Chạy:
    cd /root/API_FOREX && source .venv/bin/activate
    python3 scripts/cleanup_zombie_20260615.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import logger
from phase9_live.mt5_order_manager import MT5OrderManager

ZOMBIE_ORDER_IDS = ["107", "108", "110", "111", "112", "114", "115", "116"]


async def main():
    om = MT5OrderManager()
        trades = await om.get_open_trades()
        logger.info(f"Open trades trước cleanup: {trades}")

        for oid in ZOMBIE_ORDER_IDS:
            ok = await om.cancel_order(oid)
            logger.info(f"cancel #{oid}: {ok}")

        await asyncio.sleep(1)

        # AUDUSD position -> đóng về flat nếu còn mở
        pos = await om.get_position("AUDUSD")
        logger.info(f"AUDUSD position: {pos}")
        if pos and pos["units"] > 0:
            side = "BUY" if pos["long_units"] > 0 else "SELL"
            result = await om.close_trade("AUDUSD", side, pos["units"])
            logger.info(f"close AUDUSD result: {result}")
        else:
            logger.info("AUDUSD đã flat, không cần đóng")

        await asyncio.sleep(1)
        trades_after = await om.get_open_trades()
        pos_after = await om.get_position("AUDUSD")
        logger.info(f"Open trades sau cleanup: {trades_after}")
        logger.info(f"AUDUSD position sau cleanup: {pos_after}")


if __name__ == "__main__":
    asyncio.run(main())
