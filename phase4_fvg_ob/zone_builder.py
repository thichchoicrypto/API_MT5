"""
Phase 4.5–4.9 — FVG + OB Confluence, Entry Zone Builder, MTF Alignment.
"""
from typing import List, Optional, Dict, Tuple
from utils.logger import logger


def find_confluence_zones(fvgs: List[Dict], obs: List[Dict]) -> List[Dict]:
    """
    Phase 4.5: Find zones where FVG and OB overlap.
    Overlap = strongest entry zone.
    """
    confluence = []
    for fvg in fvgs:
        for ob in obs:
            # Types must align (both bullish or both bearish)
            if fvg["type"].split("_")[0] != ob["type"].split("_")[0]:
                continue
            overlap = _zone_overlap(fvg["zone"], ob["zone"])
            if overlap:
                confluence.append({
                    "type": f"{fvg['type'].split('_')[0]}_CONFLUENCE",
                    "zone": overlap,
                    "fvg": fvg,
                    "ob": ob,
                    "strength": "HIGH",
                })
    return confluence


def build_entry_zone(side: str,
                     fvgs: List[Dict],
                     obs: List[Dict],
                     confluence: List[Dict],
                     current_price: Optional[float] = None,
                     atr: Optional[float] = None) -> Optional[Dict]:
    """
    Phase 4.7: Build the best entry zone for a given side.
    Priority: confluence > OB > FVG
    If current_price and atr provided, only return zones within 3×ATR of price.

    TẠI SAO PRIORITY CONFLUENCE > OB > FVG?
    Confluence (OB + FVG overlap) = 2 lý do tổ chức mua/bán tại cùng 1 vùng → mạnh nhất.
    OB đơn lẻ = institutional memory nhưng không có imbalance.
    FVG đơn lẻ = imbalance nhưng không có institutional memory.

    TẠI SAO FILTER 3×ATR?
    Zone cách giá hiện tại > 3×ATR = giá khó có thể đến trong 1-2 candles tới.
    Chỉ xét zone "trong tầm với" → tránh signal quá xa thực tế.

    Order type consequence (trong entry_engine._build_signal):
      CONFLUENCE / ORDER_BLOCK → LIMIT order @ midpoint (fill tốt hơn)
      FVG → MARKET order (fill ngay, không chờ pullback về exact midpoint)
    """
    direction_prefix = "BULLISH" if side == "LONG" else "BEARISH"

    def _near_price(zone_lo: float, zone_hi: float) -> bool:
        """Zone must be within 3×ATR of current price to be relevant."""
        if current_price is None or atr is None or atr <= 0:
            return True
        mid = (zone_lo + zone_hi) / 2
        return abs(mid - current_price) <= atr * 3

    # Try confluence first
    for zone in confluence:
        if direction_prefix in zone["type"]:
            lo, hi = zone["zone"][0], zone["zone"][1]
            if _near_price(lo, hi):
                return {
                    "side": side,
                    "low": lo,
                    "high": hi,
                    "midpoint": (lo + hi) / 2,
                    "source": "CONFLUENCE",
                    "strength": "HIGH",
                }

    # OB — pick closest to current price
    valid_obs = [
        ob for ob in obs
        if direction_prefix in ob["type"]
        and not ob.get("mitigated")
        and _near_price(ob["zone"][0], ob["zone"][1])
    ]
    if valid_obs and current_price:
        best = min(valid_obs, key=lambda o: abs(o["midpoint"] - current_price))
    elif valid_obs:
        best = valid_obs[0]
    else:
        best = None

    if best:
        return {
            "side": side,
            "low": best["zone"][0],
            "high": best["zone"][1],
            "midpoint": best["midpoint"],
            "source": "ORDER_BLOCK",
            "strength": "MEDIUM",
        }

    # FVG — pick closest to current price
    valid_fvgs = [
        fvg for fvg in fvgs
        if direction_prefix in fvg["type"]
        and not fvg.get("filled")
        and _near_price(fvg["zone"][0], fvg["zone"][1])
    ]
    if valid_fvgs and current_price:
        best_fvg = min(valid_fvgs, key=lambda f: abs(f["midpoint"] - current_price))
    elif valid_fvgs:
        best_fvg = valid_fvgs[0]
    else:
        best_fvg = None

    if best_fvg:
        return {
            "side": side,
            "low": best_fvg["zone"][0],
            "high": best_fvg["zone"][1],
            "midpoint": best_fvg["midpoint"],
            "source": "FVG",
            "strength": "MEDIUM",
        }

    return None


def _zone_overlap(zone1: List[float], zone2: List[float]) -> Optional[List[float]]:
    lo = max(zone1[0], zone2[0])
    hi = min(zone1[1], zone2[1])
    if lo < hi:
        return [lo, hi]
    return None
