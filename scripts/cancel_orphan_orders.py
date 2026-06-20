"""
Cancel SL/TP orphan còn sót lại từ scripts/test_order.py (clientId offset=30).

Lý do cần script riêng: dashboard connect bằng clientId khác (offset=40) nên
IB Gateway từ chối cancel order của clientId khác (error 10147 "OrderId ...
that needs to be cancelled is not found"). Connect lại bằng CHÍNH clientId đã
đặt order (offset=30, giống test_order.py) thì cancel mới có hiệu lực.

Chạy:
    cd /root/API_FOREX && source .venv/bin/activate
    python3 scripts/cancel_orphan_orders.py 53 54
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import logger
from phase9_live.mt5_order_manager import MT5OrderManager


async def main(order_ids):
    om = MT5OrderManager()
        trades = await om.get_open_trades()
        logger.info(f"Open trades (clientId offset=30): {trades}")

        for oid in order_ids:
            ok = await om.cancel_order(oid)
            logger.info(f"cancel #{oid}: {ok}")

        await asyncio.sleep(1)
        trades_after = await om.get_open_trades()
        logger.info(f"After cancel: {trades_after}")


if __name__ == "__main__":
    ids = sys.argv[1:] or ["53", "54"]
    asyncio.run(main(ids))
