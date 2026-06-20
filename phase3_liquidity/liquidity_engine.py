"""
Phase 3.2–3.4 — Liquidity Zone Mapping.
Detects equal highs/lows and builds liquidity pool map.
"""
from typing import List, Dict, Optional
from config.settings import EQUAL_HIGH_THRESHOLD


def detect_equal_highs(swing_highs: List[Dict], threshold: float = EQUAL_HIGH_THRESHOLD) -> List[Dict]:
    """
    Phase 3.3: Detect equal highs (buy-side liquidity above).
    Returns list of equal-high zone dicts.
    """
    zones = []
    for i in range(len(swing_highs)):
        for j in range(i + 1, len(swing_highs)):
            h1 = swing_highs[i]["price"]
            h2 = swing_highs[j]["price"]
            if h1 <= 0:
                continue
            if abs(h1 - h2) / h1 <= threshold:
                zones.append({
                    "type": "equal_high",
                    "zone": [min(h1, h2), max(h1, h2)],
                    "strength": "high_liquidity",
                    "time1": swing_highs[i]["time"],
                    "time2": swing_highs[j]["time"],
                })
    return zones


def detect_equal_lows(swing_lows: List[Dict], threshold: float = EQUAL_HIGH_THRESHOLD) -> List[Dict]:
    """Phase 3.3: Detect equal lows (sell-side liquidity below)."""
    zones = []
    for i in range(len(swing_lows)):
        for j in range(i + 1, len(swing_lows)):
            l1 = swing_lows[i]["price"]
            l2 = swing_lows[j]["price"]
            if l1 <= 0:
                continue
            if abs(l1 - l2) / l1 <= threshold:
                zones.append({
                    "type": "equal_low",
                    "zone": [min(l1, l2), max(l1, l2)],
                    "strength": "high_liquidity",
                    "time1": swing_lows[i]["time"],
                    "time2": swing_lows[j]["time"],
                })
    return zones


def build_liquidity_zones(swing_highs: List[Dict], swing_lows: List[Dict]) -> List[Dict]:
    """
    Phase 3.4: Build full liquidity zone map.
    buy_side_liquidity = above price (equal/swing highs) → target for short, SL for long
    sell_side_liquidity = below price (equal/swing lows) → target for long, SL for short
    """
    zones: List[Dict] = []

    # Swing high clusters → buy-side liquidity
    for sh in swing_highs[-5:]:
        zones.append({
            "type": "buy_side_liquidity",
            "price_zone": [sh["price"] * 0.999, sh["price"] * 1.001],
            "price": sh["price"],
            "time": sh["time"],
            "source": "swing_high",
        })

    # Swing low clusters → sell-side liquidity
    for sl in swing_lows[-5:]:
        zones.append({
            "type": "sell_side_liquidity",
            "price_zone": [sl["price"] * 0.999, sl["price"] * 1.001],
            "price": sl["price"],
            "time": sl["time"],
            "source": "swing_low",
        })

    # Equal highs/lows
    for eq in detect_equal_highs(swing_highs):
        zones.append({
            "type": "buy_side_liquidity",
            "price_zone": eq["zone"],
            "price": sum(eq["zone"]) / 2,
            "strength": "equal_high",
            "source": "equal_high",
        })
    for eq in detect_equal_lows(swing_lows):
        zones.append({
            "type": "sell_side_liquidity",
            "price_zone": eq["zone"],
            "price": sum(eq["zone"]) / 2,
            "strength": "equal_low",
            "source": "equal_low",
        })

    return zones
