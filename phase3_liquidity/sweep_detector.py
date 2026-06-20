"""
Phase 3.5 + 3.8 — Liquidity Sweep Detection + Market Trap Detection.
"""
from typing import Optional, Dict


def detect_sweep(candle: dict,
                 last_swing_high: Optional[float],
                 last_swing_low: Optional[float]) -> Optional[Dict]:
    """
    Phase 3.5: Detect bullish/bearish liquidity sweep.

    Bullish sweep: wick below swing low, close back above → trapped sellers
    Bearish sweep: wick above swing high, close back below → trapped buyers

    TẠI SAO SWEEP QUAN TRỌNG?
    Lệnh stop loss của traders Long thường nằm ngay dưới swing low.
    Khi giá wick xuống dưới swing low → stop loss bị kích hoạt (thanh khoản được thu)
    → Smart money đã fill lệnh mua của họ.
    → Sau đó không còn áp lực bán → giá đảo chiều lên.

    Điều kiện: low < swing_low AND close > swing_low
    (wick vượt qua, nhưng nến đóng lại ở trên → rejection rõ ràng)

    Sau khi detect, sự kiện này được giữ trong TTL=20 candles (live_engine + backtest_engine).
    Lý do TTL: sweep cách đây 5 nến vẫn là context hợp lệ cho entry tiếp theo.
    """
    if last_swing_high is None or last_swing_low is None:
        return None

    h = candle["high"]
    l = candle["low"]
    c = candle["close"]

    # Bullish sweep — quét đáy
    if l < last_swing_low and c > last_swing_low:
        return {
            "type": "BUY_SIDE_SWEEP",
            "swept_level": last_swing_low,
            "wick_low": l,
            "close": c,
            "time": candle["open_time"],
            "strength": _sweep_strength(l, last_swing_low, c),
        }

    # Bearish sweep — quét đỉnh
    if h > last_swing_high and c < last_swing_high:
        return {
            "type": "SELL_SIDE_SWEEP",
            "swept_level": last_swing_high,
            "wick_high": h,
            "close": c,
            "time": candle["open_time"],
            "strength": _sweep_strength(last_swing_high, h, c),
        }

    return None


def detect_liquidity_trap(candle: dict, level: float, direction: str = "UP") -> bool:
    """
    Phase 3.8: Fake breakout / liquidity trap detection.
    direction="UP": high broke above level but closed below
    direction="DOWN": low broke below level but closed above
    """
    if direction == "UP":
        return candle["high"] > level and candle["close"] < level
    if direction == "DOWN":
        return candle["low"] < level and candle["close"] > level
    return False


def _sweep_strength(swept: float, extreme: float, close: float) -> str:
    """Classify sweep strength by wick size vs distance swept."""
    wick = abs(extreme - swept)
    recovery = abs(close - swept)
    ratio = recovery / wick if wick > 0 else 0
    if ratio > 0.7:
        return "strong"
    if ratio > 0.4:
        return "medium"
    return "weak"
