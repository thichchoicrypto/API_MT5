"""
Phase 1.8 — Dukascopy Bi5 Tick Data Downloader (Mac/Linux).

Dukascopy cung cấp tick data miễn phí qua binary bi5 format.
Endpoint: https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YEAR}/{MM}/{DD}/{HH}h_ticks.bi5

- Bid price, chất lượng ngân hàng Thụy Sĩ
- 2+ năm lịch sử cho tất cả Forex + Gold
- Không cần tài khoản, không cần API key
- Tự động aggregate tick → OHLCV bars

Bi5 format (mỗi record = 20 bytes, big-endian):
  uint32  : ms from start of hour
  uint32  : ask * divisor
  uint32  : bid * divisor
  float32 : ask volume
  float32 : bid volume

Price divisor:
  Forex (không JPY): 100000  (e.g. 108520 → 1.08520)
  JPY pairs:          1000   (e.g. 108520 → 108.520)
  XAUUSD:            10000   (e.g. 1234560 → 1234.560)
  XAGUSD:           100000
"""
import asyncio
import io
import lzma
import struct
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict

# Ensure project root in path
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.logger import logger
from config.settings import HISTORICAL_YEARS
from phase1_data.validator import validate_candles

# ─────────────────────────────────────────────
# SYMBOL MAP  (internal → Dukascopy)
# ─────────────────────────────────────────────
DUKA_SYMBOL_MAP = {
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD", "USDCAD": "USDCAD", "USDCHF": "USDCHF",
    "NZDUSD": "NZDUSD", "EURGBP": "EURGBP", "EURJPY": "EURJPY",
    "GBPJPY": "GBPJPY", "XAUUSD": "XAUUSD", "XAGUSD": "XAGUSD",
}

# Price divisor per symbol
PRICE_DIVISOR: Dict[str, int] = {
    "USDJPY": 1000,  "EURJPY": 1000,  "GBPJPY": 1000,
    "AUDJPY": 1000,  "CADJPY": 1000,  "CHFJPY": 1000,
    "XAUUSD": 10000,
}
DEFAULT_DIVISOR = 100000

# Timeframe → seconds
TF_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
}

_BASE = "https://datafeed.dukascopy.com/datafeed"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer":    "https://www.dukascopy.com/",
}
_SLEEP_BETWEEN_DAYS = 0.3   # giây, lịch sự với server


class DukascopyDownloader:
    """Download lịch sử OHLCV từ Dukascopy bi5 tick feed."""

    def __init__(self):
        # Tick cache: {symbol: (start_dt, end_dt, [(ts_ms, bid), ...])}
        # Tránh download cùng tick data 2 lần cho 15m + 1h
        self._tick_cache: Dict[str, tuple] = {}

    def connect(self) -> bool:
        logger.info("DukascopyDownloader ready (bi5 feed, no API key needed)")
        return True

    def disconnect(self):
        pass

    # ── public API ─────────────────────────────
    async def download_history(self, symbol: str, timeframe: str,
                                years: int = HISTORICAL_YEARS,
                                since: Optional[datetime] = None) -> List[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._download_sync, symbol, timeframe, years, since
        )

    async def fetch_range(self, symbol: str, timeframe: str,
                           start: datetime, end: datetime) -> List[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._download_sync, symbol, timeframe, 2, start
        )

    # ── internal ───────────────────────────────
    def _download_sync(self, symbol: str, timeframe: str,
                       years: int, since: Optional[datetime]) -> List[dict]:

        duka_sym = DUKA_SYMBOL_MAP.get(symbol)
        tf_secs  = TF_SECONDS.get(timeframe)
        divisor  = PRICE_DIVISOR.get(symbol, DEFAULT_DIVISOR)

        if not duka_sym:
            logger.error(f"Dukascopy: unsupported symbol {symbol}")
            return []
        if not tf_secs:
            logger.error(f"Dukascopy: unsupported timeframe {timeframe}")
            return []

        now   = datetime.now(tz=timezone.utc)
        start = since or (now - timedelta(days=365 * years))

        # Align start to day boundary
        cur_day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # ── Tick cache hit? ───────────────────────
        cached = self._tick_cache.get(symbol)
        if cached:
            cache_start, cache_end, cached_ticks = cached
            if cache_start <= cur_day and cache_end >= end_day:
                logger.info(f"Dukascopy {symbol} {timeframe}: using cached ticks "
                            f"({len(cached_ticks):,} ticks)")
                all_ticks = cached_ticks
            else:
                cached = None  # Cache miss, cần download lại

        if not cached:
            logger.info(f"Dukascopy {symbol} {timeframe} bi5: "
                        f"{cur_day.date()} → {end_day.date()} ...")

            all_ticks: List[tuple] = []
            days_done  = 0
            days_total = (end_day - cur_day).days
            _cur = cur_day

            while _cur <= end_day:
                if _cur.weekday() in (5, 6):
                    _cur += timedelta(days=1)
                    continue

                day_ticks = self._download_day(duka_sym, _cur, divisor)
                if day_ticks:
                    all_ticks.extend(day_ticks)

                days_done += 1
                if days_done % 30 == 0:
                    pct = days_done / max(days_total, 1) * 100
                    logger.info(f"  {symbol}: {days_done}/{days_total} days ({pct:.0f}%) "
                                f"— {len(all_ticks):,} ticks so far")

                _cur += timedelta(days=1)
                time.sleep(_SLEEP_BETWEEN_DAYS)

            # Lưu vào cache cho timeframe tiếp theo
            self._tick_cache[symbol] = (cur_day, end_day, all_ticks)

        if not all_ticks:
            logger.warning(f"Dukascopy: no ticks downloaded for {symbol} {timeframe}")
            return []

        logger.info(f"  {symbol}: {len(all_ticks):,} total ticks → aggregating to {timeframe} ...")
        candles = self._aggregate(all_ticks, symbol, timeframe, tf_secs)

        # Filter theo since
        if since:
            since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
            candles = [c for c in candles if c["open_time"] > since_utc]

        validated = validate_candles(candles, symbol, timeframe)
        logger.info(f"Dukascopy: {len(validated)} candles cho {symbol} {timeframe}")
        return validated

    def _download_day(self, duka_sym: str, day: datetime,
                       divisor: int) -> List[tuple]:
        """Download tất cả 24 giờ của 1 ngày → list of (timestamp_ms, bid_price)."""
        day_ticks = []
        year  = day.year
        month = day.month - 1   # Dukascopy: 0-indexed month!
        dom   = day.day

        for hour in range(24):
            url = f"{_BASE}/{duka_sym}/{year}/{month:02d}/{dom:02d}/{hour:02d}h_ticks.bi5"
            try:
                req = urllib.request.Request(url, headers=_HEADERS)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue   # Không có data cho giờ này (bình thường)
                logger.debug(f"HTTP {e.code} for {url}")
                continue
            except Exception as e:
                logger.debug(f"Error downloading {url}: {e}")
                continue

            if not raw:
                continue

            # Decompress LZMA
            try:
                decompressed = lzma.decompress(raw)
            except Exception as e:
                logger.debug(f"LZMA decompress error for {url}: {e}")
                continue

            # Parse binary records (20 bytes each)
            record_size = 20
            n_records   = len(decompressed) // record_size
            hour_base_ms = int(day.replace(hour=hour, minute=0,
                                           second=0, microsecond=0).timestamp() * 1000)

            for i in range(n_records):
                offset = i * record_size
                chunk  = decompressed[offset : offset + record_size]
                if len(chunk) < record_size:
                    break
                try:
                    ms_in_hour, ask_raw, bid_raw, _, _ = struct.unpack(">IIIff", chunk)
                    bid = bid_raw / divisor
                    ts  = hour_base_ms + ms_in_hour
                    day_ticks.append((ts, bid))
                except struct.error:
                    continue

        return day_ticks

    def _aggregate(self, ticks: List[tuple], symbol: str,
                   timeframe: str, tf_secs: int) -> List[dict]:
        """Aggregate tick list → OHLCV candles."""
        if not ticks:
            return []

        tf_ms = tf_secs * 1000
        candles: Dict[int, dict] = {}

        for ts_ms, bid in ticks:
            # Align to bar start
            bar_ms = (ts_ms // tf_ms) * tf_ms
            if bar_ms not in candles:
                candles[bar_ms] = {
                    "symbol":    symbol,
                    "timeframe": timeframe,
                    "open_time": datetime.fromtimestamp(bar_ms / 1000, tz=timezone.utc),
                    "open":      bid,
                    "high":      bid,
                    "low":       bid,
                    "close":     bid,
                    "volume":    0,
                }
            else:
                c = candles[bar_ms]
                if bid > c["high"]: c["high"]  = bid
                if bid < c["low"]:  c["low"]   = bid
                c["close"]  = bid
            candles[bar_ms]["volume"] += 1  # tick count as volume

        return sorted(candles.values(), key=lambda x: x["open_time"])


# ─────────────────────────────────────────────
# CLI test
# ─────────────────────────────────────────────
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    async def test():
        dl = DukascopyDownloader()
        dl.connect()

        # Test 3 ngày EURUSD 15m
        since = datetime.now(tz=timezone.utc) - timedelta(days=3)
        candles = await dl.download_history("EURUSD", "15m", years=1, since=since)
        if candles:
            print(f"\n✅ EURUSD 15m: {len(candles)} candles")
            print(f"   First: {candles[0]['open_time']}  O={candles[0]['open']:.5f}")
            print(f"   Last:  {candles[-1]['open_time']}  C={candles[-1]['close']:.5f}")
        else:
            print("\n❌ No data returned")

    asyncio.run(test())
