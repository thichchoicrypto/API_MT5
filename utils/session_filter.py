"""
Forex Session Filter — chỉ trade trong giờ có thanh khoản cao.

Forex có 4 phiên chính (UTC):
  Tokyo:    00:00 – 09:00  (liquidity thấp với EUR/GBP pairs)
  London:   08:00 – 17:00  (liquidity cao nhất)
  New York: 13:00 – 22:00  (liquidity cao)
  Overlap:  13:00 – 17:00  (London + NY cùng mở — tốt nhất)
  Dead zone: 22:00 – 00:00  (rất thấp, spread rộng)

Chiến lược:
  - EUR/GBP pairs  → chỉ London + NY (08:00–22:00 UTC)
  - USD/JPY pairs  → London + NY + Tokyo OK (00:00–22:00 UTC)
  - XAU/USD (Gold) → London + NY (08:00–22:00 UTC)
  - Tất cả         → tránh dead zone 22:00–00:00 UTC
"""
from datetime import datetime, timezone, time
from typing import Optional
from utils.logger import logger


# ─────────────────────────────────────────────
# SESSION DEFINITIONS (UTC)
# ─────────────────────────────────────────────
SESSIONS = {
    "TOKYO":   (time(0,  0), time(9,  0)),   # 00:00 – 09:00
    "LONDON":  (time(8,  0), time(17, 0)),   # 08:00 – 17:00
    "NEW_YORK":(time(13, 0), time(22, 0)),   # 13:00 – 22:00
    "OVERLAP": (time(13, 0), time(17, 0)),   # London + NY overlap
    "DEAD":    (time(22, 0), time(0,  0)),   # 22:00 – 00:00 (split midnight)
}

# Active hours per symbol (UTC)
# Format: (start_hour, end_hour) — trade ONLY within this window
SYMBOL_SESSIONS = {
    # Major EUR/GBP pairs: London + NY only
    "EURUSD": (8,  22),
    "GBPUSD": (8,  22),
    "EURGBP": (8,  22),
    "EURJPY": (8,  22),
    "GBPJPY": (8,  22),
    # USD/JPY: Tokyo + London + NY (active 3 sessions)
    "USDJPY": (0,  22),
    # Commodity currencies: London + NY
    "AUDUSD": (8,  22),
    "NZDUSD": (8,  22),
    "USDCAD": (13, 22),   # most active NY session
    "USDCHF": (8,  22),
    # Gold: London + NY
    "XAUUSD": (8,  22),
    "XAGUSD": (8,  22),
}

# Default fallback: London + NY
DEFAULT_SESSION = (8, 22)


def is_trading_session(symbol: str, dt: Optional[datetime] = None) -> bool:
    """
    Returns True if dt falls within the active trading session for symbol.

    Rules:
    1. Never trade on weekends
    2. Never trade in dead zone (22:00–00:00 UTC)
    3. Only trade within symbol's active hours

    Args:
        symbol: internal symbol (EURUSD, GBPUSD, ...)
        dt: datetime to check (default: now UTC)
    """
    if dt is None:
        dt = datetime.now(tz=timezone.utc)

    # Ensure UTC — IBKR trả về bars với EDT timezone (-04:00), phải convert sang UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    # Weekend check
    if dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    hour = dt.hour

    # Dead zone: 22:00 – 00:00 UTC (spread very wide)
    if hour >= 22:
        return False

    # Symbol-specific session
    start_h, end_h = SYMBOL_SESSIONS.get(symbol, DEFAULT_SESSION)
    if hour < start_h or hour >= end_h:
        return False

    return True


def get_current_session(dt: Optional[datetime] = None) -> str:
    """Return name of current Forex session."""
    if dt is None:
        dt = datetime.now(tz=timezone.utc)
    hour = dt.hour

    if 13 <= hour < 17:
        return "OVERLAP (London+NY)"
    elif 8 <= hour < 17:
        return "LONDON"
    elif 17 <= hour < 22:
        return "NEW_YORK"
    elif 0 <= hour < 9:
        return "TOKYO"
    else:
        return "DEAD_ZONE"


def session_stop_reason(symbol: str, dt: datetime) -> Optional[str]:
    """Return stop reason string if outside session, else None."""
    # Convert to UTC (IBKR may return EDT timezone)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    if dt.weekday() >= 5:
        return "weekend"
    if dt.hour >= 22:
        return "dead_zone"
    start_h, end_h = SYMBOL_SESSIONS.get(symbol, DEFAULT_SESSION)
    if dt.hour < start_h:
        return f"pre_session (before {start_h:02d}:00 UTC)"
    if dt.hour >= end_h:
        return f"post_session (after {end_h:02d}:00 UTC)"
    return None
