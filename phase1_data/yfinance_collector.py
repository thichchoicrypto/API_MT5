"""
Phase 1.6 — yfinance Real-Time Collector (Mac/Linux paper trading).

Poll yfinance mỗi 60s để lấy closed candle.
Thay MT5StreamingCollector khi chạy trên Mac/Linux.

⚠️  Data delay ~1-15 phút. CHỈ dùng cho PAPER TRADING / LOCAL TESTING.
    Live trading thật → dùng MT5 trên Windows VPS.
"""
import asyncio
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from utils.logger import logger
from utils.telegram import telegram
from config.settings import (
    SYMBOLS, TIMEFRAMES, YFINANCE_SYMBOL_MAP,
    MT5_POLL_INTERVAL, WS_RECONNECT_DELAY,
)
from phase1_data.validator import validate_candle

_POLL_INTERVAL = max(MT5_POLL_INTERVAL, 60.0)   # tối thiểu 60s


class YFinanceStreamingCollector:
    """Poll yfinance cho closed candles — Mac/Linux replacement cho MT5StreamingCollector."""

    def __init__(self, symbols: List[str], timeframes: List[str], db,
                 on_candle: Optional[Callable] = None):
        self.symbols    = symbols
        self.timeframes = timeframes
        self.db         = db
        self.on_candle  = on_candle
        self._running   = False
        self._last_bar_time: Dict[str, Optional[datetime]] = {}

        for sym in symbols:
            for tf in timeframes:
                self._last_bar_time[f"{sym}_{tf}"] = None

        try:
            import yfinance as yf
            self._yf = yf
        except ImportError:
            raise ImportError("yfinance not installed. Run: pip install yfinance")

    def _get_interval(self, tf: str) -> str:
        return {"1m":"1m","5m":"5m","15m":"15m","30m":"30m",
                "1h":"1h","4h":"4h","1d":"1d"}.get(tf, "1h")

    def _fetch_latest_closed(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Fetch bar[-2] (last fully closed bar)."""
        yf_sym   = YFINANCE_SYMBOL_MAP.get(symbol, symbol)
        interval = self._get_interval(timeframe)
        period   = "1d" if timeframe in ("1h", "4h") else "5d"
        try:
            df = self._yf.download(
                tickers     = yf_sym,
                period      = period,
                interval    = interval,
                progress    = False,
                auto_adjust = True,
            )
        except Exception as e:
            logger.debug(f"yfinance poll {symbol} {timeframe}: {e}")
            return None

        if df is None or len(df) < 2:
            return None

        row = df.iloc[-2]
        ts  = df.index[-2]
        if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
            open_time = ts.to_pydatetime().astimezone(timezone.utc)
        else:
            open_time = ts.to_pydatetime().replace(tzinfo=timezone.utc)

        return {
            "symbol":    symbol,
            "timeframe": timeframe,
            "open_time": open_time,
            "open":      float(row["Open"]),
            "high":      float(row["High"]),
            "low":       float(row["Low"]),
            "close":     float(row["Close"]),
            "volume":    int(row.get("Volume", 0) or 0),
        }

    def _poll_once(self) -> List[dict]:
        new_candles = []
        for symbol in self.symbols:
            for tf in self.timeframes:
                key    = f"{symbol}_{tf}"
                candle = self._fetch_latest_closed(symbol, tf)
                if not candle:
                    continue
                last = self._last_bar_time.get(key)
                if last is None or candle["open_time"] > last:
                    self._last_bar_time[key] = candle["open_time"]
                    new_candles.append(candle)
        return new_candles

    async def start(self):
        loop = asyncio.get_event_loop()
        logger.info(
            f"[Mac] YFinanceStreamingCollector started "
            f"(poll {_POLL_INTERVAL:.0f}s | ⚠️  delay ~1-15min)"
        )
        await telegram.send(
            f"📡 [Mac] yfinance Collector | {', '.join(self.symbols)}\n"
            f"⚠️  Paper trading only — data delay ~1-15 phút"
        )
        self._running = True
        while self._running:
            try:
                new_candles = await loop.run_in_executor(None, self._poll_once)
                for candle in new_candles:
                    if validate_candle(candle):
                        if self.db:
                            try:
                                await self.db.upsert_candle(candle)
                            except Exception as e:
                                logger.error(f"DB upsert error: {e}")
                        if self.on_candle:
                            try:
                                await self.on_candle(candle)
                            except Exception as e:
                                logger.error(f"on_candle error: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"yfinance poll error: {e}", exc_info=True)
                await asyncio.sleep(WS_RECONNECT_DELAY)
            await asyncio.sleep(_POLL_INTERVAL)

    def stop(self):
        self._running = False
        logger.info("YFinanceStreamingCollector stopped")
