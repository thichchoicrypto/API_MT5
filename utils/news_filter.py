"""
News Filter — Finnhub Economic Calendar.
Skip trading signals near high-impact US economic events (CPI, NFP, Fed, GDP...).

Usage:
    filter = NewsFilter()
    await filter.refresh()                         # fetch events (call once/day)
    filter.is_high_impact_window(datetime.now())   # True = skip signal
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import aiohttp
from utils.logger import logger


FINNHUB_API_KEY = ""   # set via .env: FINNHUB_API_KEY=...
FINNHUB_URL = "https://finnhub.io/api/v1/calendar/economic"

# Sự kiện US high-impact ảnh hưởng crypto mạnh nhất
HIGH_IMPACT_KEYWORDS = {
    "CPI", "Inflation Rate", "Core Inflation",
    "Non Farm Payrolls", "NFP",
    "Fed Interest Rate", "FOMC", "Fed Press Conference",
    "GDP", "Core PCE",
    "ISM Manufacturing", "ISM Services",
    "JOLTs",
}

# Bao nhiêu giờ trước/sau event thì skip signal
BUFFER_HOURS_BEFORE = 2   # skip 2h trước event
BUFFER_HOURS_AFTER  = 1   # skip 1h sau event


class NewsFilter:
    """
    Fetch và cache US high-impact economic events từ Finnhub.
    Dùng để filter signal trong backtest và live trading.
    """

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or FINNHUB_API_KEY
        self._events: List[Dict] = []
        self._last_refresh: Optional[datetime] = None

    def load_from_env(self):
        """Load API key từ environment."""
        import os
        key = os.getenv("FINNHUB_API_KEY", "")
        if key:
            self._api_key = key

    async def refresh(self, days_ahead: int = 7, days_back: int = 365 * 2):
        """
        Fetch events từ Finnhub.
        days_back: lấy data quá khứ (cho backtest) — mặc định 2 năm
        days_ahead: lấy data tương lai (cho live) — mặc định 7 ngày
        """
        if not self._api_key:
            logger.warning("[NewsFilter] No FINNHUB_API_KEY set — news filter disabled")
            return

        now = datetime.now(tz=timezone.utc)
        from_dt = now - timedelta(days=days_back)
        to_dt   = now + timedelta(days=days_ahead)

        # Finnhub max range per request = 30 days → paginate
        all_events = []
        cursor = from_dt
        chunk = timedelta(days=30)

        async with aiohttp.ClientSession() as session:
            while cursor < to_dt:
                end = min(cursor + chunk, to_dt)
                params = {
                    "from": cursor.strftime("%Y-%m-%d"),
                    "to":   end.strftime("%Y-%m-%d"),
                }
                headers = {"X-Finnhub-Token": self._api_key}
                try:
                    async with session.get(FINNHUB_URL, params=params,
                                           headers=headers,
                                           timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            events = data.get("economicCalendar", [])
                            # Chỉ giữ US high-impact
                            us_high = [
                                e for e in events
                                if e.get("country") == "US"
                                and e.get("impact") == "high"
                                and any(kw in e.get("event", "") for kw in HIGH_IMPACT_KEYWORDS)
                            ]
                            all_events.extend(us_high)
                        else:
                            logger.warning(f"[NewsFilter] Finnhub HTTP {resp.status}")
                except Exception as e:
                    logger.error(f"[NewsFilter] fetch error: {e}")

                cursor = end
                await asyncio.sleep(0.3)   # rate limit: 60 req/min free tier

        self._events = all_events
        self._last_refresh = now
        logger.info(f"[NewsFilter] Loaded {len(self._events)} US high-impact events "
                    f"({from_dt.date()} → {to_dt.date()})")

    def is_high_impact_window(self, candle_time: datetime) -> bool:
        """
        Returns True nếu candle_time nằm trong cửa sổ của 1 high-impact event.
        Cửa sổ = [event_time - BUFFER_HOURS_BEFORE, event_time + BUFFER_HOURS_AFTER]
        """
        if not self._events:
            return False

        if candle_time.tzinfo is None:
            candle_time = candle_time.replace(tzinfo=timezone.utc)

        for event in self._events:
            try:
                event_time = datetime.strptime(
                    event["time"], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)

                window_start = event_time - timedelta(hours=BUFFER_HOURS_BEFORE)
                window_end   = event_time + timedelta(hours=BUFFER_HOURS_AFTER)

                if window_start <= candle_time <= window_end:
                    logger.debug(
                        f"[NewsFilter] Skipping signal — near '{event['event']}' "
                        f"@ {event_time} (window: {window_start} → {window_end})"
                    )
                    return True
            except Exception:
                continue

        return False

    def get_upcoming(self, hours: int = 24) -> List[Dict]:
        """Trả về events trong N giờ tới (dùng để log/alert)."""
        now = datetime.now(tz=timezone.utc)
        result = []
        for event in self._events:
            try:
                event_time = datetime.strptime(
                    event["time"], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
                if now <= event_time <= now + timedelta(hours=hours):
                    result.append(event)
            except Exception:
                continue
        return result

    @property
    def event_count(self) -> int:
        return len(self._events)


# Singleton dùng trong backtest và live
news_filter = NewsFilter()
