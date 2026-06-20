"""
Phase 1.7 — Twelve Data Historical Downloader (Mac/Linux).

Lấy được 2 năm 15m data cho Forex — thay yfinance cho intraday.
Free tier: 800 API credits/day, mỗi request = 1 credit, 5000 candles/request.

7 symbols × 2 năm × 15m ≈ 350,000 candles → ~70 requests → xong trong 1 lần chạy.

Đăng ký free: https://twelvedata.com
"""
import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from utils.logger import logger
from config.settings import HISTORICAL_YEARS
from phase1_data.validator import validate_candles

# Twelve Data symbol map (Forex format: EUR/USD)
TWELVE_SYMBOL_MAP = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
    "USDCHF": "USD/CHF",
    "NZDUSD": "NZD/USD",
    "EURGBP": "EUR/GBP",
    "EURJPY": "EUR/JPY",
    "GBPJPY": "GBP/JPY",
    "XAUUSD": "XAU/USD",
    "XAGUSD": "XAG/USD",
}

TWELVE_TF_MAP = {
    "1m":  "1min",
    "5m":  "5min",
    "15m": "15min",
    "30m": "30min",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "1day",
}

# Free tier: 8 requests/minute → sleep 8s giữa các requests
_REQUEST_DELAY = 8.0
_MAX_PER_REQUEST = 5000


class TwelveDataDownloader:
    """Download historical OHLCV via Twelve Data API."""

    def __init__(self, api_key: str = None):
        import os
        self._api_key = api_key or os.getenv("TWELVE_DATA_API_KEY", "")
        if not self._api_key:
            raise ValueError("TWELVE_DATA_API_KEY không có trong .env")

    def connect(self) -> bool:
        logger.info(f"TwelveDataDownloader ready (key=...{self._api_key[-6:]})")
        return True

    def disconnect(self):
        pass

    async def download_history(self, symbol: str, timeframe: str,
                                years: int = HISTORICAL_YEARS,
                                since: Optional[datetime] = None) -> List[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._download_sync, symbol, timeframe, years, since
        )

    def _download_sync(self, symbol: str, timeframe: str,
                        years: int, since: Optional[datetime]) -> List[dict]:
        import urllib.request
        import urllib.parse
        import json

        td_sym = TWELVE_SYMBOL_MAP.get(symbol, symbol)
        td_tf  = TWELVE_TF_MAP.get(timeframe, "15min")

        now   = datetime.now(tz=timezone.utc)
        start = since or (now - timedelta(days=365 * years))

        all_candles = []
        end_dt      = now

        logger.info(f"Twelve Data downloading {symbol} ({td_sym}) {timeframe} "
                    f"từ {start.date()} → {end_dt.date()} ...")

        page = 0
        while True:
            page += 1
            end_str   = end_dt.strftime("%Y-%m-%d %H:%M:%S")
            start_str = start.strftime("%Y-%m-%d %H:%M:%S")

            params = urllib.parse.urlencode({
                "symbol":     td_sym,
                "interval":   td_tf,
                "start_date": start_str,
                "end_date":   end_str,
                "outputsize": _MAX_PER_REQUEST,
                "order":      "ASC",
                "timezone":   "UTC",
                "apikey":     self._api_key,
            })
            url = f"https://api.twelvedata.com/time_series?{params}"

            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
            except Exception as e:
                logger.error(f"Twelve Data request error: {e}")
                break

            if data.get("status") == "error":
                logger.error(f"Twelve Data API error: {data.get('message')}")
                break

            values = data.get("values", [])
            if not values:
                logger.info(f"  Page {page}: no more data")
                break

            batch = []
            for v in values:
                try:
                    open_time = datetime.strptime(
                        v["datetime"], "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                    batch.append({
                        "symbol":    symbol,
                        "timeframe": timeframe,
                        "open_time": open_time,
                        "open":      float(v["open"]),
                        "high":      float(v["high"]),
                        "low":       float(v["low"]),
                        "close":     float(v["close"]),
                        "volume":    int(float(v.get("volume", 0) or 0)),
                    })
                except Exception:
                    continue

            all_candles.extend(batch)
            logger.info(f"  Page {page}: {len(batch)} candles "
                        f"({batch[0]['open_time'].date()} → {batch[-1]['open_time'].date()})")

            # Nếu đã đủ data hoặc đến điểm bắt đầu → stop
            if len(batch) < _MAX_PER_REQUEST:
                break
            if batch[0]["open_time"] <= start:
                break

            # Lùi end_dt về trước batch đầu tiên để lấy page tiếp theo
            end_dt = batch[0]["open_time"] - timedelta(minutes=1)

            # Rate limit: free tier 8 req/min
            time.sleep(_REQUEST_DELAY)

        # Deduplicate + sort
        seen = set()
        unique = []
        for c in sorted(all_candles, key=lambda x: x["open_time"]):
            k = c["open_time"].isoformat()
            if k not in seen:
                seen.add(k)
                unique.append(c)

        # Filter theo since
        if since:
            since_utc = since.replace(tzinfo=timezone.utc) if since.tzinfo is None else since
            unique = [c for c in unique if c["open_time"] > since_utc]

        validated = validate_candles(unique, symbol, timeframe)
        logger.info(f"Twelve Data: {len(validated)} candles cho {symbol} {timeframe}")
        return validated

    async def fetch_range(self, symbol: str, timeframe: str,
                           start: datetime, end: datetime) -> List[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._download_sync, symbol, timeframe, 2, start
        )
