"""
Phase 3.6–3.9 — CHoCH Detection + Structure Shift Confirmation.
"""
from typing import Optional, Dict, List


def detect_choch(trend: str, bos_event: Optional[Dict]) -> Optional[Dict]:
    """
    Phase 3.6: Change of Character detection.
    Bullish CHoCH: was DOWN, gets BOS_UP → potential reversal up
    Bearish CHoCH: was UP, gets BOS_DOWN → potential reversal down

    TẠI SAO CHoCH QUAN TRỌNG?
    CHoCH = dấu hiệu đầu tiên xu hướng có thể đảo chiều.

    Ví dụ Bullish CHoCH:
      Thị trường đang DOWN (LH + LL liên tiếp)
      → Đột nhiên có BOS_UP (close vượt swing high gần nhất)
      → Lần đầu tiên buyer đủ mạnh để phá structure → cấu trúc DOWN bị phá vỡ
      → "Change of Character" — không còn DOWN thuần túy nữa

    So sánh với Sweep:
      Sweep: giá test vùng thanh khoản (ngắn hạn, 1 nến)
      CHoCH: cấu trúc thay đổi (dài hạn hơn, cần BOS confirm)
      Bot dùng ít nhất 1 trong 2 để pass Layer 3.

    Tương tự Sweep, CHoCH cũng có TTL=20 candles trong live/backtest engine.
    """
    if bos_event is None:
        return None

    if trend in ("UP", "UPTREND") and bos_event["type"] == "BOS_DOWN":
        return {
            "type": "BEARISH_CHOCH",
            "price": bos_event["price"],
            "time": bos_event["time"],
            "confidence": _choch_confidence(bos_event),
        }

    if trend in ("DOWN", "DOWNTREND") and bos_event["type"] == "BOS_UP":
        return {
            "type": "BULLISH_CHOCH",
            "price": bos_event["price"],
            "time": bos_event["time"],
            "confidence": _choch_confidence(bos_event),
        }

    return None


def _choch_confidence(bos_event: Dict) -> float:
    """Placeholder: confidence based on BOS strength (extend with volume later)."""
    return 0.65


class StructureShiftTracker:
    """
    Phase 3.9: Confirms structure shift via CHoCH → BOS → Retest sequence.
    """

    def __init__(self):
        self._choch: Optional[Dict] = None
        self._confirming_bos: Optional[Dict] = None
        self._shift_confirmed: bool = False
        self._direction: Optional[str] = None

    def process(self, choch_event: Optional[Dict], bos_event: Optional[Dict],
                current_price: float) -> Dict:
        if choch_event:
            self._choch = choch_event
            self._confirming_bos = None
            self._shift_confirmed = False
            self._direction = "UP" if choch_event["type"] == "BULLISH_CHOCH" else "DOWN"

        if self._choch and bos_event and not self._confirming_bos:
            # Confirming BOS in same direction as CHoCH
            if self._direction == "UP" and bos_event["type"] == "BOS_UP":
                self._confirming_bos = bos_event
                self._shift_confirmed = True
            elif self._direction == "DOWN" and bos_event["type"] == "BOS_DOWN":
                self._confirming_bos = bos_event
                self._shift_confirmed = True

        return {
            "structure_shift": self._shift_confirmed,
            "direction": self._direction,
            "choch": self._choch,
            "confirming_bos": self._confirming_bos,
        }
