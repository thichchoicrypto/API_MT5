"""
Check trạng thái account IBKR paper (DUQ686904) — read-only, không đặt lệnh mới.
Dùng để xem position / order / fill hiện tại mà không cần login web portal
(tránh session conflict với Gateway).

Chạy:
    cd /root/API_FOREX && source .venv/bin/activate
    python3 scripts/check_account.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import logger
from phase9_live.ibkr_order_manager import IBKROrderManager
from config.settings import SYMBOLS


async def main():
    async with IBKROrderManager() as om:
        balance = await om.get_account_balance()
        logger.info(f"Account balance (NetLiquidation USD): {balance}")

        summary = await om.get_account_summary()
        for tag in ("NetLiquidation", "AvailableFunds", "BuyingPower", "TotalCashValue", "GrossPositionValue"):
            if summary and tag in summary:
                logger.info(f"  {tag}: {summary[tag]}")

        logger.info("=== Open positions ===")
        found_pos = False
        for symbol in SYMBOLS:
            pos = await om.get_position(symbol)
            if pos:
                logger.info(f"  {symbol}: {pos}")
                found_pos = True
        if not found_pos:
            logger.info("  (không có position nào)")

        logger.info("=== Open orders (chưa fill / pending SL-TP) ===")
        open_trades = await om.get_open_trades()
        if open_trades:
            for t in open_trades:
                logger.info(f"  {t}")
        else:
            logger.info("  (không có open order)")

        logger.info("=== Recent fills (closed trades) ===")
        for symbol in SYMBOLS:
            fills = await om.get_closed_trades(symbol, count=5)
            for f in fills:
                logger.info(f"  {f}")


if __name__ == "__main__":
    asyncio.run(main())
