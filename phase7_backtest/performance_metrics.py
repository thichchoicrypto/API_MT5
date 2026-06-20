"""
Phase 7.10 + 7.14 — Performance Metrics + Monte Carlo Simulation.
"""
import random
import numpy as np
from typing import List, Dict


def compute_metrics(trades: list, initial_balance: float, equity_curve: List[Dict]) -> Dict:
    """Phase 7.10: Comprehensive performance metrics."""
    if not trades:
        return _empty_metrics(initial_balance)

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    total_trades = len(pnls)
    winrate = len(wins) / total_trades if total_trades > 0 else 0
    net_profit = sum(pnls)
    net_profit_pct = net_profit / initial_balance

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    avg_r = avg_win / abs(avg_loss) if avg_loss != 0 else 0

    # Equity-based metrics
    balances = [e["balance"] for e in equity_curve]
    max_dd, max_dd_pct = _calc_max_drawdown(balances, initial_balance)
    sharpe = _calc_sharpe(pnls)

    # Status breakdown
    tp_count = sum(1 for t in trades if t.status == "TP")
    sl_count = sum(1 for t in trades if t.status == "SL")
    be_count = sum(1 for t in trades if t.status == "BE")

    result = {
        "total_trades": total_trades,
        "winrate": round(winrate, 4),
        "net_profit": round(net_profit, 2),
        "net_profit_pct": round(net_profit_pct, 4),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "avg_R": round(avg_r, 2),
        "sharpe_ratio": round(sharpe, 2),
        "tp_count": tp_count,
        "sl_count": sl_count,
        "be_count": be_count,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "passed": _check_acceptance(profit_factor, max_dd_pct, winrate),
    }
    return result


def _calc_max_drawdown(balances: List[float], initial: float) -> tuple:
    if not balances:
        return 0.0, 0.0
    peak = initial
    max_dd = 0.0
    for b in balances:
        if b > peak:
            peak = b
        dd = peak - b
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = max_dd / peak if peak > 0 else 0
    return max_dd, max_dd_pct


def _calc_sharpe(pnls: List[float], risk_free: float = 0.0) -> float:
    if len(pnls) < 2:
        return 0.0
    arr = np.array(pnls)
    mean = arr.mean() - risk_free
    std = arr.std()
    return float(mean / std * np.sqrt(252)) if std > 0 else 0.0


def _check_acceptance(pf: float, max_dd_pct: float, winrate: float) -> bool:
    """Phase 7.19: Acceptance criteria."""
    return pf > 1.5 and max_dd_pct < 0.20


def _empty_metrics(initial_balance: float) -> Dict:
    return {
        "total_trades": 0, "winrate": 0, "net_profit": 0,
        "net_profit_pct": 0, "profit_factor": 0,
        "max_drawdown": 0, "max_drawdown_pct": 0,
        "avg_R": 0, "sharpe_ratio": 0, "passed": False,
    }


# ─────────────────────────────────────────────────────────
# Monte Carlo (Phase 7.14)
# ─────────────────────────────────────────────────────────
def monte_carlo_simulation(trade_pnls: List[float],
                            initial_balance: float,
                            simulations: int = 1000) -> Dict:
    """
    Shuffle trade sequence and re-compute equity N times.
    Returns distribution of outcomes.
    """
    final_balances = []
    max_drawdowns = []

    for _ in range(simulations):
        shuffled = random.sample(trade_pnls, len(trade_pnls))
        balance = initial_balance
        peak = initial_balance
        max_dd = 0.0
        for pnl in shuffled:
            balance += pnl
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        final_balances.append(balance)
        max_drawdowns.append(max_dd)

    fb = np.array(final_balances)
    mdd = np.array(max_drawdowns)

    return {
        "median_final_balance": round(float(np.median(fb)), 2),
        "p5_final_balance": round(float(np.percentile(fb, 5)), 2),
        "p95_final_balance": round(float(np.percentile(fb, 95)), 2),
        "median_max_dd": round(float(np.median(mdd)), 4),
        "p95_max_dd": round(float(np.percentile(mdd, 95)), 4),
        "ruin_probability": round(float(np.mean(fb < initial_balance * 0.5)), 4),
    }
