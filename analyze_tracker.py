"""
Phân tích candle_tracker_backtest từ DB — xuất CSV chi tiết.
Dữ liệu đã được save từ lần chạy backtest trước, không cần chạy lại.

Usage:
    source .venv/bin/activate
    python analyze_tracker.py --symbol EURUSD --tf 15m
"""
import asyncio
import argparse
import csv
from pathlib import Path
from datetime import datetime


async def main(symbol: str, tf: str):
    from dotenv import load_dotenv
    load_dotenv()

    import asyncpg
    from config.settings import DATABASE_URL

    print(f"[INFO] Kết nối DB: {symbol} {tf} ...")
    conn = await asyncpg.connect(DATABASE_URL)

    # ── Query toàn bộ tracker records ─────────────────────────────────────
    rows = await conn.fetch("""
        SELECT
            candle_time, side, trend, mtf_bias,
            zone_type, zone_low, zone_high,
            l1_trend, l2_zone_touch, l3_liquidity, l4_volume, l5_trigger, l6_risk,
            eligible,
            order_type, order_placed, stop_reason,
            entry_price, sl, tp1, rr,
            trade_closed, exit_price, exit_reason, pnl
        FROM candle_tracker_backtest
        WHERE symbol = $1 AND timeframe = $2
        ORDER BY candle_time ASC, side ASC
    """, symbol, tf)

    await conn.close()
    print(f"[INFO] Loaded {len(rows)} records từ DB")

    if not rows:
        print("[ERROR] Không có dữ liệu. Chạy backtest trước.")
        return

    # ── Thống kê ──────────────────────────────────────────────────────────
    total          = len(rows)
    eligible       = [r for r in rows if r["eligible"]]
    market_placed  = [r for r in rows if r["order_type"] == "MARKET" and r["order_placed"]]
    limit_pending  = [r for r in rows if r["order_type"] == "LIMIT"]
    limit_filled   = [r for r in rows if r["order_type"] == "LMT_FILL"]
    all_filled     = [r for r in rows if r["order_placed"]]
    trades_closed  = [r for r in rows if r["trade_closed"]]

    # Cancel reasons (tên ngắn ≤10 ký tự cho VARCHAR(10) DB column)
    c_structure = [r for r in rows if r["stop_reason"] == "struct_break"]
    c_ob        = [r for r in rows if r["stop_reason"] == "ob_invalid"]
    c_timeout   = [r for r in rows if r["stop_reason"] == "lmt_timeout"]
    c_eob       = [r for r in rows if r["stop_reason"] in ("lmt_eob", "limit_expired_eob")]
    c_already   = [r for r in rows if r["stop_reason"] == "lmt_already_pending"]

    # Trade outcomes
    tp_trades   = [r for r in trades_closed if r["exit_reason"] == "TP"]
    sl_trades   = [r for r in trades_closed if r["exit_reason"] == "SL"]
    be_trades   = [r for r in trades_closed if r["exit_reason"] == "BE"]

    pnl_list    = [r["pnl"] for r in trades_closed if r["pnl"] is not None]
    total_pnl   = sum(pnl_list)
    wins        = [p for p in pnl_list if p > 0]
    losses      = [p for p in pnl_list if p <= 0]
    winrate     = len(wins) / len(pnl_list) if pnl_list else 0

    # Stop reason breakdown (tất cả lý do)
    from collections import Counter
    stop_reasons = Counter(r["stop_reason"] for r in rows if r["stop_reason"])

    # ── In summary ────────────────────────────────────────────────────────
    sep = "═" * 58
    print(f"\n{sep}")
    print(f"  TRACKER ANALYSIS — {symbol} {tf}")
    print(f"  Records trong DB: {total:,}")
    print(f"{sep}")
    print(f"  {'Tổng signals xử lý':<40}: {total:,}")
    print(f"  {'Signals đủ điều kiện (eligible)':<40}: {len(eligible):,}")
    print(f"")
    print(f"  ── Phân loại lệnh ──────────────────────────────")
    print(f"  {'MARKET (khớp ngay)':<40}: {len(market_placed):,}")
    print(f"  {'LIMIT (đặt chờ — pending)':<40}: {len(limit_pending):,}")
    print(f"  {'LIMIT (đã khớp lệnh)':<40}: {len(limit_filled):,}")
    print(f"  {'Tổng lệnh khớp (MARKET + LIMIT filled)':<40}: {len(all_filled):,}")
    print(f"")
    print(f"  ── Lý do hủy LIMIT ──────────────────────────────")
    print(f"  {'  structure_broken':<40}: {len(c_structure):,}")
    print(f"  {'  ob_invalidated':<40}: {len(c_ob):,}")
    print(f"  {'  limit_timeout (safety fallback)':<40}: {len(c_timeout):,}")
    print(f"  {'  limit_expired_eob':<40}: {len(c_eob):,}")
    print(f"  {'  lmt_already_pending (2nd LIMIT skip)':<40}: {len(c_already):,}")
    print(f"")
    print(f"  ── Lý do bị lọc (tất cả stop_reason) ──────────")
    for reason, cnt in stop_reasons.most_common(10):
        print(f"  {'  ' + reason:<40}: {cnt:,}")
    print(f"")
    print(f"  ── Kết quả trades ───────────────────────────────")
    print(f"  {'Tổng trades đã đóng':<40}: {len(trades_closed):,}")
    print(f"  {'TP / SL / BE':<40}: {len(tp_trades)} / {len(sl_trades)} / {len(be_trades)}")
    print(f"  {'Winrate':<40}: {winrate:.1%}")
    print(f"  {'Net PnL':<40}: {total_pnl:+.2f} USD")
    print(f"  {'Avg win':<40}: {sum(wins)/len(wins):+.2f}" if wins else "  Avg win: N/A")
    print(f"  {'Avg loss':<40}: {sum(losses)/len(losses):+.2f}" if losses else "  Avg loss: N/A")
    print(f"{sep}\n")

    # ── Xuất CSV ──────────────────────────────────────────────────────────
    out_dir  = Path(__file__).parent
    csv_file = out_dir / f"backtest_detail_{symbol}_{tf}.csv"

    fieldnames = [
        "candle_time", "side",
        "l1_trend", "l2_zone_touch", "l3_liquidity", "l4_volume", "l5_trigger", "l6_risk",
        "eligible",
        "zone_type", "zone_low", "zone_high",
        "order_type", "order_placed", "stop_reason",
        "entry_price", "sl", "tp1", "rr",
        "trade_closed", "exit_price", "exit_reason", "pnl",
        "trend", "mtf_bias",
    ]

    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] for k in fieldnames})

    print(f"[OK] CSV chi tiết: {csv_file}")
    print(f"     {len(rows):,} rows — mở bằng Excel để lọc theo order_type, stop_reason, pnl\n")

    # ── Xuất CSV tóm tắt theo tháng ───────────────────────────────────────
    monthly_file = out_dir / f"backtest_monthly_{symbol}_{tf}.csv"
    from collections import defaultdict

    monthly: dict = defaultdict(lambda: {
        "trades": 0, "tp": 0, "sl": 0, "be": 0,
        "market": 0, "limit_placed": 0, "limit_filled": 0,
        "pnl": 0.0
    })
    for r in trades_closed:
        if r["candle_time"]:
            m = r["candle_time"].strftime("%Y-%m")
            monthly[m]["trades"]  += 1
            monthly[m]["pnl"]     += r["pnl"] or 0
            if r["exit_reason"] == "TP": monthly[m]["tp"] += 1
            if r["exit_reason"] == "SL": monthly[m]["sl"] += 1
            if r["exit_reason"] == "BE": monthly[m]["be"] += 1
    for r in market_placed:
        if r["candle_time"]:
            m = r["candle_time"].strftime("%Y-%m")
            monthly[m]["market"] += 1
    for r in limit_pending:
        if r["candle_time"]:
            m = r["candle_time"].strftime("%Y-%m")
            monthly[m]["limit_placed"] += 1
    for r in limit_filled:
        if r["candle_time"]:
            m = r["candle_time"].strftime("%Y-%m")
            monthly[m]["limit_filled"] += 1

    with open(monthly_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "month", "trades", "tp", "sl", "be",
            "market", "limit_placed", "limit_filled", "pnl"
        ])
        writer.writeheader()
        for m in sorted(monthly.keys()):
            d = monthly[m]
            writer.writerow({"month": m, **d, "pnl": round(d["pnl"], 2)})

    print(f"[OK] Tóm tắt theo tháng: {monthly_file}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--tf",     default="15m")
    args = parser.parse_args()
    asyncio.run(main(args.symbol, args.tf))
