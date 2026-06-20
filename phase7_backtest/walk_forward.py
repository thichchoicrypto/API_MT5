"""
Phase 7.12–7.13 — Walk-Forward + Out-of-Sample Testing.
"""
from typing import List, Dict
from utils.logger import logger


def walk_forward_test(candles: List[dict], symbol: str, timeframe: str,
                      train_ratio: float = 0.7,
                      n_folds: int = 3,
                      initial_balance: float = 10_000.0,
                      candles_15m: List[dict] = None,
                      candles_1h: List[dict] = None) -> Dict:
    """
    Phase 7.12: Split candles into train/test windows and run backtest on each.
    Passes MTF candles (15m, 1h) to each fold engine for proper multi-timeframe analysis.
    """
    from phase7_backtest.backtest_engine import BacktestEngine
    from datetime import timezone

    total = len(candles)
    fold_size = total // n_folds
    results = []

    for fold in range(n_folds):
        start = fold * fold_size
        end = start + fold_size
        fold_data = candles[start:end]

        train_end = int(len(fold_data) * train_ratio)
        train = fold_data[:train_end]
        test = fold_data[train_end:]

        if len(test) < 50:
            continue

        logger.info(f"Walk-forward fold {fold+1}/{n_folds}: train={len(train)}, test={len(test)}")

        # Slice MTF candles to match this fold's time range
        fold_start_time = fold_data[0]["open_time"]
        fold_end_time   = fold_data[-1]["open_time"]

        fold_15m = [c for c in (candles_15m or [])
                    if fold_start_time <= c["open_time"] <= fold_end_time]
        fold_1h  = [c for c in (candles_1h or [])
                    if fold_start_time <= c["open_time"] <= fold_end_time]

        engine = BacktestEngine(symbol, timeframe, initial_balance,
                                candles_15m=fold_15m, candles_1h=fold_1h)
        combined = train + test
        metrics = engine.run(combined, warmup=len(train))
        metrics["fold"] = fold + 1
        results.append(metrics)

    if not results:
        return {"error": "insufficient data"}

    # Aggregate
    import numpy as np
    avg_metrics = {
        "folds": results,
        "avg_winrate": round(float(np.mean([r["winrate"] for r in results])), 4),
        "avg_profit_factor": round(float(np.mean([r["profit_factor"] for r in results])), 2),
        "avg_max_dd": round(float(np.mean([r["max_drawdown_pct"] for r in results])), 4),
        "avg_net_profit_pct": round(float(np.mean([r["net_profit_pct"] for r in results])), 4),
        "consistent": all(r["profit_factor"] > 1.0 for r in results),
    }
    return avg_metrics
