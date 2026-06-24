"""
Phase 4.2–4.3 — Fair Value Gap (FVG) Detection and Scoring.
"""
from typing import List, Optional, Dict
import numpy as np
from config.settings import FVG_MIN_ATR_RATIO, FVG_MIN_ATR_RATIO_OVERRIDE


def detect_fvg(candles: List[dict], symbol: str = "EURUSD") -> List[Dict]:
    """
    Phase 4.2: Detect FVGs across a candle list.
    FVG = 3-candle pattern where there's a gap between C1 and C3.

    Bullish FVG: C1.high < C3.low  → imbalance upward
    Bearish FVG: C1.low > C3.high → imbalance downward

    TẠI SAO FVG LÀ ĐIỂM VÀO LỆNH?
    FVG xảy ra khi giá di chuyển quá nhanh (thường do news hoặc institutional order).
    Tạo ra "khoảng trống" mà lệnh ở giữa không được fill đầy đủ.
    Market có xu hướng quay lại fill FVG trước khi tiếp tục xu hướng chính.
    → Bot chờ giá pullback về FVG zone rồi vào lệnh theo hướng trend.

    Điều kiện lọc: FVG phải có size >= 30% ATR (FVG_MIN_ATR_RATIO=0.3)
    → Loại bỏ FVG quá nhỏ (noise), chỉ giữ FVG có ý nghĩa.

    Chú ý: hàm này được gọi mỗi candle với window[-30:] — chỉ lấy FVG gần đây,
    tránh giữ FVG quá cũ không còn relevant.
    """
    if len(candles) < 3:
        return []

    atr = _calc_atr(candles)
    _ratio = FVG_MIN_ATR_RATIO_OVERRIDE.get(symbol, FVG_MIN_ATR_RATIO)
    min_size = atr * _ratio
    fvgs = []

    for i in range(len(candles) - 2):
        c1, c2, c3 = candles[i], candles[i + 1], candles[i + 2]

        # Bullish FVG
        if c1["high"] < c3["low"]:
            size = c3["low"] - c1["high"]
            if size >= min_size:
                fvgs.append({
                    "type": "BULLISH_FVG",
                    "zone": [c1["high"], c3["low"]],
                    "midpoint": (c1["high"] + c3["low"]) / 2,
                    "size": size,
                    "index": i,
                    "time": c2["open_time"],
                    "filled": False,
                })

        # Bearish FVG
        elif c1["low"] > c3["high"]:
            size = c1["low"] - c3["high"]
            if size >= min_size:
                fvgs.append({
                    "type": "BEARISH_FVG",
                    "zone": [c3["high"], c1["low"]],
                    "midpoint": (c3["high"] + c1["low"]) / 2,
                    "size": size,
                    "index": i,
                    "time": c2["open_time"],
                    "filled": False,
                })

    return fvgs


def score_fvg(fvg: Dict, bos_events: List[Dict], sweep_events: List[Dict],
              candles: List[dict]) -> int:
    """Phase 4.3: Score FVG quality."""
    score = 0
    atr = _calc_atr(candles)

    if bos_events:
        score += 2
    if sweep_events:
        score += 2

    # Volume spike near FVG
    if len(candles) > 0:
        avg_vol = np.mean([c["volume"] for c in candles[-20:]]) if len(candles) >= 20 else 0
        fvg_idx = fvg.get("index", 0)
        if fvg_idx < len(candles) and candles[fvg_idx]["volume"] > avg_vol * 1.5:
            score += 1

    # Size bonus
    if fvg["size"] > atr:
        score += 1

    return score


def update_fvg_fills(fvgs: List[Dict], current_candle: dict) -> List[Dict]:
    """Mark FVGs as filled when price CLOSES into the zone.
    Dùng close thay vì wick để tránh xóa zone khi trigger candle chỉ wick vào
    nhưng chưa close qua — zone cần tồn tại đến confirmation candle.

    TẠI SAO DÙNG CLOSE, KHÔNG DÙNG WICK?
    Kịch bản: nến trigger wick vào FVG zone, close ở rìa ngoài zone.
    Nếu dùng range overlap (wick) → FVG bị xóa ngay tại nến trigger.
    → Confirmation candle (1 nến sau) sẽ không còn zone để validate.
    → Bot không vào lệnh dù đây là setup đẹp.

    Dùng close → FVG chỉ bị xóa khi giá thực sự close vào trong zone.
    Trigger candle wick vào zone OK, close ngoài → zone còn tồn tại → confirm candle check được.

    QUAN TRỌNG: quyết định này ảnh hưởng số lượng signal.
    Backtest đã validate với logic close-only này (PF 2.22/3.23 với 1h).
    Nếu đổi sang range overlap → phải backtest lại toàn bộ.
    """
    active = []
    for fvg in fvgs:
        if not fvg["filled"]:
            lo, hi = fvg["zone"]
            price = current_candle["close"]
            if lo <= price <= hi:
                fvg["filled"] = True
        if not fvg["filled"]:
            active.append(fvg)
    return active


def _calc_atr(candles: List[dict], period: int = 14) -> float:
    if len(candles) < 2:
        return 1.0
    trs = []
    for i in range(1, min(period + 1, len(candles))):
        c = candles[i]
        p = candles[i - 1]
        tr = max(c["high"] - c["low"],
                 abs(c["high"] - p["close"]),
                 abs(c["low"] - p["close"]))
        trs.append(tr)
    return float(np.mean(trs)) if trs else 1.0
