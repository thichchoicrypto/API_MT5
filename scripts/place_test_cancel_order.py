"""
Đặt 1 LIMIT order DUY NHẤT (không SL/TP) để test nút "Cancel" trên dashboard
(CHG-FX-022).

- Symbol: NZDUSD (không nằm trong SYMBOLS của bot -> không đụng forex-bot).
- Giá đặt cách xa giá hiện tại (-5%) -> không fill, nằm yên trong open orders.
- Đặt bằng clientId offset=30 (clientId 31) -> KHÁC clientId của dashboard
  (offset=40 / clientId 41) -> đúng kịch bản cross-client mà CHG-FX-022 fix.

Chạy:
    cd /root/API_FOREX && source .venv/bin/activate
    python3 scripts/place_test_cancel_order.py

Sau khi chạy: mở dashboard -> "Open orders" sẽ thấy 1 order NZDUSD BUY LIMIT.
Bấm "Cancel" -> order phải biến mất khỏi danh sách (và khỏi IB thật).
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import logger
from phase9_live.ibkr_order_manager import IBKROrderManager


async def main():
    async with IBKROrderManager(client_id_offset=30) as om:
        price = await om.get_current_price("NZDUSD")
        entry = round(price * 0.95, 5)  # -5% so với giá hiện tại -> không fill
        logger.info(f"NZDUSD giá hiện tại ~{price}, đặt LIMIT BUY @ {entry}")

        result = await om.place_order("NZDUSD", "BUY", "LIMIT", 20000, price=entry)
        logger.info(f"place_order result: {result}")

        await asyncio.sleep(1)
        open_trades = await om.get_open_trades("NZDUSD")
        logger.info(f"open_trades NZDUSD: {open_trades}")


if __name__ == "__main__":
    asyncio.run(main())
