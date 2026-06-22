"""
Test script — đặt lệnh MARKET + LIMIT rồi cancel sau 1 phút.

Usage (trên VPS, trong venv):
    python tools/test_orders.py

Yêu cầu: MT5 Terminal đang chạy và đã login.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import MetaTrader5 as mt5
from phase9_live.mt5_order_manager import MT5OrderManager
from utils.logger import logger

# ─────────────────────────────────────────────
# CONFIG — chỉnh tại đây
# ─────────────────────────────────────────────
SYMBOL     = "GBPUSD"
VOLUME     = 0.01          # lots (min lot)
CANCEL_AFTER = 60          # giây


def get_current_price(symbol: str):
    """Lấy giá bid/ask hiện tại."""
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise RuntimeError(f"Cannot get tick for {symbol}")
    return tick.bid, tick.ask


async def test_market_order(om: MT5OrderManager):
    """Đặt MARKET BUY, chờ 1 phút, đóng position."""
    print("\n" + "="*50)
    print("TEST 1: MARKET ORDER")
    print("="*50)

    bid, ask = get_current_price(SYMBOL)
    pip = 0.0001

    sl = round(ask - 20 * pip, 5)   # SL 20 pips bên dưới
    tp = round(ask + 40 * pip, 5)   # TP 40 pips bên trên

    print(f"Symbol : {SYMBOL}")
    print(f"Side   : BUY MARKET")
    print(f"Price  : {ask:.5f} (ask)")
    print(f"SL     : {sl:.5f}")
    print(f"TP     : {tp:.5f}")
    print(f"Volume : {VOLUME} lots")

    ticket = await om.place_order(
        symbol=SYMBOL, side="BUY", volume=VOLUME,
        sl=sl, tp=tp, order_type="MARKET", comment="TEST_MARKET"
    )

    if not ticket:
        print("❌ MARKET order FAILED")
        return

    print(f"✅ MARKET order filled — ticket #{ticket}")
    print(f"⏳ Chờ {CANCEL_AFTER}s rồi đóng position...")
    await asyncio.sleep(CANCEL_AFTER)

    ok = await om.close_position(ticket, SYMBOL)
    if ok:
        print(f"✅ Position #{ticket} đã đóng")
    else:
        print(f"❌ Đóng position FAILED — vào MT5 đóng tay ticket #{ticket}")


async def test_limit_order(om: MT5OrderManager):
    """Đặt LIMIT BUY thấp hơn giá hiện tại, chờ 1 phút, cancel."""
    print("\n" + "="*50)
    print("TEST 2: LIMIT ORDER")
    print("="*50)

    bid, ask = get_current_price(SYMBOL)
    pip = 0.0001

    entry = round(ask - 30 * pip, 5)  # Đặt limit 30 pips dưới ask (sẽ không fill ngay)
    sl    = round(entry - 20 * pip, 5)
    tp    = round(entry + 40 * pip, 5)

    print(f"Symbol : {SYMBOL}")
    print(f"Side   : BUY LIMIT")
    print(f"Entry  : {entry:.5f} (30 pips dưới ask {ask:.5f})")
    print(f"SL     : {sl:.5f}")
    print(f"TP     : {tp:.5f}")
    print(f"Volume : {VOLUME} lots")

    ticket = await om.place_order(
        symbol=SYMBOL, side="BUY", volume=VOLUME,
        price=entry, sl=sl, tp=tp,
        order_type="LIMIT", comment="TEST_LIMIT"
    )

    if not ticket:
        print("❌ LIMIT order FAILED")
        return

    print(f"✅ LIMIT order pending — ticket #{ticket}")
    print(f"⏳ Chờ {CANCEL_AFTER}s rồi cancel...")
    await asyncio.sleep(CANCEL_AFTER)

    ok = await om.cancel_order(ticket)
    if ok:
        print(f"✅ LIMIT order #{ticket} đã cancel")
    else:
        print(f"❌ Cancel FAILED — vào MT5 cancel tay ticket #{ticket}")


async def main():
    # Init MT5
    if not mt5.initialize():
        print(f"❌ MT5 init failed: {mt5.last_error()}")
        return

    info = mt5.account_info()
    if not info:
        print("❌ Cannot get account info")
        mt5.shutdown()
        return

    print(f"\n✅ MT5 Connected")
    print(f"   Account : {info.login}")
    print(f"   Balance : {info.balance} {info.currency}")
    print(f"   Server  : {info.server}")

    om = MT5OrderManager()

    try:
        await test_market_order(om)
        await asyncio.sleep(3)
        await test_limit_order(om)
    finally:
        mt5.shutdown()
        print("\n✅ Done — MT5 disconnected")


if __name__ == "__main__":
    asyncio.run(main())
