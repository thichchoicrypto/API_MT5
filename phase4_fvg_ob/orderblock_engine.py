"""
Phase 4.4 — Order Block Detection.
OB = last opposing candle before a strong BOS move.
"""
from typing import List, Optional, Dict
from config.settings import OB_LOOKBACK, OB_LOOKBACK_OVERRIDE


def detect_order_block(candles: List[dict], bos_index: int, bos_type: str, symbol: str = "EURUSD") -> Optional[Dict]:
    """
    Phase 4.4: Find the last bearish candle before a bullish BOS (Bullish OB)
    or the last bullish candle before a bearish BOS (Bearish OB).

    TẠI SAO OB LÀ ĐIỂM VÀO LỆNH?
    Trước một BOS_UP mạnh, thường có nến bearish cuối cùng (smart money đang tích lũy lệnh mua).
    Nến bearish đó = "Order Block" = nơi tổ chức đặt lệnh mua lớn.
    Khi giá quay lại zone đó, tổ chức thường add thêm lệnh → giá bounce.

    Logic tìm OB:
      BOS_UP → tìm về trước tối đa OB_LOOKBACK=10 nến
      → Lấy nến bearish (close < open) CỰC CỦI gần BOS nhất
      → zone = [nến.low, nến.high]

    Tại sao lấy nến CUỐI CÙNG (gần BOS nhất)?
    Nến bearish gần BOS nhất = đợt bán cuối cùng trước khi smart money đẩy giá.
    Đây là điểm tổ chức vừa tích lũy xong → mạnh nhất.
    """
    _lookback = OB_LOOKBACK_OVERRIDE.get(symbol, OB_LOOKBACK)
    start = max(0, bos_index - _lookback)

    if bos_type == "BOS_UP":
        # Look back for last bearish candle → Bullish OB
        for i in range(bos_index - 1, start - 1, -1):
            c = candles[i]
            if c["close"] < c["open"]:  # bearish candle
                return {
                    "type": "BULLISH_OB",
                    "zone": [c["low"], c["high"]],
                    "midpoint": (c["low"] + c["high"]) / 2,
                    "index": i,
                    "time": c["open_time"],
                    "mitigated": False,
                }

    elif bos_type == "BOS_DOWN":
        # Look back for last bullish candle → Bearish OB
        for i in range(bos_index - 1, start - 1, -1):
            c = candles[i]
            if c["close"] > c["open"]:  # bullish candle
                return {
                    "type": "BEARISH_OB",
                    "zone": [c["low"], c["high"]],
                    "midpoint": (c["low"] + c["high"]) / 2,
                    "index": i,
                    "time": c["open_time"],
                    "mitigated": False,
                }

    return None


def detect_all_obs(candles: List[dict], bos_events: List[Dict], symbol: str = "EURUSD") -> List[Dict]:
    """Detect OBs for all BOS events in the list."""
    obs = []
    for bos in bos_events:
        # Map BOS time to candle index
        bos_idx = _find_candle_index(candles, bos.get("time"))
        if bos_idx is None:
            continue
        ob = detect_order_block(candles, bos_idx, bos["type"], symbol=symbol)
        if ob:
            obs.append(ob)
    return obs


def update_ob_mitigation(obs: List[Dict], current_candle: dict) -> List[Dict]:
    """Mark OBs as mitigated when price trades through them.

    OB "mitigated" = tổ chức đã fill hết lệnh tại zone này, không còn hiệu lực.
    Sau khi mitigated → xóa khỏi danh sách active (không dùng làm entry zone nữa).

    DÙNG CLOSE, KHÔNG DÙNG WICK (cùng lý do với FVG):
    Wick vào OB = test (giá kiểm tra zone, chưa fill hết).
    Close vào OB = tổ chức đã fill, zone không còn giá trị.
    Nếu dùng wick → OB bị xóa sớm → ít signal.
    Backtest đã validate với close-only.
    """
    active = []
    for ob in obs:
        if not ob["mitigated"]:
            lo, hi = ob["zone"]
            # OB mitigated khi candle CLOSE vào trong zone
            # (không dùng wick — wick chỉ là test, close xác nhận mitigation thật sự)
            price = current_candle["close"]
            if lo <= price <= hi:
                ob["mitigated"] = True
        if not ob["mitigated"]:
            active.append(ob)
    return active


def _find_candle_index(candles: List[dict], target_time) -> Optional[int]:
    """Find candle index by open_time. Normalizes tz-aware vs tz-naive datetimes."""
    if target_time is None:
        return None
    from datetime import timezone as _tz
    # Normalize target to UTC-aware
    if hasattr(target_time, "tzinfo") and target_time.tzinfo is None:
        target_time = target_time.replace(tzinfo=_tz.utc)
    for i, c in enumerate(candles):
        t = c["open_time"]
        if hasattr(t, "tzinfo") and t.tzinfo is None:
            t = t.replace(tzinfo=_tz.utc)
        if t == target_time:
            return i
    return None
