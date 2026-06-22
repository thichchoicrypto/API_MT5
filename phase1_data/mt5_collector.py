"""
Phase 1.4 — MetaTrader5 Polling Collector (Windows VPS).

Poll MT5 terminal mỗi MT5_POLL_INTERVAL giây để lấy closed candle.
Thay thế IBKR WebSocket collector.

MT5 không có WebSocket nên dùng polling:
  bar[0] = candle đang mở
  bar[1] = candle vừa đóng  ← dùng cái này
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from utils.logger import logger
from utils.telegram import telegram
from config.settings import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH,
    MT5_DEMO_MODE, MT5_SYMBOL_MAP, MT5_TF_MAP,
    MT5_POLL_INTERVAL, WS_RECONNECT_DELAY,
    STALE_CLOSED_BAR_THRESHOLD, BROKER_TZ_OFFSET,
)
from phase1_data.validator import validate_candle


def _get_tf_const(timeframe: str):
    """Trả về hằng số TIMEFRAME_* từ MetaTrader5."""
    import MetaTrader5 as mt5
    tf_name = MT5_TF_MAP.get(timeframe)
    if not tf_name:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return getattr(mt5, tf_name)


def _init_mt5() -> bool:
    """Khởi tạo / reconnect MT5 terminal."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise ImportError(
            "MetaTrader5 not installed. On Windows run:\n"
            "  pip install MetaTrader5\n"
            "On Mac/Linux → use yfinance (DATA_SOURCE=YFINANCE)."
        )
    kwargs = {}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH
    if not mt5.initialize(**kwargs):
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return False
    if MT5_LOGIN:
        ok = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
        if not ok:
            logger.error(f"MT5 login failed: {mt5.last_error()}")
            mt5.shutdown()
            return False
    info = mt5.account_info()
    if info:
        mode = "DEMO" if MT5_DEMO_MODE else "LIVE"
        logger.info(f"MT5 connected [{mode}] balance={info.balance} {info.currency}")
    return True


class MT5StreamingCollector:
    """Poll MT5 terminal cho closed candles. Windows-only."""

    def __init__(self, symbols: List[str], timeframes: List[str], db,
                 on_candle: Optional[Callable] = None):
        self.symbols    = symbols
        self.timeframes = timeframes
        self.db         = db
        self.on_candle  = on_candle
        self._running   = False
        self._last_bar_time: Dict[str, Optional[datetime]] = {}
        self._last_seen:     Dict[str, float]              = {}

        for sym in symbols:
            for tf in timeframes:
                key = f"{sym}_{tf}"
                self._last_bar_time[key] = None
                self._last_seen[key]     = time.time()

    def _poll_once(self) -> List[dict]:
        """Đọc bar[-1] (last closed) cho tất cả symbol/tf. Return list candles mới."""
        import MetaTrader5 as mt5
        new_candles = []
        for symbol in self.symbols:
            mt5_sym = MT5_SYMBOL_MAP.get(symbol, symbol)
            for tf in self.timeframes:
                key = f"{symbol}_{tf}"
                try:
                    tf_const = _get_tf_const(tf)
                    # 0,2 → lấy 2 bar kể từ vị trí 0 (bar hiện tại)
                    # rates[0] = bar đang mở, rates[1] = bar vừa đóng
                    rates = mt5.copy_rates_from_pos(mt5_sym, tf_const, 0, 2)
                except Exception as e:
                    logger.debug(f"MT5 copy_rates error {symbol} {tf}: {e}")
                    continue

                if rates is None or len(rates) < 2:
                    continue

                closed = rates[1]   # bar[1] = last fully closed bar
                # MT5 trả về time theo broker server local (ICMarkets = UTC+3)
                # Phải trừ offset để convert về UTC thật
                open_time = datetime.fromtimestamp(
                    int(closed["time"]) - BROKER_TZ_OFFSET * 3600,
                    tz=timezone.utc
                )

                last = self._last_bar_time.get(key)
                if last is not None and open_time <= last:
                    # Stale detection
                    age = time.time() - self._last_seen[key]
                    if age > STALE_CLOSED_BAR_THRESHOLD:
                        logger.warning(
                            f"[{symbol} {tf}] Stale {age:.0f}s — reconnecting MT5"
                        )
                        _init_mt5()
                        self._last_seen[key] = time.time()
                        # Fire-and-forget Telegram (sync context)
                        import asyncio as _asyncio
                        try:
                            loop = _asyncio.get_event_loop()
                            if loop.is_running():
                                _asyncio.ensure_future(telegram.send(
                                    f"⚠️ MT5 Stale {age:.0f}s — reconnecting\n[{symbol} {tf}]"
                                ))
                        except Exception:
                            pass
                    continue

                self._last_bar_time[key] = open_time
                self._last_seen[key]     = time.time()
                candle = {
                    "symbol":    symbol,
                    "timeframe": tf,
                    "open_time": open_time,
                    "open":      float(closed["open"]),
                    "high":      float(closed["high"]),
                    "low":       float(closed["low"]),
                    "close":     float(closed["close"]),
                    "volume":    int(closed["tick_volume"]) if "tick_volume" in closed.dtype.names else 0,
                }
                new_candles.append(candle)
        return new_candles

    async def start(self):
        loop = asyncio.get_event_loop()

        # Connect MT5
        ok = await loop.run_in_executor(None, _init_mt5)
        if not ok:
            logger.error("MT5 init failed — collector aborted")
            await telegram.send("🔴 MT5 init FAILED — collector aborted. Check MT5 Terminal!")
            return

        logger.info(
            f"MT5StreamingCollector started "
            f"(poll {MT5_POLL_INTERVAL:.0f}s | "
            f"symbols={self.symbols} | tf={self.timeframes})"
        )
        await telegram.send(
            f"📡 MT5 Collector started\n"
            f"Symbols: {', '.join(self.symbols)}\n"
            f"Timeframes: {', '.join(self.timeframes)}"
        )

        self._running = True
        while self._running:
            try:
                new_candles = await loop.run_in_executor(None, self._poll_once)
                for candle in new_candles:
                    if not validate_candle(candle):
                        continue
                    if self.db:
                        try:
                            await self.db.upsert_candle(candle["symbol"], candle["timeframe"], candle)
                        except Exception as e:
                            logger.error(f"DB upsert error: {e}")
                    if self.on_candle:
                        try:
                            await self.on_candle(candle)
                        except Exception as e:
                            logger.error(f"on_candle callback error: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"MT5 poll loop error: {e}", exc_info=True)
                await telegram.send(f"🔴 MT5 poll error: {e}\nReconnecting in {WS_RECONNECT_DELAY}s...")
                await asyncio.sleep(WS_RECONNECT_DELAY)
                await loop.run_in_executor(None, _init_mt5)

            await asyncio.sleep(MT5_POLL_INTERVAL)

    def stop(self):
        self._running = False
        try:
            import MetaTrader5 as mt5
            mt5.shutdown()
        except Exception:
            pass
        logger.info("MT5StreamingCollector stopped")
