"""
Phase 1.5b — MetaTrader 5 Historical Downloader (Secondary / Backup).

⚠️  WINDOWS ONLY: MetaTrader5 Python package only works on Windows
    with MT5 terminal installed and running.

On Linux/Mac VPS, set MT5_ENABLED=false (default) in .env.
This module is skipped unless MT5_ENABLED=true.

Usage:
  from phase1_data.mt5_downloader import MT5Downloader
  # Check MT5_ENABLED before instantiating
  downloader = MT5Downloader()
  candles = await downloader.download_history("EURUSD", "1h")
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from utils.logger import logger
from config.settings import (
    MT5_ENABLED, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER,
    MT5_SYMBOL_MAP, MT5_TF_MAP, HISTORICAL_YEARS, BROKER_TZ_OFFSET
)
from phase1_data.validator import validate_candles


class MT5Downloader:
    """
    Download historical candles from MetaTrader 5.
    Requires MetaTrader5 package and Windows + MT5 terminal.
    """

    def __init__(self):
        if not MT5_ENABLED:
            raise RuntimeError(
                "MT5 is disabled (MT5_ENABLED=false). "
                "Set MT5_ENABLED=true in .env and run on Windows with MT5 terminal."
            )
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
        except ImportError:
            raise ImportError(
                "MetaTrader5 package not installed. "
                "Run: pip install MetaTrader5  (Windows only)"
            )

    def connect(self) -> bool:
        """Initialize MT5 connection."""
        mt5 = self._mt5
        if not mt5.initialize():
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False
        if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
            if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                mt5.shutdown()
                return False
        logger.info("MT5 connected successfully")
        return True

    def disconnect(self):
        self._mt5.shutdown()

    def _get_tf_constant(self, timeframe: str):
        """Get MT5 TIMEFRAME constant from string."""
        tf_name = MT5_TF_MAP.get(timeframe, "TIMEFRAME_H1")
        return getattr(self._mt5, tf_name, self._mt5.TIMEFRAME_H1)

    async def download_history(self, symbol: str, timeframe: str,
                                years: int = HISTORICAL_YEARS,
                                since: Optional[datetime] = None) -> List[dict]:
        """
        Download historical candles from MT5.
        Runs MT5 calls in thread executor (MT5 is synchronous).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._download_sync, symbol, timeframe, years, since
        )

    def _download_sync(self, symbol: str, timeframe: str,
                        years: int, since: Optional[datetime]) -> List[dict]:
        """Synchronous MT5 download (must run in executor)."""
        mt5 = self._mt5
        mt5_symbol = MT5_SYMBOL_MAP.get(symbol, symbol)
        tf_const   = self._get_tf_constant(timeframe)

        now   = datetime.now(tz=timezone.utc)
        start = since or (now - timedelta(days=365 * years))

        logger.info(f"MT5 downloading {symbol} {timeframe} from {start.date()} ...")

        # MT5 copy_rates_range nhận thời gian theo broker server local (ICMarkets = UTC+3)
        # Phải cộng offset vào start/end trước khi pass vào MT5
        broker_offset = timedelta(hours=BROKER_TZ_OFFSET)
        import numpy as np
        rates = mt5.copy_rates_range(
            mt5_symbol, tf_const,
            (start + broker_offset).replace(tzinfo=None),
            (now + broker_offset).replace(tzinfo=None)
        )

        if rates is None or len(rates) == 0:
            logger.error(f"MT5 no data for {symbol} {timeframe}: {mt5.last_error()}")
            return []

        candles = []
        for r in rates:
            candles.append({
                "symbol":    symbol,
                "timeframe": timeframe,
                # MT5 time = broker local (UTC+3) → convert về UTC thật
                "open_time": datetime.fromtimestamp(r["time"] - BROKER_TZ_OFFSET * 3600, tz=timezone.utc),
                "open":      float(r["open"]),
                "high":      float(r["high"]),
                "low":       float(r["low"]),
                "close":     float(r["close"]),
                "volume":    int(r["tick_volume"]),
            })

        validated = validate_candles(candles, symbol, timeframe)
        logger.info(f"MT5 downloaded {len(validated)} candles for {symbol} {timeframe}")
        return validated

    async def fetch_range(self, symbol: str, timeframe: str,
                          start: datetime, end: datetime) -> List[dict]:
        """Fetch candles for specific date range."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._download_sync, symbol, timeframe,
            HISTORICAL_YEARS, start
        )
