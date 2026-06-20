"""
Phase 8.7–8.9 — Fill Simulation + Slippage + Latency Models.
"""
import asyncio
import random
from typing import Optional, Dict
import numpy as np
from config.settings import PAPER_SLIPPAGE_ATR_RATIO, PAPER_LATENCY_MS
from utils.logger import logger


def simulate_slippage(price: float, atr: float, side: str) -> float:
    """
    Phase 8.8: Realistic slippage = ATR * random factor.
    Long entries fill higher, short entries fill lower.
    """
    slip_amount = atr * random.uniform(0.05, PAPER_SLIPPAGE_ATR_RATIO)
    if side == "LONG":
        return price + slip_amount
    else:
        return price - slip_amount


def simulate_fill(order: Dict, current_candle: dict, atr: float) -> Optional[Dict]:
    """
    Phase 8.7: Determine if a limit order would fill on this candle.
    Returns fill dict or None if no fill.

    Rules:
    - Limit: fills if candle range touches the zone
    - Volume threshold adds realistic fill probability
    """
    order_type = order.get("type", "LIMIT")
    side = order["side"]
    zone_low = order["entry_zone"][0]
    zone_high = order["entry_zone"][1]

    candle_low = current_candle["low"]
    candle_high = current_candle["high"]

    filled = False
    fill_price = None

    if order_type == "MARKET":
        fill_price = simulate_slippage(current_candle["open"], atr, side)
        filled = True

    elif order_type == "LIMIT":
        if side == "LONG" and candle_low <= zone_high:
            fill_price = simulate_slippage(min(zone_high, candle_low + atr * 0.1), atr, side)
            filled = True
        elif side == "SHORT" and candle_high >= zone_low:
            fill_price = simulate_slippage(max(zone_low, candle_high - atr * 0.1), atr, side)
            filled = True

    if filled and fill_price:
        return {
            "filled": True,
            "fill_price": fill_price,
            "slippage": abs(fill_price - (zone_low + zone_high) / 2),
            "time": current_candle["open_time"],
        }

    # Partial fill simulation
    if order_type == "LIMIT" and random.random() < 0.05:
        partial_size = order.get("size", 1.0) * random.uniform(0.3, 0.8)
        return {
            "filled": True,
            "partial": True,
            "fill_size": partial_size,
            "fill_price": (zone_low + zone_high) / 2,
            "time": current_candle["open_time"],
        }

    return None


async def simulate_latency(ms: int = PAPER_LATENCY_MS):
    """Phase 8.9: Simulate network/execution latency."""
    await asyncio.sleep(ms / 1000)
