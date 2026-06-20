"""
Phase 1.9 + 1.10 — Missing Candle Detector & Backfill Service.
Forex-specific: skips weekend periods in gap detection.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List
from utils.logger import logger
from utils.telegram import telegram
from config.settings import SYMBOLS, TIMEFRAMES
from phase1_data.validator import tf_to_seconds


class BackfillService:
    def __init__(self, db, downloader):
        self.db = db
        self.downloader = downloader

    async def check_and_fill(self, symbol: str, timeframe: str,
                              lookback_hours: int = 24) -> tuple[int, int]:
        """
        Detect and backfill missing candles within the last N hours.
        Returns (missing_count, filled_count) — caller handles Telegram.
        """
        now   = datetime.now(tz=timezone.utc)
        start = now - timedelta(hours=lookback_hours)
        missing = await self.db.find_missing_candles(symbol, timeframe, start, now)

        if not missing:
            return 0, 0

        # Bỏ qua nếu chỉ thiếu 1-2 candle 15m/5m — thường là candle vừa đóng
        # lúc bot restart, collector polling chưa có đủ data ngay lập tức. Streaming
        # sẽ tự fill khi candle tiếp theo đến.
        tf_step = tf_to_seconds(timeframe)
        now = datetime.now(tz=timezone.utc)
        real_missing = [ts for ts in missing
                        if (now - ts).total_seconds() > tf_step * 2]
        if not real_missing:
            logger.debug(f"[{symbol} {timeframe}] {len(missing)} missing candle(s) too recent — skip backfill")
            return 0, 0

        n_missing = len(real_missing)
        missing = real_missing
        logger.warning(f"Missing {n_missing} candles for {symbol} {timeframe}, backfilling ...")

        step = tf_to_seconds(timeframe)
        ranges = _group_consecutive(missing, step)
        filled = 0
        for (start_dt, end_dt) in ranges:
            candles = await self.downloader.fetch_range(
                symbol, timeframe,
                start_dt,
                end_dt + timedelta(seconds=step)
            )
            if candles:
                cnt = await self.db.upsert_candles_bulk(symbol, timeframe, candles)
                filled += cnt

        logger.info(f"Backfill complete: {filled} candles for {symbol} {timeframe}")
        return n_missing, filled

    async def run_all(self, lookback_hours: int = 24):
        """
        Run backfill for all symbols/timeframes.
        Gom kết quả thành 1 Telegram message duy nhất thay vì spam per-symbol.
        """
        issues = []   # (symbol, tf, missing, filled)
        for symbol in SYMBOLS:
            for tf in TIMEFRAMES:
                n_missing, filled = await self.check_and_fill(symbol, tf, lookback_hours)
                if n_missing > 0:
                    issues.append((symbol, tf, n_missing, filled))
                await asyncio.sleep(0.2)

        if not issues:
            return

        # Chỉ gửi Telegram nếu có ít nhất 1 symbol thực sự được fill
        any_filled = any(f > 0 for _, _, _, f in issues)
        if not any_filled:
            logger.info("Backfill: all gaps too recent — streaming will fill naturally")
            return

        # Group by symbol → {symbol: {tf: (missing, filled)}}
        by_symbol: dict = {}
        for symbol, tf, n_missing, filled in issues:
            by_symbol.setdefault(symbol, {})[tf] = (n_missing, filled)

        lines = ["📋 Backfill:"]
        for symbol, tfs in by_symbol.items():
            parts = []
            for tf, (m, f) in tfs.items():
                icon = "✅" if f > 0 else "⚠️"
                parts.append(f"{tf} {icon}{f}/{m}")
            lines.append(f"  {symbol}: {' | '.join(parts)}")
        await telegram.send("\n".join(lines))


def _group_consecutive(timestamps: List[datetime], step_s: int):
    """Group list of datetimes into (start, end) ranges of consecutive gaps."""
    if not timestamps:
        return []
    ranges = []
    start = timestamps[0]
    prev  = timestamps[0]
    for ts in timestamps[1:]:
        if (ts - prev).total_seconds() <= step_s * 1.5:
            prev = ts
        else:
            ranges.append((start, prev))
            start = ts
            prev  = ts
    ranges.append((start, prev))
    return ranges
