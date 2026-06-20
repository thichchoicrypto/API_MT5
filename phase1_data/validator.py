"""
Phase 1.8 — Data Validation.
Validates OHLCV candles before writing to DB.

Forex-specific additions:
- Weekend gap detection (Forex closes Fri ~22:00 UTC, opens Sun ~22:00 UTC)
- Spread sanity check (high - low > 0 for real data)
"""
from datetime import datetime, timezone
from typing import Optional
from utils.logger import logger

TF_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900,
    "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
}


def tf_to_seconds(tf: str) -> int:
    return TF_SECONDS.get(tf, 60)


def is_weekend_candle(open_time: datetime) -> bool:
    """
    Returns True if the candle open_time falls on a Forex weekend close period.

    MT5 Forex actual close window:
      - Friday   from ~21:00 UTC  (last 15m candle observed: 20:45 UTC)
      - Saturday all day
      - Sunday   before ~21:00 UTC

    IMPORTANT: open_time từ MT5 là UTC. yfinance có thể trả về timezone-aware (UTC) hoặc naive.
    KHÔNG phải UTC. weekday()/hour bên dưới giả định UTC, nên phải convert
    sang UTC trước khi check — nếu không, candle ngay sau khi reopen
    (vd 22:00 UTC Sunday = 18:00 -04:00 Sunday, hour<21) sẽ bị tính nhầm
    thành weekend candle và bị validate_candle() loại bỏ âm thầm.
    """
    if open_time.tzinfo is not None:
        open_time = open_time.astimezone(timezone.utc)
    if open_time.weekday() == 4 and open_time.hour >= 21:  # Friday from 21:00 UTC
        return True
    if open_time.weekday() == 5:  # Saturday
        return True
    if open_time.weekday() == 6 and open_time.hour < 21:  # Sunday before 21:00 UTC
        return True
    return False


def validate_candle(candle: dict, symbol: str = "", tf: str = "",
                    allow_weekend: bool = False) -> bool:
    """
    Returns True if candle passes all OHLCV sanity checks.
    Minor OHLC inconsistencies (bid/ask mixing from data providers) are
    auto-corrected by clamping: high=max(o,h,c), low=min(o,l,c).
    """
    try:
        o = float(candle["open"])
        h = float(candle["high"])
        l = float(candle["low"])
        c = float(candle["close"])
        v = float(candle["volume"])
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"[{symbol} {tf}] candle parse error: {e}")
        return False

    # Hard failures — drop candle
    if o <= 0 or h <= 0 or l <= 0 or c <= 0:
        logger.warning(f"[{symbol} {tf}] non-positive price @ {candle.get('open_time')} — dropped")
        return False
    if v < 0:
        logger.warning(f"[{symbol} {tf}] negative volume @ {candle.get('open_time')} — dropped")
        return False

    # Soft failures — auto-clamp OHLC (common with Forex bid/ask mixing)
    fixed = False
    if h < max(o, c):
        candle["high"] = max(o, h, c)
        fixed = True
    if l > min(o, c):
        candle["low"] = min(o, l, c)
        fixed = True
    if fixed:
        logger.debug(f"[{symbol} {tf}] OHLC clamped @ {candle.get('open_time')}: "
                     f"O={o} H={candle['high']} L={candle['low']} C={c}")

    # Weekend gap filter
    if not allow_weekend:
        open_time = candle.get("open_time")
        if isinstance(open_time, datetime) and is_weekend_candle(open_time):
            logger.debug(f"[{symbol} {tf}] skipping weekend candle @ {open_time}")
            return False

    return True


def validate_candles(candles: list, symbol: str = "", tf: str = "",
                     allow_weekend: bool = False) -> list:
    """Filter and return only valid candles."""
    valid = [c for c in candles if validate_candle(c, symbol, tf, allow_weekend)]
    rejected = len(candles) - len(valid)
    if rejected:
        logger.debug(f"[{symbol} {tf}] rejected {rejected}/{len(candles)} candles (incl. weekends)")
    return valid
