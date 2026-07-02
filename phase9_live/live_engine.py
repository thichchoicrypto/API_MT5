"""
Phase 9 — Live Trading Engine.
Orchestrates live market data → strategy → execution → monitoring.
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from utils.logger import logger
from utils.telegram import telegram
from config.settings import (
    SYMBOLS, TIMEFRAMES, ENTRY_TIMEFRAME, STRUCTURE_TIMEFRAME,
    BIAS_TIMEFRAME, MAX_OPEN_POSITIONS, MAX_LEVERAGE, RISK_PER_TRADE,
    LIMIT_ORDER_TIMEOUT_CANDLES,
)
from phase2_structure.structure_engine import StructureEngine
from phase2_structure.mtf_bias import MTFBias
from phase3_liquidity.liquidity_engine import build_liquidity_zones
from phase3_liquidity.sweep_detector import detect_sweep
from phase3_liquidity.choch_detector import detect_choch, StructureShiftTracker
from phase4_fvg_ob.fvg_engine import detect_fvg, update_fvg_fills, _calc_atr
from phase4_fvg_ob.orderblock_engine import detect_all_obs, update_ob_mitigation
from phase4_fvg_ob.zone_builder import find_confluence_zones, build_entry_zone
from phase5_entry.entry_engine import EntryEngine
from phase6_risk.risk_engine import RiskEngine
from phase9_live.mt5_order_manager import MT5OrderManager, BOT_MAGIC
from phase9_live.kill_switch import KillSwitch
from phase9_live.position_monitor import LivePositionMonitor


class LiveTradingEngine:
    """
    Phase 9.18 Full Pipeline:
    Market Data → Structure → Liquidity → FVG/OB → Entry → Risk → Execution → Exchange
    """

    def __init__(self):
        self.order_manager = MT5OrderManager()
        self.kill_switch = KillSwitch(self.order_manager)
        self.position_monitor = LivePositionMonitor(self.order_manager)
        self.risk_engine = RiskEngine()

        # Per-symbol engines
        self._structures: Dict[str, StructureEngine] = {}
        self._entries: Dict[str, EntryEngine] = {}
        self._shift_trackers: Dict[str, StructureShiftTracker] = {}

        # Separate 1h structure engine per symbol cho MTF bias.
        # Tại sao không dùng MTFBias object (phase2_structure/mtf_bias.py)?
        #   MTFBias.update(tf, trend) cần gọi với đúng TF để work.
        #   Với ENTRY_TIMEFRAME=15m: on_candle callback chỉ nhận 15m candle vào _process_signal.
        #   1h update chỉ xảy ra khi 1h candle đóng (trong on_candle, tf==BIAS_TIMEFRAME branch).
        #   Bug 18: nếu dùng MTFBias object, bias không được update đúng timing → NEUTRAL mãi.
        #   Fix: dùng _struct_1h_output riêng, update khi nhận 1h candle, đọc khi process 15m signal.
        self._struct_1h: Dict[str, StructureEngine] = {}
        self._struct_1h_output: Dict[str, Dict] = {}

        # Candle buffers
        self._candle_buffers: Dict[str, List[dict]] = {}
        self._fvgs: Dict[str, List[dict]] = {}
        self._obs: Dict[str, List[dict]] = {}

        self._running = False
        self._api_errors = 0

        # CHG-FX-027: LIMIT entry chưa fill tại thời điểm đặt lệnh (sau 2s check
        # trong _execute_signal) được theo dõi ở đây — _check_pending_limit_orders
        # (chạy mỗi 60s trong _monitoring_loop) sẽ poll lại và đặt SL/TP khi fill.
        # Lưu ý: dict này CHỈ ở memory — nếu bot restart khi đang có LIMIT order
        # pending, entry đó sẽ "mồ côi" (không bị track lại). Acceptable edge-case
        # hiện tại, có thể cải thiện sau bằng cách lưu vào DB.
        self._pending_limit_orders: Dict[str, Dict] = {}

        # Guard chống race condition: symbol đang trong quá trình đặt lệnh
        # (giữa lúc place_order và khi _pending_limit_orders được cập nhật)
        self._placing_orders: set = set()

        # TTL memory cho sweep/choch — persist N candles sau khi detect (như backtest)
        self._last_sweep: Dict[str, Optional[Dict]] = {}
        self._last_choch: Dict[str, Optional[Dict]] = {}
        self._sweep_ttl:  Dict[str, int] = {}
        self._choch_ttl:  Dict[str, int] = {}
        self._EVENT_TTL = 20   # giữ sweep/choch 20 candles

        for symbol in SYMBOLS:
            self._structures[symbol] = StructureEngine(symbol, ENTRY_TIMEFRAME)
            self._struct_1h[symbol]  = StructureEngine(symbol, "1h")
            self._struct_1h_output[symbol] = {}
            self._entries[symbol] = EntryEngine(symbol, ENTRY_TIMEFRAME)
            self._shift_trackers[symbol] = StructureShiftTracker()
            self._candle_buffers[symbol] = []
            self._fvgs[symbol] = []
            self._obs[symbol] = []
            self._last_sweep[symbol] = None
            self._last_choch[symbol] = None
            self._sweep_ttl[symbol]  = 0
            self._choch_ttl[symbol]  = 0

    async def start(self, db):
        """Main entry point — sets up leverage and starts data collection."""
        self._db = db
        # MT5: không cần set_position_mode hay set_leverage (cấu hình trong MT5 terminal)
        # Load account balance — phải update cả peak_balance và _day_start_balance
        # để tránh false drawdown (default 10,000 vs actual balance)
        balance = await self.order_manager.get_account_balance()
        if balance:
            self.risk_engine.account_balance = balance
            self.risk_engine.peak_balance = balance
            self.risk_engine._day_start_balance = balance
            logger.info(f"Account balance: ${balance:.2f}")

        await telegram.send(f"🚀 MT5 Live Trading Started | Balance: ${balance:.2f}" if balance else "🚀 MT5 Live Trading Started")

        self._running = True

        # Preload candles từ DB để strategy hoạt động ngay lập tức
        # Không cần đợi 50+ giờ tích lũy candle qua polling
        logger.info("Preloading candles from DB ...")
        for symbol in SYMBOLS:
                for tf in TIMEFRAMES:
                    candles = await db.get_candles(symbol, tf, limit=500)
                    if candles:
                        key = f"{symbol}_{tf}"
                        self._candle_buffers[key] = candles
                        logger.info(f"Preloaded {len(candles)} candles: {symbol} {tf}")
        logger.info("Candle preload complete — strategy ready immediately")

        # Gap-fill: dùng BackfillService để detect và fill ALL missing candles
        # lookback_hours = thực tế bot down bao lâu + buffer đủ cho các layer
        # Structure engine cần 200 candles × 15m = 50h → lookback tối thiểu 50h
        # Tính từ latest candle trong DB đến hiện tại để biết downtime thực tế
        from phase1_data.backfill import BackfillService
        from config.settings import DATA_SOURCE
        from datetime import timezone as _tz
        if DATA_SOURCE == "MT5":
                from phase1_data.mt5_downloader import MT5Downloader as _DL
        else:
                from phase1_data.yfinance_downloader import YFinanceDownloader as _DL

        _now = datetime.now(tz=_tz.utc)
        _min_lookback = 50   # đủ cho structure engine (200 candles × 15m = 50h)
        _max_lookback = 168  # tối đa 7 ngày (tránh quá nhiều REST calls)

        # Tìm candle cũ nhất trong buffer để tính downtime
        _oldest_buf_time = None
        for symbol in SYMBOLS:
                buf = self._candle_buffers.get(f"{symbol}_{ENTRY_TIMEFRAME}", [])
                if buf:
                    t = buf[-1]["open_time"]
                    t = t.replace(tzinfo=_tz.utc) if t.tzinfo is None else t
                    if _oldest_buf_time is None or t < _oldest_buf_time:
                        _oldest_buf_time = t

        if _oldest_buf_time:
                _downtime_hours = (_now - _oldest_buf_time).total_seconds() / 3600
                _lookback = min(max(_downtime_hours + _min_lookback, _min_lookback), _max_lookback)
        else:
                _lookback = _min_lookback

        logger.info(f"Gap-filling missed candles (lookback={_lookback:.0f}h) ...")
        _dl = _DL()
        _dl.connect()
        bf = BackfillService(db, _dl)
        await bf.run_all(lookback_hours=int(_lookback))

        # Reload buffer từ DB sau khi backfill
        for symbol in SYMBOLS:
                for tf in TIMEFRAMES:
                    candles = await db.get_candles(symbol, tf, limit=500)
                    if candles:
                        self._candle_buffers[f"{symbol}_{tf}"] = candles
        logger.info("Gap-fill complete — buffers reloaded")

        # Warmup engines: replay preloaded candles để build BOS/sweep/CHoCH state
        # ── TẠI SAO CẦN WARMUP? ──────────────────────────────────────────────
        # Khi bot restart, _bos_events=[], _last_sweep=None, _last_choch=None.
        # Nếu không warmup → candle đầu tiên nhận qua WebSocket:
        #   L3 (liquidity) → không có sweep/CHoCH → FAIL → không vào lệnh.
        #   _bos_events=[] → không detect OB nào → Phase 4 trả về None.
        # Warmup = replay toàn bộ 500 candles preloaded để tái dựng state
        # như thể bot chưa bao giờ restart.
        # ─────────────────────────────────────────────────────────────────────
        logger.info("Warming up strategy engines ...")

        # Bug fix: warmup 1h structure engine để có MTF bias ngay từ đầu
        for symbol in SYMBOLS:
                buf_1h = self._candle_buffers.get(f"{symbol}_1h", [])
                if buf_1h:
                    self._struct_1h_output[symbol] = self._struct_1h[symbol].update(
                        buf_1h[-201:], silent=True)
                    logger.info(f"[{symbol}] 1h bias warmed up: "
                                f"trend={self._struct_1h_output[symbol].get('trend', 'RANGE')}")

        for symbol in SYMBOLS:
                key = f"{symbol}_{ENTRY_TIMEFRAME}"
                buf = self._candle_buffers.get(key, [])
                if len(buf) < 10:
                    continue
                struct_engine = self._structures[symbol]
                # Replay từng candle theo thứ tự để build up BOS events + sweep/choch TTL
                # Bug fix: cap window tại 201 candles để match backtest window size
                for i in range(5, len(buf)):
                    slice_c = buf[max(0, i - 200):i + 1]   # max 201 candles
                    struct = struct_engine.update(slice_c, silent=True)
                    candle_i = slice_c[-1]
                    new_sweep = detect_sweep(candle_i,
                                             struct.get("last_swing_high"),
                                             struct.get("last_swing_low"))
                    last_bos_i = struct["bos_events"][-1] if struct.get("bos_events") else None
                    new_choch = detect_choch(struct.get("trend", "RANGE"), last_bos_i)
                    # Update TTL memory (same logic as _process_signal)
                    if new_sweep:
                        self._last_sweep[symbol] = new_sweep
                        self._sweep_ttl[symbol]  = self._EVENT_TTL
                    elif self._sweep_ttl[symbol] > 0:
                        self._sweep_ttl[symbol] -= 1
                    else:
                        self._last_sweep[symbol] = None
                    if new_choch:
                        self._last_choch[symbol] = new_choch
                        self._choch_ttl[symbol]  = self._EVENT_TTL
                    elif self._choch_ttl[symbol] > 0:
                        self._choch_ttl[symbol] -= 1
                    else:
                        self._last_choch[symbol] = None
                bos_count = len(struct_engine._bos_events)
                logger.info(
                    f"[{symbol}] Warmup done: bos_events={bos_count}, "
                    f"sweep={self._last_sweep[symbol]['type'] if self._last_sweep[symbol] else None}, "
                    f"choch={self._last_choch[symbol]['type'] if self._last_choch[symbol] else None}"
                )
        logger.info("Engine warmup complete — L3 ready immediately after restart")

        # Restore open positions từ DB sau khi restart
        # Tránh mất track lệnh đang mở khi bot restart giữa chừng
        open_trades = await db.get_open_live_trades()
        if open_trades:
                logger.info(f"Restoring {len(open_trades)} open position(s) from DB ...")
                for row in open_trades:
                    from phase9_live.position_monitor import LivePosition
                    pos = LivePosition.restore_from_db(row)
                    if pos:
                        self.position_monitor.restore(pos)
                logger.info(f"Restored {len(self.position_monitor.open_positions)} position(s)")
        else:
                logger.info("No open positions to restore")

        # Setup polling collector (MT5 on Windows / yfinance on Mac)
        from config.settings import DATA_SOURCE as _DS
        if _DS == "MT5":
                from phase1_data.mt5_collector import MT5StreamingCollector as _Collector
        else:
                from phase1_data.yfinance_collector import YFinanceStreamingCollector as _Collector
        collector = _Collector(SYMBOLS, TIMEFRAMES, db, on_candle=self.on_candle)

        # Run collector + monitor concurrently
        await asyncio.gather(
                collector.start(),
                self._monitoring_loop(),
        )

    async def on_candle(self, candle: dict):
        """Called for every closed candle from WebSocket."""
        symbol = candle["symbol"]
        tf = candle["timeframe"]

        # Buffer candles
        key = f"{symbol}_{tf}"
        if key not in self._candle_buffers:
            self._candle_buffers[key] = []

        # Gap detection: nếu candle mới không liền sau candle trước → WS bị miss
        # Trigger backfill ngay thay vì chờ đến lần restart
        buf = self._candle_buffers[key]
        if buf:
            from phase1_data.validator import tf_to_seconds
            step = tf_to_seconds(tf)
            last_time = buf[-1]["open_time"]
            curr_time = candle["open_time"]
            gap_s = (curr_time - last_time).total_seconds()
            if gap_s > step * 1.5:
                missed = int(gap_s / step) - 1
                logger.warning(f"[{symbol} {tf}] Gap detected: {missed} candle(s) missing "
                               f"({last_time} → {curr_time}) — triggering backfill")
                asyncio.create_task(self._backfill_gap(symbol, tf, gap_s))

        self._candle_buffers[key].append(candle)
        if len(self._candle_buffers[key]) > 500:
            self._candle_buffers[key] = self._candle_buffers[key][-500:]

        candles = self._candle_buffers[key]

        # Only trade on ENTRY_TIMEFRAME
        if tf != ENTRY_TIMEFRAME:
            # Bug fix: update 1h structure engine riêng (match backtest _get_mtf_bias logic)
            if tf == BIAS_TIMEFRAME and symbol in self._struct_1h:
                buf_1h = self._candle_buffers.get(f"{symbol}_{tf}", [])
                if buf_1h:
                    self._struct_1h_output[symbol] = self._struct_1h[symbol].update(
                        buf_1h[-201:], silent=True)
            return

        await self._process_signal(symbol, candles)

    async def _backfill_gap(self, symbol: str, tf: str, gap_seconds: float):
        """Backfill missing candles khi polling bị lỡ candle."""
        try:
            from phase1_data.backfill import BackfillService
            from config.settings import DATA_SOURCE as _DS
            if _DS == "MT5":
                from phase1_data.mt5_downloader import MT5Downloader as _DL
            else:
                from phase1_data.yfinance_downloader import YFinanceDownloader as _DL
            lookback = max(int(gap_seconds / 3600) + 2, 2)
            _dl = _DL(); _dl.connect()
            bf  = BackfillService(self._db, _dl)
            await bf.check_and_fill(symbol, tf, lookback_hours=lookback)
            # Reload buffer sau khi fill
            candles = await self._db.get_candles(symbol, tf, limit=500)
            if candles:
                self._candle_buffers[f"{symbol}_{tf}"] = candles
            logger.info(f"[{symbol} {tf}] Gap backfill complete")
        except Exception as e:
            logger.error(f"[{symbol} {tf}] Gap backfill error: {e}")

    async def _process_signal(self, symbol: str, candles: List[dict]):
        """Core strategy pipeline per candle."""
        if not self.kill_switch.trading_allowed:
            return

        try:
            # Phase 2: Structure — Bug fix: max 201 candles, match backtest window size
            struct = self._structures[symbol].update(candles[-201:])

            # Phase 3: Liquidity
            liq_zones = build_liquidity_zones(
                [s for s in struct.get("structure", []) if s.get("type") in ("swing_high", "HH", "LH")],
                [s for s in struct.get("structure", []) if s.get("type") in ("swing_low", "HL", "LL")],
            )
            last_bos  = struct["bos_events"][-1] if struct.get("bos_events") else None
            new_sweep = detect_sweep(candles[-1], struct.get("last_swing_high"), struct.get("last_swing_low"))
            new_choch = detect_choch(struct.get("trend", "RANGE"), last_bos)
            shift     = self._shift_trackers[symbol].process(new_choch, last_bos, candles[-1]["close"])

            # TTL memory — giữ sweep/choch 20 candles sau khi detect (matches backtest)
            if new_sweep:
                self._last_sweep[symbol] = new_sweep
                self._sweep_ttl[symbol]  = self._EVENT_TTL
            elif self._sweep_ttl[symbol] > 0:
                self._sweep_ttl[symbol] -= 1
            else:
                self._last_sweep[symbol] = None

            if new_choch:
                self._last_choch[symbol] = new_choch
                self._choch_ttl[symbol]  = self._EVENT_TTL
            elif self._choch_ttl[symbol] > 0:
                self._choch_ttl[symbol] -= 1
            else:
                self._last_choch[symbol] = None

            # MTF bias: match backtest _get_mtf_bias() logic
            # Priority: 1h trend → entry TF trend → NEUTRAL
            # Lý do: 1h là "higher timeframe bias" — quyết định chiều LONG hay SHORT.
            # 15m chỉ là "entry timeframe" — tìm điểm vào trong chiều của 1h.
            # Nếu 1h RANGE → dùng 15m trend. Nếu cả hai RANGE → NEUTRAL → không trade.
            _trend = struct.get("trend", "RANGE")
            h1_trend = self._struct_1h_output.get(symbol, {}).get("trend", "RANGE")
            if h1_trend in ("UP", "UPTREND"):
                _mtf_bias = "LONG"
            elif h1_trend in ("DOWN", "DOWNTREND"):
                _mtf_bias = "SHORT"
            else:
                _mtf_bias = ("LONG" if _trend in ("UP", "UPTREND")
                             else "SHORT" if _trend in ("DOWN", "DOWNTREND")
                             else "NEUTRAL")

            liq_output = {
                "liq_zones": liq_zones,
                "last_sweep": self._last_sweep[symbol],
                "last_choch": self._last_choch[symbol],
                "structure_shift": shift,
                "mtf_bias": _mtf_bias,
            }

            # Phase 4: FVG + OB (pass symbol for per-symbol ATR ratio / OB lookback)
            self._fvgs[symbol] = detect_fvg(candles[-30:], symbol=symbol)
            self._fvgs[symbol] = update_fvg_fills(self._fvgs[symbol], candles[-1])
            self._obs[symbol] = detect_all_obs(candles[-50:], struct.get("bos_events", []), symbol=symbol)
            self._obs[symbol] = update_ob_mitigation(self._obs[symbol], candles[-1])
            confluence = find_confluence_zones(self._fvgs[symbol], self._obs[symbol])

            # Phase 5 + 6 + Execution
            # CHG-FX-027: tính cả LIMIT order đang pending (chưa fill) vào tổng số
            # "vị thế đang chiếm slot" — tránh đặt thêm signal mới khi đã đủ.
            _active = len(self.position_monitor.open_positions) + len(self._pending_limit_orders)
            if _active >= MAX_OPEN_POSITIONS:
                return

            for side in ("LONG", "SHORT"):

                current = candles[-1]
                last_bos_event = struct["bos_events"][-1] if struct.get("bos_events") else None

                # Base tracker record
                tracker = {
                    "symbol":          symbol,
                    "timeframe":       ENTRY_TIMEFRAME,
                    "candle_time":     current["open_time"],
                    "side":            side,
                    "trend":           struct.get("trend"),
                    "last_swing_high": struct.get("last_swing_high"),
                    "last_swing_low":  struct.get("last_swing_low"),
                    "bos_type":        last_bos_event["type"] if last_bos_event else None,
                    "sweep_type":      self._last_sweep[symbol]["type"] if self._last_sweep[symbol] else None,
                    "choch_type":      self._last_choch[symbol]["type"] if self._last_choch[symbol] else None,
                    "mtf_bias":        liq_output.get("mtf_bias"),
                }

                current_price = current["close"]
                atr = _calc_atr(candles)
                entry_zone = build_entry_zone(side, self._fvgs[symbol], self._obs[symbol], confluence,
                                              current_price=current_price, atr=atr)
                if not entry_zone:
                    tracker["stop_reason"] = "no_zone"
                    await self._save_tracker(tracker)
                    continue

                tracker.update({
                    "zone_type": entry_zone["source"],
                    "zone_low":  entry_zone["low"],
                    "zone_high": entry_zone["high"],
                })

                risk_out = self.risk_engine.evaluate(side, symbol, entry_zone["midpoint"], candles, struct, liq_zones)
                if not risk_out:
                    tracker["stop_reason"] = "risk_rejected"
                    tracker["l6_risk"] = False
                    await self._save_tracker(tracker)
                    continue

                tracker.update({
                    "l6_risk": True,
                    "sl":      risk_out.get("sl"),
                    "tp1":     risk_out["tp"][0]["level"] if risk_out.get("tp") else None,
                    "rr":      risk_out.get("rr"),
                })

                signal = self._entries[symbol].evaluate(candles, struct, liq_output, entry_zone, risk_out)

                dbg = self._entries[symbol].last_eval_debug
                tracker.update({
                    "l1_trend":      dbg.get("l1_trend"),
                    "l2_zone_touch": dbg.get("l2_zone_touch"),
                    "l3_liquidity":  dbg.get("l3_liquidity"),
                    "l4_volume":     dbg.get("l4_volume"),
                    "l5_trigger":    dbg.get("l5_trigger"),
                    "stop_reason":   dbg.get("stop_reason"),
                    "eligible": bool(
                        dbg.get("l1_trend") and dbg.get("l2_zone_touch") and
                        dbg.get("l3_liquidity") and dbg.get("l4_volume") and
                        dbg.get("l5_trigger") and risk_out
                    ),
                })

                if signal:
                    signal["candle_time"] = current["open_time"]  # để link với tracker row khi đóng lệnh
                    tracker.update({
                        "signal_side":  side,
                        "order_placed": True,
                        "order_type":   signal.get("entry_type", "MARKET"),
                        "entry_price":  signal.get("entry_price"),
                        "stop_reason":  None,
                        "eligible":     True,
                    })
                    await self._save_tracker(tracker)
                    await self._execute_signal(signal, risk_out)
                    break
                else:
                    await self._save_tracker(tracker)

        except Exception as e:
            self._api_errors += 1
            logger.error(f"[{symbol}] Strategy error: {e}", exc_info=True)
            if self._api_errors >= 10:
                await self.kill_switch.enter_safe_mode(f"Too many strategy errors: {e}")

    async def _save_tracker(self, record: dict):
        """Save candle tracker record to candle_tracker_live."""
        try:
            if hasattr(self, "_db") and self._db:
                await self._db.save_candle_tracker(record, table="candle_tracker_live")
        except Exception as e:
            logger.debug(f"[tracker] save error: {e}")

    async def _execute_signal(self, signal: Dict, risk: Dict):
        """Phase 9.3: Execute live order."""
        symbol   = signal["symbol"]
        side_api = "BUY" if signal["side"] == "LONG" else "SELL"

        # Guard: nếu đang đặt lệnh cho symbol này (race condition giữa place_order
        # và asyncio.sleep(2) trước khi _pending_limit_orders được cập nhật) → skip
        if symbol in self._placing_orders or symbol in self._pending_limit_orders:
            logger.warning(f"[{symbol}] Duplicate signal ignored — already placing/pending")
            return
        self._placing_orders.add(symbol)

        try:
            # risk_engine trả về units (OANDA-compatible) → convert sang MT5 lots
            # FX pairs:  1 lot = 100,000 units (EURUSD, GBPUSD, AUDUSD, USDCHF…)
            # XAUUSD:    1 lot = 100 oz  → chia 100
            # XAGUSD:    1 lot = 5000 oz → chia 5000
            _MT5_CONTRACT = {"XAUUSD": 100, "XAGUSD": 5_000}
            qty_units = risk["position_size"]
            qty       = max(0.01, round(qty_units / _MT5_CONTRACT.get(symbol, 100_000), 2))

            tp_level = risk["tp"][0]["level"] if risk.get("tp") else 0.0

            logger.info(
                f"[LIVE] Executing {signal['side']} {symbol} "
                f"{qty:.2f}L (={qty_units:.0f} units) @ {signal['entry_price']:.5f}"
            )

            is_market = signal.get("entry_type") == "MARKET"

            if is_market:
                # MARKET: SL/TP nhúng thẳng vào order request MT5
                ticket = await self.order_manager.place_order(
                    symbol    = symbol,
                    side      = side_api,
                    volume    = qty,
                    sl        = risk["sl"],
                    tp        = tp_level,
                    order_type= "MARKET",
                )
            else:
                # LIMIT: SL/TP nhúng vào LIMIT order MT5 ngay từ đầu
                # (MT5 hỗ trợ SL/TP embedded trong pending order)
                ticket = await self.order_manager.place_order(
                    symbol     = symbol,
                    side       = side_api,
                    volume     = qty,
                    price      = signal["entry_price"],
                    sl         = risk["sl"],
                    tp         = tp_level,
                    order_type = "LIMIT",
                )

            if not ticket:
                self._api_errors += 1
                logger.error(f"Order failed for {symbol}")
                return

            order_id = str(ticket)

            if is_market:
                # MARKET fill ngay — lấy actual fill price từ MT5 để track đúng entry
                self._placing_orders.discard(symbol)
                mt5_pos = await self.order_manager.get_position(symbol)
                if mt5_pos and mt5_pos.get("entry"):
                    signal = dict(signal)  # copy để không mutate original
                    signal["entry_price"] = mt5_pos["entry"]
                await self._finalize_entry(symbol, order_id, signal, risk, tp_level)
                return

            # LIMIT entry: check fill sau 2s bằng cách xem ticket còn trong pending không
            await asyncio.sleep(2)
            pending = await self.order_manager.get_pending_orders(symbol)
            still_pending = any(str(o["ticket"]) == order_id for o in pending)
            pos = await self.order_manager.get_position(symbol)
            filled = (not still_pending) and (pos is not None)

            self._placing_orders.discard(symbol)  # release guard sau sleep

            if filled:
                # SL/TP đã nhúng trong LIMIT order → không cần đặt lại
                await self._finalize_entry(symbol, order_id, signal, risk, tp_level)
            else:
                # Chưa fill — theo dõi trong _monitoring_loop
                logger.info(f"[LIVE] LIMIT order #{order_id} ({symbol}) chưa fill → theo dõi")
                self._pending_limit_orders[symbol] = {
                    "order_id":  order_id,
                    "ticket":    int(ticket),
                    "signal":    signal,
                    "risk":      risk,
                    "qty":       qty,
                    "tp_level":  tp_level,
                    "placed_at": datetime.now(tz=timezone.utc),
                }
                await telegram.send(
                    f"⏳ [LIVE] LIMIT pending {signal['side']} {symbol}\n"
                    f"  Entry : {signal['entry_price']:.5f}\n"
                    f"  SL    : {risk['sl']:.5f}\n"
                    f"  TP    : {tp_level:.5f}\n"
                    f"  Lots  : {qty:.2f}L  RR={risk['rr']:.1f}R\n"
                    f"  TTL   : {LIMIT_ORDER_TIMEOUT_CANDLES} nến {ENTRY_TIMEFRAME}"
                )
        except Exception:
            logger.exception(f"[{symbol}] Exception in _execute_signal")
        finally:
            # Đảm bảo guard luôn được giải phóng, kể cả khi có exception
            self._placing_orders.discard(symbol)

    async def _place_sl_tp_for_limit(self, symbol: str, signal: Dict, risk: Dict,
                                      qty: float, tp_level: float):
        """MT5: SL/TP đã nhúng trong LIMIT order ban đầu → không cần đặt thêm."""
        # Không cần làm gì — MT5 tự giữ SL/TP khi LIMIT chuyển thành position
        pass

    async def _finalize_entry(self, symbol: str, order_id: str, signal: Dict,
                               risk: Dict, tp_level: float):
        """Bookkeeping sau khi entry CONFIRMED FILLED (MARKET fill ngay, hoặc
        LIMIT fill trong 2s đầu / fill trễ qua _check_pending_limit_orders):
        Telegram + lưu DB + track vào position_monitor.
        Tách riêng (CHG-FX-027) để dùng chung cho cả 3 đường trên — trước đây
        bị gọi NGAY CẢ KHI LIMIT order chưa fill, khiến position_monitor +
        _check_closed_positions coi 1 LIMIT order chưa fill là "position đã
        bị đóng" (vì get_position() trả về None) -> false "CLOSED" event."""
        msg = (f"📊 [LIVE] {signal['side']} {symbol} | "
               f"Entry={signal['entry_price']:.2f} SL={risk['sl']:.2f} "
               f"TP={tp_level:.2f} RR={risk['rr']:.1f}")
        logger.info(msg)
        await telegram.send(msg)
        self._api_errors = 0

        if hasattr(self, "_db") and self._db:
            await self._db.save_live_trade_open(
                order_id=order_id,
                symbol=symbol,
                side=signal["side"],
                entry_price=signal["entry_price"],
                sl=risk["sl"],
                tp=tp_level,
                size=risk["position_size"],
                balance=self.risk_engine.account_balance,
            )

        self.position_monitor.track({"orderId": order_id}, signal, risk)

    async def _monitoring_loop(self):
        """Phase 9.13: Periodic system monitoring + position close detection."""
        _last_day = None
        _balance_none_count = 0  # đếm số lần liên tiếp balance=None
        while self._running:
            await asyncio.sleep(60)
            try:
                balance = await self.order_manager.get_account_balance()
                if balance:
                    self.risk_engine.account_balance = balance
                    if _balance_none_count > 0:
                        # Reconnected — notify recovery
                        await telegram.send(f"✅ MT5 reconnected — balance=${balance:.2f}")
                    _balance_none_count = 0
                else:
                    _balance_none_count += 1
                    logger.warning(f"[Monitor] balance=None (count={_balance_none_count})")
                    if _balance_none_count == 3:  # alert sau 3 phút liên tiếp
                        await telegram.send(
                            "⚠️ MT5 API mất kết nối — đang thử reconnect..."
                        )
                        logger.warning("[Monitor] Attempting MT5 reconnect ...")
                        ok = await self.order_manager.reconnect()
                        if ok:
                            logger.info("[Monitor] MT5 reconnect SUCCESS")
                            # balance sẽ được lấy lại ở vòng lặp tiếp theo
                        else:
                            logger.error("[Monitor] MT5 reconnect FAILED")
                            await telegram.send(
                                "🔴 MT5 reconnect thất bại!\n"
                                "Bot KHÔNG THỂ đặt lệnh. Cần restart thủ công."
                            )

                # Bug fix: reset daily limits mỗi ngày UTC mới (match backtest)
                today = datetime.now(tz=timezone.utc).date()
                if _last_day is None or today != _last_day:
                    self.risk_engine.reset_daily()
                    self.kill_switch.reset()   # auto-reset kill switch mỗi ngày mới
                    _last_day = today
                    logger.info(f"[Monitor] Daily limits reset for {today}")

                # CHG-FX-027: poll các LIMIT entry chưa fill -> đặt SL/TP khi fill
                await self._check_pending_limit_orders()

                # CHG-FX-031: breakeven — dời SL về entry khi đạt 1R profit
                await self._check_breakeven_live()
                # Trailing stop: disabled — chỉ dùng BE

                # Check if any tracked positions have been closed by OANDA (TP/SL hit)
                await self._check_closed_positions(balance)

                open_pos = len(self.position_monitor.open_positions)
                dd = self.risk_engine.daily_pnl / self.risk_engine.account_balance if self.risk_engine.account_balance else 0

                status = {
                    "balance": balance,
                    "open_positions": open_pos,
                    "daily_pnl_pct": dd,
                    "api_errors": self._api_errors,
                }
                logger.info(f"[Monitor] {status}")

                await self.kill_switch.check(
                    daily_pnl_pct=dd,
                    drawdown=(self.risk_engine.peak_balance - self.risk_engine.account_balance) / self.risk_engine.peak_balance,
                    ws_connected=True,
                    data_delayed=False,
                    api_errors=self._api_errors,
                )
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")

    async def _check_breakeven_live(self):
        """
        CHG-FX-031: Dời SL về entry (breakeven) khi position đạt 1R profit.

        Logic:
          - LONG : current_price >= entry + sl_dist → SL → entry
          - SHORT: current_price <= entry - sl_dist → SL → entry
          - Chỉ chạy 1 lần / position (be_set flag)
          - Gọi modify_trade_sl() để update stop order trên IBKR
          - Gửi Telegram khi dời SL
        """
        if not self.position_monitor.open_positions:
            return

        for symbol, pos in list(self.position_monitor.open_positions.items()):
            try:
                if pos.be_set:
                    continue

                current_price = await self.order_manager.get_current_price(symbol)
                if not current_price:
                    continue

                entry    = pos.entry
                sl       = pos.sl
                sl_dist  = abs(entry - sl)
                if sl_dist <= 0:
                    continue

                triggered = False
                if pos.side == "LONG" and current_price >= entry + sl_dist:
                    triggered = True
                elif pos.side == "SHORT" and current_price <= entry - sl_dist:
                    triggered = True

                if triggered:
                    ok = await self.order_manager.modify_trade_sl(int(pos.order_id), symbol, new_sl=entry)
                    if ok:
                        pos.sl    = entry
                        pos.be_set = True
                        logger.info(
                            f"[BE] {symbol} {pos.side} — SL dời về entry {entry:.5f} "
                            f"(giá hiện tại {current_price:.5f}, +1R={sl_dist:.5f})"
                        )
                        await telegram.send(
                            f"🛡 [LIVE] Breakeven set\n"
                            f"{symbol} {pos.side} — SL → {entry:.5f}\n"
                            f"Price={current_price:.5f} (+{sl_dist:.5f} = 1R)"
                        )
                    else:
                        logger.warning(f"[BE] modify_trade_sl thất bại cho {symbol}")

            except Exception as e:
                logger.error(f"_check_breakeven_live error for {symbol}: {e}")

    async def _check_trailing_stop_live(self):
        """
        Trailing stop: sau khi BE set (1R), khi peak đạt 1.3R → trail SL = peak - 0.4R
        Match với backtest_engine logic để live/backtest nhất quán.
        Telegram chỉ gửi khi trail THAY ĐỔI (tránh spam khi trend mạnh).
        """
        if not self.position_monitor.open_positions:
            return

        for symbol, pos in list(self.position_monitor.open_positions.items()):
            try:
                if not pos.be_set:
                    continue  # chỉ trail sau khi BE đã set

                current_price = await self.order_manager.get_current_price(symbol)
                if not current_price:
                    continue

                entry = pos.entry

                # sl_dist gốc = (tp1_level - entry) / tp1_rr — không đổi dù SL đã dời
                if not pos.tp:
                    continue
                tp1_level = pos.tp[0]["level"]
                tp1_rr    = pos.tp[0].get("rr", 2.5)
                if tp1_rr <= 0:
                    continue
                sl_dist = abs(tp1_level - entry) / tp1_rr

                if sl_dist <= 0:
                    continue

                # Cập nhật peak price (luôn track, kể cả trước 1.3R)
                if pos.side == "LONG":
                    if current_price > pos.peak_price:
                        pos.peak_price = current_price

                    # Trailing: khi peak ≥ entry + 1.3R
                    if pos.peak_price >= entry + sl_dist * 1.3:
                        trail_sl = round(pos.peak_price - sl_dist * 0.4, 5)
                        if trail_sl > pos.sl:  # chỉ dời SL lên, không xuống
                            ok = await self.order_manager.modify_trade_sl(int(pos.order_id), symbol, new_sl=trail_sl)
                            if ok:
                                logger.info(f"[TRAIL] {symbol} LONG SL: {pos.sl:.5f} → {trail_sl:.5f} (peak={pos.peak_price:.5f})")
                                # Telegram chỉ khi lần đầu activate trailing
                                if not pos.trail_set:
                                    await telegram.send(
                                        f"📈 [LIVE] Trailing Stop activated\n"
                                        f"{symbol} LONG — SL → {trail_sl:.5f}\n"
                                        f"Peak={pos.peak_price:.5f} (+{(pos.peak_price-entry)/sl_dist:.1f}R)"
                                    )
                                    pos.trail_set = True
                                pos.sl = trail_sl

                elif pos.side == "SHORT":
                    if current_price < pos.peak_price:
                        pos.peak_price = current_price

                    # Trailing: khi peak ≤ entry - 1.3R
                    if pos.peak_price <= entry - sl_dist * 1.3:
                        trail_sl = round(pos.peak_price + sl_dist * 0.4, 5)
                        if trail_sl < pos.sl:  # chỉ dời SL xuống, không lên
                            ok = await self.order_manager.modify_trade_sl(int(pos.order_id), symbol, new_sl=trail_sl)
                            if ok:
                                logger.info(f"[TRAIL] {symbol} SHORT SL: {pos.sl:.5f} → {trail_sl:.5f} (peak={pos.peak_price:.5f})")
                                if not pos.trail_set:
                                    await telegram.send(
                                        f"📉 [LIVE] Trailing Stop activated\n"
                                        f"{symbol} SHORT — SL → {trail_sl:.5f}\n"
                                        f"Peak={pos.peak_price:.5f} (-{(entry-pos.peak_price)/sl_dist:.1f}R)"
                                    )
                                    pos.trail_set = True
                                pos.sl = trail_sl

            except Exception as e:
                logger.error(f"_check_trailing_stop_live error for {symbol}: {e}")

    async def _check_pending_limit_orders(self):
        """
        CHG-FX-027: Theo dõi các LIMIT entry CHƯA fill tại thời điểm đặt lệnh
        (_execute_signal chỉ check 1 lần, 2s sau khi đặt). Gọi mỗi 60s từ
        _monitoring_loop để poll lại trạng thái:
          - "filled"    -> đặt SL/TP (trước đây bị BỎ QUÊN hoàn toàn, gây
                           "naked position" không có SL/TP) + finalize
                           (telegram/DB/position_monitor).
          - "cancelled" -> order đã bị cancel (vd: tay trên dashboard, hoặc
                           IB tự cancel) -> bỏ theo dõi, không làm gì thêm.
          - "open"      -> vẫn đang chờ khớp -> giữ nguyên, check lại lần sau.
          - None        -> không tìm thấy order (đã bị xoá khỏi IB) -> bỏ
                           theo dõi (coi như cancelled).
        """
        if not self._pending_limit_orders:
            return

        # LIMIT_ORDER_TIMEOUT_CANDLES * ENTRY_TIMEFRAME (phút) = tổng thời gian tối đa
        # Tính theo giây để so sánh với timedelta. 0 = vô hiệu hoá timeout (GTC mãi).
        _tf_minutes = {"1m":1,"5m":5,"15m":15,"30m":30,"1h":60,"4h":240,"1d":1440}
        _tf_min = _tf_minutes.get(ENTRY_TIMEFRAME, 15)
        _timeout_sec = LIMIT_ORDER_TIMEOUT_CANDLES * _tf_min * 60 if LIMIT_ORDER_TIMEOUT_CANDLES > 0 else 0

        for symbol, pend in list(self._pending_limit_orders.items()):
            try:
                # CHG-FX-028: kiểm tra timeout — nếu quá hạn, cancel lệnh + bỏ theo dõi.
                if _timeout_sec > 0 and "placed_at" in pend:
                    age = (datetime.now(tz=timezone.utc) - pend["placed_at"]).total_seconds()
                    if age > _timeout_sec:
                        logger.info(
                            f"[LIVE] Pending LIMIT #{pend['order_id']} ({symbol}) "
                            f"timeout sau {age/60:.0f} phút "
                            f"({LIMIT_ORDER_TIMEOUT_CANDLES} candle {ENTRY_TIMEFRAME}) "
                            f"— tự cancel"
                        )
                        await self.order_manager.cancel_order(pend["ticket"])
                        _sig = pend.get("signal", {})
                        _rsk = pend.get("risk", {})
                        _tp  = pend.get("tp_level", 0)
                        await telegram.send(
                            f"🚫 [LIVE] LIMIT {_sig.get('side','')} {symbol} cancelled\n"
                            f"  Entry : {_sig.get('entry_price', 0):.5f}\n"
                            f"  SL    : {_rsk.get('sl', 0):.5f}\n"
                            f"  TP    : {_tp:.5f}\n"
                            f"  Lý do : timeout {LIMIT_ORDER_TIMEOUT_CANDLES} nến {ENTRY_TIMEFRAME} chưa khớp"
                        )
                        del self._pending_limit_orders[symbol]
                        continue

                # MT5: kiểm tra ticket còn trong pending orders không
                ticket     = pend.get("ticket", 0)
                pending    = await self.order_manager.get_pending_orders(symbol)
                ticket_ids = [o["ticket"] for o in pending]

                if ticket not in ticket_ids:
                    # Không còn pending → kiểm tra xem đã fill thành position chưa
                    pos = await self.order_manager.get_position(symbol)
                    if pos:
                        signal, risk = pend["signal"], pend["risk"]
                        await self._finalize_entry(symbol, pend["order_id"], signal, risk, pend["tp_level"])
                        logger.info(f"[LIVE] LIMIT #{ticket} ({symbol}) filled → finalized")
                    else:
                        logger.info(f"[LIVE] LIMIT #{ticket} ({symbol}) bị cancel → bỏ theo dõi")
                    del self._pending_limit_orders[symbol]
                # còn trong pending → chưa fill, chờ tiếp

            except Exception as e:
                logger.error(f"_check_pending_limit_orders error for {symbol}: {e}")

    async def _check_closed_positions(self, current_balance: Optional[float]):
        """
        Compare locally tracked positions against IBKR.
        If a position is no longer on IBKR → it was closed by TP/SL → update DB.

        CÁCH DETECT TP/SL HIT:
        Bot không subscribe MT5 fill notifications (dùng polling).
        Thay vào đó: mỗi 60s, hỏi MT5 "position còn tồn tại không?".
        Nếu pos=None → đã đóng → fetch history qua get_last_closed_trade().
        Latency: tối đa 60s trễ sau khi TP/SL hit → acceptable cho scalping.

        Lưu ý: position_monitor.open_positions dùng symbol làm key.
        Nếu có cả LONG lẫn SHORT cùng symbol → overwrite (known bug, xem GUIDELINE section 26).
        """
        if not self.position_monitor.open_positions:
            return

        for symbol, pos in list(self.position_monitor.open_positions.items()):
            try:
                mt5_pos  = await self.order_manager.get_position(symbol)
                pos_open = mt5_pos is not None

                if not pos_open:
                    # Position closed on MT5 (TP/SL hit) — fetch close details
                    exit_price, pnl, status = await self._get_close_details(symbol, pos)

                    icon = "✅" if pnl and pnl > 0 else ("🔴" if pnl and pnl < 0 else "⚪")
                    msg = (
                        f"{icon} [LIVE] {status} {pos.side} {symbol}\n"
                        f"  Exit  : {exit_price:.5f}\n"
                        f"  P&L   : ${pnl:+.2f}\n"
                        f"  Entry : {pos.entry:.5f}"
                    )
                    logger.info(msg)
                    await telegram.send(msg)

                    # Update DB
                    if hasattr(self, "_db") and self._db:
                        await self._db.save_live_trade_close(
                            order_id=pos.order_id,
                            exit_price=exit_price,
                            pnl=pnl,
                            status=status,
                            balance=current_balance or self.risk_engine.account_balance,
                        )
                        # Update candle_tracker_live outcome (chỉ update outcome columns, không đụng các cột khác)
                        if pos.candle_time:
                            await self._db.update_candle_tracker_outcome(
                                symbol=symbol,
                                timeframe=ENTRY_TIMEFRAME,
                                candle_time=pos.candle_time,
                                side=pos.side,
                                exit_price=exit_price,
                                pnl=pnl,
                                exit_reason=status,
                            )

                    # Update risk engine
                    if pnl:
                        self.risk_engine.register_pnl(pnl)

                    self.position_monitor.remove(symbol)

            except Exception as e:
                logger.error(f"_check_closed_positions error for {symbol}: {e}")

    async def _get_close_details(self, symbol: str, pos) -> tuple:
        """Fetch exit price + PnL from MT5 deal history."""
        try:
            closed = await self.order_manager.get_last_closed_trade(symbol)
            if closed:
                exit_price = float(closed.get("close", 0) or 0)
                realized   = float(closed.get("profit", 0) or 0)
                status = "TP" if realized > 0 else ("SL" if realized < 0 else "BE")
                return exit_price, realized, status
        except Exception as e:
            logger.error(f"_get_close_details error: {e}")

        # Fallback: estimate from last known price
        return pos.entry, 0.0, "CLOSED"

    async def stop(self):
        self._running = False
        logger.info("Live engine stopped")
        await telegram.send("⏹ Live Trading Engine stopped")
