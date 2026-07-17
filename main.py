"""
MT5 SMC Scalper Bot — Main Orchestrator.
Data source : MetaTrader5 (Windows) / yfinance (Mac/Linux)
Order source: MetaTrader5 Python API (Windows only)

Usage:
    python main.py download               # Phase 1: download historical data
    python main.py backtest               # Phase 7: run backtest on stored data
    python main.py paper                  # Phase 8: paper trading on live market
    python main.py live                   # Phase 9: real money trading (Windows only)
    python main.py debug --symbol EURUSD  # Debug: trace layers
"""
import asyncio
import argparse
import sys

from utils.logger import logger
from utils.telegram import telegram
from config.settings import SYMBOLS, TIMEFRAMES, HISTORICAL_YEARS, ENTRY_TIMEFRAME, DATA_SOURCE, IS_WINDOWS


# ─────────────────────────────────────────────
# HELPER: pick downloader / collector by OS
# ─────────────────────────────────────────────
def _get_downloader():
    import os
    provider = os.getenv("DATA_PROVIDER", "").upper()

    if DATA_SOURCE == "MT5":
        from phase1_data.mt5_downloader import MT5Downloader
        dl = MT5Downloader(); dl.connect(); return dl
    elif provider == "DUKASCOPY":
        # Dukascopy: bid price, chất lượng cao, không cần API key
        from phase1_data.dukascopy_downloader import DukascopyDownloader
        dl = DukascopyDownloader(); dl.connect(); return dl
    elif os.getenv("TWELVE_DATA_API_KEY"):
        # Twelve Data: 2 năm 15m, cần API key
        from phase1_data.twelvedata_downloader import TwelveDataDownloader
        dl = TwelveDataDownloader(); dl.connect(); return dl
    else:
        from phase1_data.yfinance_downloader import YFinanceDownloader
        dl = YFinanceDownloader(); dl.connect(); return dl


def _get_collector(symbols, timeframes, db, on_candle):
    if DATA_SOURCE == "MT5":
        from phase1_data.mt5_collector import MT5StreamingCollector
        return MT5StreamingCollector(symbols, timeframes, db, on_candle=on_candle)
    else:
        from phase1_data.yfinance_collector import YFinanceStreamingCollector
        return YFinanceStreamingCollector(symbols, timeframes, db, on_candle=on_candle)


# ─────────────────────────────────────────────
# MODE: DOWNLOAD
# ─────────────────────────────────────────────
async def run_download(extra_symbols: list = None):
    """Phase 1: Download historical data for all symbols/timeframes."""
    from datetime import datetime, timezone, timedelta
    from phase1_data.database import Database

    MIN_HISTORY_DAYS = 180

    db = Database()
    await db.connect()

    symbols_to_download = list(SYMBOLS)
    if extra_symbols:
        for s in extra_symbols:
            if s not in symbols_to_download:
                symbols_to_download.append(s)

    dl = _get_downloader()
    is_dukascopy = dl.__class__.__name__ == "DukascopyDownloader"

    for symbol in symbols_to_download:

        if is_dukascopy:
            # ── Dukascopy: download ticks 1 lần → aggregate tất cả TFs ──
            # Lấy earliest since trong tất cả TFs để download đủ data
            now = datetime.now(tz=timezone.utc)
            since_per_tf = {}
            min_since = None
            for tf in TIMEFRAMES:
                latest   = await db.get_latest_open_time(symbol, tf)
                earliest = await db.get_earliest_open_time(symbol, tf)
                has_enough = (
                    earliest is not None and
                    (now - earliest.replace(tzinfo=timezone.utc)).days >= MIN_HISTORY_DAYS
                )
                since_tf = latest if has_enough else None
                since_per_tf[tf] = since_tf
                if since_tf is None:
                    min_since = None  # Cần full download
                elif min_since is None or since_tf < min_since:
                    min_since = since_tf

            logger.info(f"Dukascopy {symbol}: downloading ticks once → {TIMEFRAMES}")

            # Download ticks 1 lần với since sớm nhất
            for tf in TIMEFRAMES:
                since = since_per_tf[tf]
                candles = await dl.download_history(symbol, tf,
                                                    years=HISTORICAL_YEARS, since=since)
                if candles:
                    cnt = await db.upsert_candles_bulk(symbol, tf, candles)
                    logger.info(f"Saved {cnt} candles for {symbol} {tf}")
                elif since is not None:
                    logger.info(f"No new candles for {symbol} {tf} (already up to date)")
                else:
                    logger.warning(f"No data for {symbol} {tf}")

        else:
            # ── Khác (Twelve Data, yfinance, MT5): download từng TF ──
            for tf in TIMEFRAMES:
                latest   = await db.get_latest_open_time(symbol, tf)
                earliest = await db.get_earliest_open_time(symbol, tf)
                now = datetime.now(tz=timezone.utc)

                has_enough = (
                    earliest is not None and
                    (now - earliest.replace(tzinfo=timezone.utc)).days >= MIN_HISTORY_DAYS
                )
                since = latest if has_enough else None

                if since is None:
                    logger.info(f"Full download: {symbol} {tf} (insufficient history in DB)")
                else:
                    logger.info(f"Incremental update: {symbol} {tf} from {since.date()}")

                candles = await dl.download_history(symbol, tf,
                                                    years=HISTORICAL_YEARS, since=since)
                if candles:
                    cnt = await db.upsert_candles_bulk(symbol, tf, candles)
                    logger.info(f"Saved {cnt} candles for {symbol} {tf}")
                elif since is not None:
                    logger.info(f"No new candles for {symbol} {tf} (already up to date)")
                else:
                    logger.warning(f"No data returned for {symbol} {tf} — check API key or symbol map")

    dl.disconnect()
    await db.disconnect()
    logger.info("Download complete")


# ─────────────────────────────────────────────
# MODE: BACKTEST
# ─────────────────────────────────────────────
async def run_backtest(symbol: str = "EURUSD", timeframe: str = "1h",
                       limit: int = 210_000, offset: int = 0,
                       use_news_filter: bool = False,
                       from_date: str = None, to_date: str = None,
                       initial_balance: float = 10_000.0):
    """Phase 7: Run event-driven backtest on historical data."""
    from datetime import datetime, timezone, timedelta
    from phase1_data.database import Database
    from phase7_backtest.backtest_engine import BacktestEngine
    from phase7_backtest.walk_forward import walk_forward_test
    from phase7_backtest.performance_metrics import monte_carlo_simulation
    from phase1_data.validator import tf_to_seconds

    db = Database()
    await db.connect()

    _from_dt = _to_dt = None
    if from_date:
        _from_dt = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
    if to_date:
        _to_dt = datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)

    logger.info(f"Loading candles for {symbol} {timeframe} ...")

    if _from_dt:
        step_s = tf_to_seconds(timeframe)
        warmup_since = _from_dt - timedelta(seconds=step_s * 500)
        candles = await db.get_candles(symbol, timeframe, limit=210_000, since=warmup_since)
    else:
        candles = await db.get_candles(symbol, timeframe, limit=210_000)

    if timeframe in ("5m", "15m"):
        mtf_since = (_from_dt - timedelta(hours=300)) if _from_dt else None
        candles_15m = await db.get_candles(symbol, "15m", limit=70_000, since=mtf_since)
        candles_1h  = await db.get_candles(symbol, "1h",  limit=17_520, since=mtf_since)
    else:
        candles_15m, candles_1h = [], []

    if len(candles) < 200:
        await db.disconnect()
        logger.error("Insufficient candle data. Run 'python main.py download' first.")
        return

    if _to_dt:
        candles = [c for c in candles if c["open_time"] <= _to_dt]

    if _from_dt:
        warmup = next((i for i, c in enumerate(candles) if c["open_time"] >= _from_dt), 50)
        warmup = max(warmup, 50)
        logger.info(f"Custom range: from {from_date} → warmup={warmup} candles")
    else:
        if offset > 0:
            candles = candles[offset:]
        candles = candles[:limit]
        warmup = 50

    start_date = candles[0]["open_time"].strftime("%Y-%m-%d")
    end_date   = candles[-1]["open_time"].strftime("%Y-%m-%d")
    logger.info(f"Running backtest on {len(candles)} candles ({start_date} → {end_date})")

    nf = None
    if use_news_filter:
        from utils.news_filter import NewsFilter
        from config.settings import FINNHUB_API_KEY
        nf = NewsFilter(api_key=FINNHUB_API_KEY)
        logger.info("Loading Finnhub economic calendar ...")
        await nf.refresh(days_back=365 * 2, days_ahead=0)
        logger.info(f"News filter ready: {nf.event_count} US high-impact events")

    # Truncate backtest tracker before each run to avoid mixing stale data
    # (UPSERT on (symbol, timeframe, candle_time, side) can mix old & new runs)
    try:
        async with db.pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE candle_tracker_backtest")
        logger.info("candle_tracker_backtest truncated ✅")
    except Exception as e:
        logger.warning(f"Could not truncate candle_tracker_backtest: {e}")

    engine = BacktestEngine(symbol, timeframe,
                            initial_balance=initial_balance,
                            candles_15m=candles_15m,
                            candles_1h=candles_1h,
                            enable_tracker=True,
                            news_filter=nf)
    results = engine.run(candles, warmup=warmup)

    if engine._tracker_records:
        logger.info(f"Saving {len(engine._tracker_records)} candle_tracker records ...")
        await db.bulk_save_candle_tracker(engine._tracker_records)
        logger.info("candle_tracker saved ✅")

    await db.disconnect()

    print("\n" + "═" * 50)
    print(f"  BACKTEST RESULTS — {symbol} {timeframe}")
    print(f"  Period: {start_date} → {end_date}")
    print("═" * 50)
    for k, v in results.items():
        if k != "passed":
            print(f"  {k:<25}: {v}")
    print(f"  {'PASSED':<25}: {'✅ YES' if results.get('passed') else '❌ NO'}")
    print("═" * 50)

    _print_quarterly_breakdown(engine.trades, engine.equity_curve, engine.initial_balance)

    logger.info("Running walk-forward validation ...")
    wf = walk_forward_test(candles, symbol, timeframe,
                           candles_15m=candles_15m, candles_1h=candles_1h)
    print("\n  Walk-Forward:")
    for k, v in wf.items():
        if k != "folds":
            print(f"    {k}: {v}")

    if engine.trades:
        pnls = [t.pnl for t in engine.trades]
        mc = monte_carlo_simulation(pnls, 10_000)
        print("\n  Monte Carlo (1000 simulations):")
        for k, v in mc.items():
            print(f"    {k}: {v}")


async def run_backtest_multi(symbols: list, timeframe: str,
                             limit: int = 210_000, offset: int = 0,
                             from_date: str = None, to_date: str = None,
                             initial_balance: float = 5_000.0):
    """Chạy backtest cho nhiều symbol trên cùng $10k."""
    from datetime import datetime, timezone, timedelta
    from phase1_data.database import Database
    from phase7_backtest.backtest_engine import BacktestEngine
    from phase1_data.validator import tf_to_seconds

    _from_dt = _to_dt = None
    if from_date:
        _from_dt = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
    if to_date:
        _to_dt = datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)

    INITIAL = initial_balance
    db = Database()
    await db.connect()

    all_results = {}

    for symbol in symbols:
        if _from_dt:
            step_s = tf_to_seconds(timeframe)
            warmup_since = _from_dt - timedelta(seconds=step_s * 500)
            candles = await db.get_candles(symbol, timeframe, limit=limit, since=warmup_since)
            mtf_since = _from_dt - timedelta(hours=300)
            c15m = await db.get_candles(symbol, "15m", limit=70_000, since=mtf_since) if timeframe in ("5m","15m") else []
            c1h  = await db.get_candles(symbol, "1h",  limit=17_520, since=mtf_since) if timeframe in ("5m","15m") else []
        else:
            candles = await db.get_candles(symbol, timeframe, limit=limit)
            c15m    = await db.get_candles(symbol, "15m", limit=70_000) if timeframe in ("5m","15m") else []
            c1h     = await db.get_candles(symbol, "1h",  limit=17_520) if timeframe in ("5m","15m") else []

        if _to_dt:
            candles = [c for c in candles if c["open_time"] <= _to_dt]

        if _from_dt:
            warmup = next((i for i, c in enumerate(candles) if c["open_time"] >= _from_dt), 50)
            warmup = max(warmup, 50)
        else:
            if offset > 0:
                candles = candles[offset:]
            candles = candles[:limit]
            warmup = 50

        if len(candles) < 200:
            logger.warning(f"Insufficient data for {symbol}, skipping")
            continue

        engine = BacktestEngine(symbol, timeframe, initial_balance=INITIAL,
                                candles_15m=c15m, candles_1h=c1h, enable_tracker=True)
        results = engine.run(candles, warmup=warmup)
        all_results[symbol] = (results, engine.trades)

        if engine._tracker_records:
            logger.info(f"Saving {len(engine._tracker_records)} tracker records for {symbol} ...")
            await db.bulk_save_candle_tracker(engine._tracker_records)

        print(f"\n{'═'*50}")
        print(f"  {symbol} {timeframe}")
        print(f"{'═'*50}")
        for k, v in results.items():
            if k != "passed":
                print(f"  {k:<25}: {v}")
        print(f"  {'PASSED':<25}: {'✅ YES' if results.get('passed') else '❌ NO'}")

    await db.disconnect()

    if len(all_results) < 2:
        return

    total_pnl = sum(r[0]["net_profit"] for r in all_results.values())
    total_pct = total_pnl / INITIAL
    total_tp  = sum(r[0].get("tp_count", 0) for r in all_results.values())
    total_sl  = sum(r[0].get("sl_count", 0) for r in all_results.values())
    total_be  = sum(r[0].get("be_count", 0) for r in all_results.values())
    total_n   = sum(r[0]["total_trades"] for r in all_results.values())
    avg_wrate = sum(r[0]["winrate"] for r in all_results.values()) / len(all_results)
    final_bal = INITIAL + total_pnl

    print(f"\n{'═'*50}")
    print(f"  COMBINED ({' + '.join(symbols)}) — vốn ${INITIAL:,.0f}")
    print(f"{'═'*50}")
    print(f"  {'total_trades':<25}: {total_n}")
    print(f"  {'avg_winrate':<25}: {avg_wrate:.4f}")
    print(f"  {'net_profit':<25}: {total_pnl:+.2f}  ({total_pct*100:+.1f}%)")
    print(f"  {'tp / sl / be':<25}: {total_tp} / {total_sl} / {total_be}")
    print(f"  {'final_balance':<25}: ${final_bal:,.2f}")
    print(f"{'═'*50}")


def _print_quarterly_breakdown(trades, equity_curve, initial_balance):
    if not equity_curve:
        return
    from collections import defaultdict

    quarterly = defaultdict(list)
    for e in equity_curve:
        t = e["time"]
        quarter = f"{t.year}-Q{(t.month - 1) // 3 + 1}"
        quarterly[quarter].append(e["balance"])

    trade_by_q = defaultdict(list)
    for t in trades:
        if t.exit_time:
            q = f"{t.exit_time.year}-Q{(t.exit_time.month - 1) // 3 + 1}"
            trade_by_q[q].append(t)

    print("\n  ── Quarterly Breakdown ──────────────────────────────")
    print(f"  {'Quarter':<10} {'Trades':>7} {'Win%':>6} {'P&L':>10} {'Balance':>10} {'DD%':>7}")
    print("  " + "─" * 55)

    prev_balance = initial_balance
    for q in sorted(quarterly.keys()):
        balances = quarterly[q]
        end_bal  = balances[-1]
        pnl      = end_bal - prev_balance
        pnl_pct  = pnl / prev_balance * 100
        qtrades  = trade_by_q.get(q, [])
        n        = len(qtrades)
        wins     = sum(1 for t in qtrades if t.pnl > 0)
        winpct   = wins / n * 100 if n > 0 else 0
        peak     = max(balances)
        trough   = min(balances[balances.index(peak):]) if peak in balances else end_bal
        dd       = (peak - trough) / peak * 100 if peak > 0 else 0
        arrow    = "📈" if pnl >= 0 else "📉"
        print(f"  {q:<10} {n:>7} {winpct:>5.0f}% {pnl:>+9.0f} {end_bal:>10.0f} {dd:>6.1f}%  {arrow}")
        prev_balance = end_bal

    print("  " + "─" * 55)
    final     = equity_curve[-1]["balance"]
    total_pnl = final - initial_balance
    print(f"  {'TOTAL':<10} {len(trades):>7} {'':>6} {total_pnl:>+9.0f} {final:>10.0f}")


# ─────────────────────────────────────────────
# PERIODIC BACKFILL (paper mode background task)
# ─────────────────────────────────────────────
async def _periodic_backfill_loop(db, lookback_hours: int = 2, interval_s: int = 3600):
    """Mỗi interval_s giây, fill lại candle bị thiếu (do collector polling miss)."""
    from phase1_data.backfill import BackfillService

    while True:
        await asyncio.sleep(interval_s)
        try:
            logger.info(f"[PeriodicBackfill] Checking last {lookback_hours}h for gaps ...")
            dl = _get_downloader()
            bf = BackfillService(db, dl)
            await bf.run_all(lookback_hours=lookback_hours)
            dl.disconnect()
            logger.info("[PeriodicBackfill] Check complete")
        except Exception as e:
            logger.error(f"[PeriodicBackfill] error: {e}")


# ─────────────────────────────────────────────
# MODE: PAPER TRADING
# ─────────────────────────────────────────────
async def run_paper():
    """Phase 8: Paper trading on live market data."""
    from phase1_data.database import Database
    from phase1_data.backfill import BackfillService
    from phase8_paper.paper_engine import PaperTradingEngine

    db = Database()
    await db.connect()

    # Backfill recent gaps
    dl = _get_downloader()
    bf = BackfillService(db, dl)
    await bf.run_all(lookback_hours=24)
    dl.disconnect()

    paper = PaperTradingEngine(strategy_runner=_make_strategy_runner(), db=db)

    collect_tfs_preload = list({ENTRY_TIMEFRAME, "5m", "1h"})
    await paper.preload_from_db(db, SYMBOLS, collect_tfs_preload, limit=500)

    collect_tfs = list({ENTRY_TIMEFRAME, "5m", "1h"})
    collector   = _get_collector(SYMBOLS, collect_tfs, db, on_candle=paper.on_candle)

    logger.info(f"Paper trading started [{DATA_SOURCE}]")
    await telegram.send(f"📝 Paper Trading Started | {DATA_SOURCE} | {', '.join(SYMBOLS)}")

    asyncio.create_task(_periodic_backfill_loop(db, lookback_hours=2, interval_s=3600))

    try:
        await collector.start()
    except KeyboardInterrupt:
        logger.info("Paper trading stopped by user")
        metrics = paper.get_metrics()
        logger.info(f"Final metrics: {metrics}")
        await telegram.send(f"📝 Paper Trading Stopped\n{metrics}")
    finally:
        await db.disconnect()


# ─────────────────────────────────────────────
# MODE: LIVE TRADING
# ─────────────────────────────────────────────
async def run_live():
    """Phase 9: Live trading — Windows VPS + MT5 terminal only."""
    if not IS_WINDOWS:
        logger.error(
            "❌ Live trading chỉ hỗ trợ trên Windows VPS với MT5 terminal.\n"
            "   Mac/Linux: dùng 'python main.py paper' để paper trading.\n"
            "   Xem VPS_WINDOWS_DEPLOY.md để hướng dẫn deploy."
        )
        sys.exit(1)

    import signal
    from phase1_data.database import Database
    from phase9_live.live_engine import LiveTradingEngine

    db = Database()
    await db.connect()

    engine = LiveTradingEngine()

    loop = asyncio.get_event_loop()
    def _handle_sigterm():
        logger.info("SIGTERM received — shutting down gracefully ...")
        asyncio.create_task(_shutdown(engine, db))

    async def _shutdown(eng, database):
        await telegram.send("⏹ Bot stopped (SIGTERM)")
        await eng.stop()
        await database.disconnect()
        loop.stop()

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)

    try:
        await engine.start(db)
    except KeyboardInterrupt:
        logger.info("Live engine stopped by user")
        await telegram.send("⏹ Bot stopped (KeyboardInterrupt)")
        await engine.stop()
    except Exception as e:
        logger.error(f"Live engine crashed: {e}", exc_info=True)
        await telegram.send(f"🔴 Bot CRASHED: {e}\nCheck logs immediately!")
        await engine.stop()
        raise
    finally:
        await db.disconnect()


# ─────────────────────────────────────────────
# SHARED STRATEGY RUNNER (used by paper mode)
# ─────────────────────────────────────────────
def _make_strategy_runner():
    from phase2_structure.structure_engine import StructureEngine
    from phase2_structure.mtf_bias import MTFBias
    from phase3_liquidity.liquidity_engine import build_liquidity_zones
    from phase3_liquidity.sweep_detector import detect_sweep
    from phase3_liquidity.choch_detector import detect_choch, StructureShiftTracker
    from phase4_fvg_ob.fvg_engine import detect_fvg, update_fvg_fills
    from phase4_fvg_ob.orderblock_engine import detect_all_obs, update_ob_mitigation
    from phase4_fvg_ob.zone_builder import find_confluence_zones, build_entry_zone
    from phase5_entry.entry_engine import EntryEngine
    from phase6_risk.risk_engine import RiskEngine

    engines = {
        symbol: {
            "structure":    StructureEngine(symbol, ENTRY_TIMEFRAME),
            "structure_1h": StructureEngine(symbol, "1h"),
            "entry":        EntryEngine(symbol, ENTRY_TIMEFRAME),
            "shift":        StructureShiftTracker(),
            "mtf":          MTFBias(),
            "fvgs": [],
            "obs":  [],
        }
        for symbol in SYMBOLS
    }
    risk = RiskEngine()

    async def strategy_runner(candle: dict, candles: list):
        symbol = candle["symbol"]
        tf     = candle["timeframe"]
        if symbol not in engines:
            return None
        eng = engines[symbol]

        if tf == "1h":
            struct_1h = eng["structure_1h"].update(candles)
            eng["mtf"].update("1h", struct_1h.get("trend", "RANGE"))

        if tf != ENTRY_TIMEFRAME:
            return None

        struct = eng["structure"].update(candles)
        eng["mtf"].update(ENTRY_TIMEFRAME, struct.get("trend", "RANGE"))

        swing_highs = [s for s in struct.get("structure", []) if s.get("type") in ("swing_high", "HH", "LH")]
        swing_lows  = [s for s in struct.get("structure", []) if s.get("type") in ("swing_low", "HL", "LL")]
        liq_zones   = build_liquidity_zones(swing_highs, swing_lows)
        sweep       = detect_sweep(candle, struct.get("last_swing_high"), struct.get("last_swing_low"))
        last_bos    = struct["bos_events"][-1] if struct.get("bos_events") else None
        choch       = detect_choch(struct.get("trend", "RANGE"), last_bos)
        shift       = eng["shift"].process(choch, last_bos, candle["close"])
        liq_output  = {
            "liq_zones": liq_zones, "last_sweep": sweep,
            "last_choch": choch, "structure_shift": shift,
            "mtf_bias": eng["mtf"].get_bias(),
        }

        eng["fvgs"] = detect_fvg(candles[-30:])
        eng["fvgs"] = update_fvg_fills(eng["fvgs"], candle)
        eng["obs"]  = detect_all_obs(candles[-50:], struct.get("bos_events", []))
        eng["obs"]  = update_ob_mitigation(eng["obs"], candle)
        confluence  = find_confluence_zones(eng["fvgs"], eng["obs"])

        for side in ("LONG", "SHORT"):
            entry_zone = build_entry_zone(side, eng["fvgs"], eng["obs"], confluence)
            if not entry_zone:
                continue
            risk_out = risk.evaluate(side, symbol, entry_zone["midpoint"], candles, struct, liq_zones)
            if not risk_out:
                continue
            signal = eng["entry"].evaluate(candles, struct, liq_output, entry_zone, risk_out)
            if signal:
                return signal
        return None

    return strategy_runner


# ─────────────────────────────────────────────
# MODE: DEBUG
# ─────────────────────────────────────────────
async def run_debug(symbol: str = "EURUSD", timeframe: str = "1h", limit: int = 2000):
    """Debug: trace how many candles pass each entry layer."""
    from phase1_data.database import Database
    from phase2_structure.structure_engine import StructureEngine
    from phase2_structure.mtf_bias import MTFBias
    from phase3_liquidity.liquidity_engine import build_liquidity_zones
    from phase3_liquidity.sweep_detector import detect_sweep
    from phase3_liquidity.choch_detector import detect_choch, StructureShiftTracker
    from phase4_fvg_ob.fvg_engine import detect_fvg, update_fvg_fills, _calc_atr
    from phase4_fvg_ob.orderblock_engine import detect_all_obs, update_ob_mitigation
    from phase4_fvg_ob.zone_builder import find_confluence_zones, build_entry_zone
    from phase5_entry.trigger_detector import classify_trigger
    from phase6_risk.risk_engine import RiskEngine
    from config.settings import VOLUME_THRESHOLD
    import numpy as np

    db = Database()
    await db.connect()
    candles = await db.get_candles(symbol, timeframe, limit=limit)
    await db.disconnect()

    if len(candles) < 100:
        print("Not enough candles. Run 'python main.py download' first.")
        return

    print(f"\nDebug: {symbol} {timeframe} — {len(candles)} candles\n")

    se   = StructureEngine(symbol, timeframe)
    risk = RiskEngine(5000)
    shift_tracker = StructureShiftTracker()

    last_sweep = last_choch = None
    sweep_ttl = choch_ttl = 0
    fvgs = obs = []

    counts = {"total": 0, "has_zone": 0, "L1_trend": 0, "L2_zone_touch": 0,
              "L3_liquidity": 0, "L4_volume": 0, "L5_trigger": 0, "risk_ok": 0}

    warmup = 50
    for i in range(warmup, len(candles)):
        window  = candles[max(0, i-200): i+1]
        current = candles[i]
        counts["total"] += 1

        struct      = se.update(window)
        swing_highs = [s for s in struct.get("structure", []) if s.get("type") == "swing_high"]
        swing_lows  = [s for s in struct.get("structure", []) if s.get("type") == "swing_low"]
        liq_zones   = build_liquidity_zones(swing_highs, swing_lows)

        new_sweep = detect_sweep(current, struct.get("last_swing_high"), struct.get("last_swing_low"))
        last_bos  = struct["bos_events"][-1] if struct.get("bos_events") else None
        new_choch = detect_choch(struct.get("trend", "RANGE"), last_bos)
        shift     = shift_tracker.process(new_choch, last_bos, current["close"])

        if new_sweep:   last_sweep = new_sweep; sweep_ttl = 20
        elif sweep_ttl > 0: sweep_ttl -= 1
        else: last_sweep = None

        if new_choch:   last_choch = new_choch; choch_ttl = 20
        elif choch_ttl > 0: choch_ttl -= 1
        else: last_choch = None

        trend    = struct.get("trend", "RANGE")
        mtf_bias = "LONG" if trend in ("UP","UPTREND") else \
                   "SHORT" if trend in ("DOWN","DOWNTREND") else "NEUTRAL"
        liq_output = {"liq_zones": liq_zones, "last_sweep": last_sweep,
                      "last_choch": last_choch, "structure_shift": shift, "mtf_bias": mtf_bias}

        atr           = _calc_atr(window)
        current_price = current["close"]
        fvgs          = detect_fvg(window[-30:])
        fvgs          = update_fvg_fills(fvgs, current)
        obs           = detect_all_obs(window[-50:], struct.get("bos_events", []))
        obs           = update_ob_mitigation(obs, current)
        confluence    = find_confluence_zones(fvgs, obs)

        for side in ("LONG", "SHORT"):
            ez = build_entry_zone(side, fvgs, obs, confluence, current_price=current_price, atr=atr)
            if ez is None:
                continue
            counts["has_zone"] += 1

            if side == "LONG":
                ok = trend in ("UP","UPTREND") or mtf_bias == "LONG" or (
                    trend == "RANGE" and last_sweep and last_sweep["type"] == "BUY_SIDE_SWEEP"
                    and last_choch and last_choch["type"] == "BULLISH_CHOCH")
            else:
                ok = trend in ("DOWN","DOWNTREND") or mtf_bias == "SHORT" or (
                    trend == "RANGE" and last_sweep and last_sweep["type"] == "SELL_SIDE_SWEEP"
                    and last_choch and last_choch["type"] == "BEARISH_CHOCH")
            if not ok:
                continue
            counts["L1_trend"] += 1

            lo, hi = ez["low"], ez["high"]
            buf = hi * 0.001
            if side == "LONG":
                touches = current["low"] <= (hi + buf) and current["close"] >= (lo - buf)
            else:
                touches = current["high"] >= (lo - buf) and current["close"] <= (hi + buf)
            if not touches:
                continue
            counts["L2_zone_touch"] += 1

            sweep_ok = last_sweep and (
                (side == "LONG" and last_sweep["type"] == "BUY_SIDE_SWEEP") or
                (side == "SHORT" and last_sweep["type"] == "SELL_SIDE_SWEEP"))
            choch_ok = last_choch and (
                (side == "LONG" and last_choch["type"] == "BULLISH_CHOCH") or
                (side == "SHORT" and last_choch["type"] == "BEARISH_CHOCH"))
            if not (sweep_ok or choch_ok):
                continue
            counts["L3_liquidity"] += 1

            if len(window) >= 20:
                avg_vol = np.mean([c["volume"] for c in window[-20:]])
                if avg_vol > 0 and current["volume"] / avg_vol < VOLUME_THRESHOLD:
                    continue
            counts["L4_volume"] += 1

            trigger = classify_trigger(window, side)
            if trigger is None:
                continue
            counts["L5_trigger"] += 1

            risk_out = risk.evaluate(side, symbol, ez["midpoint"], window, struct, liq_zones)
            if risk_out:
                counts["risk_ok"] += 1

    print("═" * 45)
    print(f"  Layer                  Passed / Total")
    print("═" * 45)
    print(f"  Total candles          {counts['total']}")
    print(f"  Has entry zone         {counts['has_zone']}")
    print(f"  L1 Trend aligned       {counts['L1_trend']}")
    print(f"  L2 Zone touched        {counts['L2_zone_touch']}")
    print(f"  L3 Sweep/CHoCH         {counts['L3_liquidity']}")
    print(f"  L4 Volume OK           {counts['L4_volume']}")
    print(f"  L5 Trigger candle      {counts['L5_trigger']}")
    print(f"  Risk OK (RR≥1.5)       {counts['risk_ok']}")
    print("═" * 45)
    print(f"\n  FVGs detected (last window): {len(fvgs)}")
    print(f"  OBs detected  (last window): {len(obs)}")
    print(f"  Last trend: {struct.get('trend')}")
    print(f"  Last sweep: {last_sweep and last_sweep['type']}")
    print(f"  Last choch: {last_choch and last_choch['type']}")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MT5 SMC Scalper Bot")
    parser.add_argument("mode", choices=["download", "backtest", "paper", "live", "debug"])
    parser.add_argument("--symbol", default=",".join(SYMBOLS),
                        help="Symbol(s) — dấu phẩy cho nhiều: EURUSD,GBPUSD")
    parser.add_argument("--tf",     default=ENTRY_TIMEFRAME, help="Timeframe (backtest/debug)")
    parser.add_argument("--limit",  default=2000, type=int)
    parser.add_argument("--offset", default=0,    type=int)
    parser.add_argument("--from",   dest="from_date", default=None,
                        help="Backtest từ ngày (ISO: 2025-01-01)")
    parser.add_argument("--to",     dest="to_date",   default=None,
                        help="Backtest đến ngày (ISO: 2025-12-31)")
    parser.add_argument("--balance", default=None, type=float,
                        help="Initial balance cho backtest (default: 10000 single / 5000 multi)")
    parser.add_argument("--news-filter", action="store_true")
    args = parser.parse_args()

    logger.info(
        f"MT5 Scalper | mode={args.mode} | "
        f"OS={'Windows' if IS_WINDOWS else 'Mac/Linux'} | DATA_SOURCE={DATA_SOURCE}"
    )

    if args.mode == "download":
        extra = [s.strip() for s in args.symbol.split(",") if s.strip() not in SYMBOLS] \
                if args.symbol != ",".join(SYMBOLS) else []
        asyncio.run(run_download(extra_symbols=extra or None))

    elif args.mode == "backtest":
        limit   = args.limit if args.limit != 2000 else 210_000
        symbols = [s.strip() for s in args.symbol.split(",")]
        if len(symbols) > 1:
            bal = args.balance if args.balance is not None else 5_000.0
            asyncio.run(run_backtest_multi(symbols, args.tf, limit=limit, offset=args.offset,
                                           from_date=args.from_date, to_date=args.to_date,
                                           initial_balance=bal))
        else:
            bal = args.balance if args.balance is not None else 10_000.0
            asyncio.run(run_backtest(symbols[0], args.tf, limit=limit, offset=args.offset,
                                     use_news_filter=args.news_filter,
                                     from_date=args.from_date, to_date=args.to_date,
                                     initial_balance=bal))

    elif args.mode == "paper":
        asyncio.run(run_paper())

    elif args.mode == "live":
        asyncio.run(run_live())

    elif args.mode == "debug":
        asyncio.run(run_debug(args.symbol, args.tf, args.limit))


if __name__ == "__main__":
    main()
