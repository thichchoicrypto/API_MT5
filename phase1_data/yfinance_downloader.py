"""
Phase 1.5 — yfinance Historical Downloader (Mac/Linux).

Dùng khi chạy trên Mac/Linux (MetaTrader5 chỉ hỗ trợ Windows).
yfinance hỗ trợ Forex majors + Gold/Silver qua Yahoo Finance API.

⚠️  yfinance Forex (=X tickers) giới hạn:
  - 15m : period="60d"   (không dùng start/end với intraday Forex)
  - 1h  : period="2y"    ✅
  - 1d  : period="max"   ✅

→ Khuyến nghị: ENTRY_TIMEFRAME=1h trên Mac để có đủ 2 năm data backtest.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from utils.logger import logger
from config.settings import YFINANCE_SYMBOL_MAP, HISTORICAL_YEARS
from phase1_data.validator import validate_candles


# Period string cho từng timeframe (Forex =X không dùng start/end intraday)
_TF_PERIOD = {
    "1m":  "7d",
    "5m":  "60d",
    "15m": "60d",
    "30m": "60d",
    "1h":  "2y",
    "4h":  "2y",
    "1d":  "max",
}

_TF_INTERVAL = {
    "1m":"1m","5m":"5m","15m":"15m","30m":"30m",
    "1h":"1h","4h":"4h","1d":"1d",
}


class YFinanceDownloader:
    """Download historical OHLCV via yfinance. Works on Mac, Linux, Windows."""

    def __init__(self):
        try:
            import yfinance as yf
            self._yf = yf
        except ImportError:
            raise ImportError("yfinance not installed. Run: pip3 install yfinance")

    def connect(self) -> bool:
        logger.info("YFinanceDownloader ready")
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
        yf_sym   = YFINANCE_SYMBOL_MAP.get(symbol, symbol)
        interval = _TF_INTERVAL.get(timeframe, "1h")
        period   = _TF_PERIOD.get(timeframe, "2y")

        # Incremental: nếu có since và timeframe là daily → dùng start date
        # Intraday Forex =X: luôn dùng period (yfinance giới hạn start/end)
        is_intraday = timeframe not in ("1d",)
        use_period  = is_intraday  # Forex =X intraday phải dùng period

        logger.info(
            f"yfinance downloading {symbol} ({yf_sym}) {timeframe} "
            f"{'period=' + period if use_period else 'from ' + str(since.date() if since else 'max')} ..."
        )

        try:
            ticker = self._yf.Ticker(yf_sym)
            if use_period:
                df = ticker.history(
                    period      = period,
                    interval    = interval,
                    auto_adjust = True,
                    prepost     = False,
                )
            else:
                now   = datetime.now(tz=timezone.utc)
                start = since or (now - timedelta(days=365 * years))
                df = ticker.history(
                    start       = start.strftime("%Y-%m-%d"),
                    end         = now.strftime("%Y-%m-%d"),
                    interval    = interval,
                    auto_adjust = True,
                    prepost     = False,
                )
        except Exception as e:
            logger.error(f"yfinance error {symbol} {timeframe}: {e}")
            return []

        if df is None or df.empty:
            logger.warning(f"yfinance không có data {symbol} {timeframe}")
            return []

        candles = []
        for ts, row in df.iterrows():
            if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                open_time = ts.to_pydatetime().astimezone(timezone.utc)
            else:
                open_time = ts.to_pydatetime().replace(tzinfo=timezone.utc)
            candles.append({
                "symbol":    symbol,
                "timeframe": timeframe,
                "open_time": open_time,
                "open":      float(row["Open"]),
                "high":      float(row["High"]),
                "low":       float(row["Low"]),
                "close":     float(row["Close"]),
                "volume":    int(row.get("Volume", 0) or 0),
            })

        # Filter theo since nếu có (incremental update)
        if since:
            since_utc = since.replace(tzinfo=timezone.utc) if since.tzinfo is None else since
            candles = [c for c in candles if c["open_time"] > since_utc]

        validated = validate_candles(candles, symbol, timeframe)
        logger.info(f"yfinance downloaded {len(validated)} candles cho {symbol} {timeframe}")
        return validated

    async def fetch_range(self, symbol: str, timeframe: str,
                           start: datetime, end: datetime) -> List[dict]:
        """Dùng cho BackfillService — fallback về period nếu intraday."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._download_sync, symbol, timeframe, 2, None
        )
