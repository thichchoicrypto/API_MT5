(venv) PS C:\Projects\API_MT5> python main.py backtest
2026-06-20 19:56:40 | INFO     | __main__ - MT5 Scalper | mode=backtest | OS=Windows | DATA_SOURCE=MT5
2026-06-20 19:56:40 | INFO     | phase1_data.database - Database connected and schema ensured
2026-06-20 19:56:40 | INFO     | phase7_backtest.backtest_engine - Backtest started: EURUSD 15m — 48340 candles
2026-06-20 19:58:23 | WARNING  | phase6_risk.risk_engine - Max drawdown 17.3% hit — disabling trading
2026-06-20 19:58:26 | INFO     | __main__ - Saving 92337 tracker records for EURUSD ...
2026-06-20 20:04:20 | INFO     | phase1_data.database - Saved 92337 candle_tracker_backtest records

══════════════════════════════════════════════════
  EURUSD 15m
══════════════════════════════════════════════════
  total_trades             : 158
  winrate                  : 0.3924
  net_profit               : 5500.81
  net_profit_pct           : 1.1002
  profit_factor            : 1.37
  max_drawdown             : 2191.36
  max_drawdown_pct         : 0.1727
  avg_R                    : 2.13
  sharpe_ratio             : 2.01
  tp_count                 : 62
  sl_count                 : 54
  be_count                 : 42
  avg_win                  : 326.82
  avg_loss                 : -153.77
  PASSED                   : ❌ NO
2026-06-20 20:04:20 | INFO     | phase7_backtest.backtest_engine - Backtest started: GBPUSD 15m — 48335 candles
2026-06-20 20:04:55 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-517.25) — disabling trading
2026-06-20 20:04:57 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-493.87) — disabling trading
2026-06-20 20:04:57 | WARNING  | phase6_risk.risk_engine - Max drawdown 16.7% hit — disabling trading
2026-06-20 20:05:42 | INFO     | __main__ - Saving 31425 tracker records for GBPUSD ...
2026-06-20 20:07:34 | INFO     | phase1_data.database - Saved 31425 candle_tracker_backtest records

══════════════════════════════════════════════════
  GBPUSD 15m
══════════════════════════════════════════════════
  total_trades             : 72
  winrate                  : 0.3889
  net_profit               : 1838.22
  net_profit_pct           : 0.3676
  profit_factor            : 1.33
  max_drawdown             : 1374.74
  max_drawdown_pct         : 0.1674
  avg_R                    : 2.09
  sharpe_ratio             : 1.85
  tp_count                 : 28
  sl_count                 : 26
  be_count                 : 18
  avg_win                  : 264.94
  avg_loss                 : -126.82
  PASSED                   : ❌ NO
2026-06-20 20:07:34 | INFO     | phase7_backtest.backtest_engine - Backtest started: USDJPY 15m — 48335 candles
2026-06-20 20:07:35 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-325.21) — disabling trading
2026-06-20 20:07:45 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-527.95) — disabling trading
2026-06-20 20:08:03 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-1042.61) — disabling trading
2026-06-20 20:08:05 | WARNING  | phase6_risk.risk_engine - Max drawdown 15.6% hit — disabling trading
2026-06-20 20:08:51 | INFO     | __main__ - Saving 25955 tracker records for USDJPY ...
2026-06-20 20:10:21 | INFO     | phase1_data.database - Saved 25955 candle_tracker_backtest records

══════════════════════════════════════════════════
  USDJPY 15m
══════════════════════════════════════════════════
  total_trades             : 115
  winrate                  : 0.4174
  net_profit               : 9256.73
  net_profit_pct           : 1.8513
  profit_factor            : 1.79
  max_drawdown             : 2639.98
  max_drawdown_pct         : 0.1562
  avg_R                    : 2.5
  sharpe_ratio             : 3.59
  tp_count                 : 48
  sl_count                 : 35
  be_count                 : 32
  avg_win                  : 436.55
  avg_loss                 : -174.59
  PASSED                   : ✅ YES
2026-06-20 20:10:21 | INFO     | phase7_backtest.backtest_engine - Backtest started: XAUUSD 15m — 45962 candles
2026-06-20 20:10:23 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-347.29) — disabling trading
2026-06-20 20:11:21 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-845.37) — disabling trading
2026-06-20 20:12:04 | INFO     | __main__ - Saving 89056 tracker records for XAUUSD ...
2026-06-20 20:18:11 | INFO     | phase1_data.database - Saved 89056 candle_tracker_backtest records

══════════════════════════════════════════════════
  XAUUSD 15m
══════════════════════════════════════════════════
  total_trades             : 133
  winrate                  : 0.4286
  net_profit               : 14081.58
  net_profit_pct           : 2.8163
  profit_factor            : 2.11
  max_drawdown             : 1101.94
  max_drawdown_pct         : 0.0577
  avg_R                    : 2.81
  sharpe_ratio             : 4.52
  tp_count                 : 57
  sl_count                 : 43
  be_count                 : 33
  avg_win                  : 469.91
  avg_loss                 : -167.15
  PASSED                   : ✅ YES
2026-06-20 20:18:12 | INFO     | phase7_backtest.backtest_engine - Backtest started: USDCAD 15m — 35543 candles
2026-06-20 20:19:20 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-514.99) — disabling trading
2026-06-20 20:19:22 | WARNING  | phase6_risk.risk_engine - Max drawdown 15.0% hit — disabling trading
2026-06-20 20:19:43 | INFO     | __main__ - Saving 45617 tracker records for USDCAD ...
2026-06-20 20:22:28 | INFO     | phase1_data.database - Saved 45617 candle_tracker_backtest records

══════════════════════════════════════════════════
  USDCAD 15m
══════════════════════════════════════════════════
  total_trades             : 79
  winrate                  : 0.3544
  net_profit               : 1659.2
  net_profit_pct           : 0.3318
  profit_factor            : 1.29
  max_drawdown             : 1177.56
  max_drawdown_pct         : 0.1503
  avg_R                    : 2.35
  sharpe_ratio             : 1.65
  tp_count                 : 28
  sl_count                 : 29
  be_count                 : 22
  avg_win                  : 265.0
  avg_loss                 : -112.96
  PASSED                   : ❌ NO
2026-06-20 20:22:29 | INFO     | phase7_backtest.backtest_engine - Backtest started: AUDUSD 15m — 48342 candles
2026-06-20 20:25:06 | WARNING  | phase6_risk.risk_engine - Max drawdown 15.1% hit — disabling trading
2026-06-20 20:25:18 | INFO     | __main__ - Saving 83654 tracker records for AUDUSD ...
2026-06-20 20:32:33 | INFO     | phase1_data.database - Saved 83654 candle_tracker_backtest records

══════════════════════════════════════════════════
  AUDUSD 15m
══════════════════════════════════════════════════
  total_trades             : 105
  winrate                  : 0.4381
  net_profit               : 9497.4
  net_profit_pct           : 1.8995
  profit_factor            : 1.69
  max_drawdown             : 2581.46
  max_drawdown_pct         : 0.1511
  avg_R                    : 2.17
  sharpe_ratio             : 3.45
  tp_count                 : 46
  sl_count                 : 36
  be_count                 : 23
  avg_win                  : 504.63
  avg_loss                 : -232.46
  PASSED                   : ✅ YES
2026-06-20 20:32:34 | INFO     | phase7_backtest.backtest_engine - Backtest started: EURJPY 15m — 48335 candles
2026-06-20 20:32:37 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-320.87) — disabling trading
2026-06-20 20:34:25 | WARNING  | phase6_risk.risk_engine - Max drawdown 16.7% hit — disabling trading
2026-06-20 20:34:51 | INFO     | __main__ - Saving 71715 tracker records for EURJPY ...
2026-06-20 20:39:56 | INFO     | phase1_data.database - Saved 71715 candle_tracker_backtest records

══════════════════════════════════════════════════
  EURJPY 15m
══════════════════════════════════════════════════
  total_trades             : 107
  winrate                  : 0.4579
  net_profit               : 9609.07
  net_profit_pct           : 1.9218
  profit_factor            : 2.0
  max_drawdown             : 2919.23
  max_drawdown_pct         : 0.1665
  avg_R                    : 2.37
  sharpe_ratio             : 4.23
  tp_count                 : 49
  sl_count                 : 30
  be_count                 : 28
  avg_win                  : 391.68
  avg_loss                 : -165.22
  PASSED                   : ✅ YES
2026-06-20 20:39:56 | INFO     | phase1_data.database - Database disconnected

══════════════════════════════════════════════════
  COMBINED (EURUSD + GBPUSD + USDJPY + XAUUSD + USDCAD + AUDUSD + EURJPY) — vốn $5,000
══════════════════════════════════════════════════
  total_trades             : 769
  avg_winrate              : 0.4111
  net_profit               : +51443.01  (+1028.9%)
  tp / sl / be             : 318 / 253 / 198
  final_balance            : $56,443.01
══════════════════════════════════════════════════





24/06/2026


(.venv) ngocdang@MacBook-Pro API_MT5 % python3 main.py backtest --symbol XAUUSD --tf 15m
python3 analyze_tracker.py --symbol XAUUSD --tf 15m
2026-06-24 00:02:24 | INFO     | __main__ - MT5 Scalper | mode=backtest | OS=Mac/Linux | DATA_SOURCE=YFINANCE
2026-06-24 00:02:24 | INFO     | phase1_data.database - Database connected and schema ensured
2026-06-24 00:02:24 | INFO     | __main__ - Loading candles for XAUUSD 15m ...
2026-06-24 00:02:24 | INFO     | __main__ - Running backtest on 45962 candles (2024-06-21 → 2026-06-19)
2026-06-24 00:02:24 | INFO     | __main__ - candle_tracker_backtest truncated ✅
2026-06-24 00:02:24 | INFO     | phase7_backtest.backtest_engine - Backtest started: XAUUSD 15m — 45962 candles
2026-06-24 00:02:27 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-754.93) — disabling trading
2026-06-24 00:02:30 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-778.56) — disabling trading
2026-06-24 00:02:36 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-1037.85) — disabling trading
2026-06-24 00:02:40 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-1067.55) — disabling trading
2026-06-24 00:02:47 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-2171.14) — disabling trading
2026-06-24 00:02:49 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-1793.99) — disabling trading
2026-06-24 00:02:50 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-1912.53) — disabling trading
2026-06-24 00:03:04 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-5069.37) — disabling trading
2026-06-24 00:03:13 | INFO     | __main__ - Saving 84555 candle_tracker records ...
2026-06-24 00:03:38 | INFO     | phase1_data.database - Saved 84555 candle_tracker_backtest records
2026-06-24 00:03:38 | INFO     | __main__ - candle_tracker saved ✅
2026-06-24 00:03:38 | INFO     | phase1_data.database - Database disconnected
══════════════════════════════════════════════════
  BACKTEST RESULTS — XAUUSD 15m
  Period: 2024-06-21 → 2026-06-19
══════════════════════════════════════════════════
  total_trades             : 702
  winrate                  : 0.5171
  net_profit               : 104011.71
  net_profit_pct           : 10.4012
  profit_factor            : 1.5
  max_drawdown             : 13252.89
  max_drawdown_pct         : 0.1162
  avg_R                    : 1.4
  sharpe_ratio             : 2.44
  tp_count                 : 366
  sl_count                 : 281
  be_count                 : 55
  avg_win                  : 858.15
  avg_loss                 : -612.08
  PASSED                   : ✅ YES
══════════════════════════════════════════════════
  ── Quarterly Breakdown ──────────────────────────────
  Quarter     Trades   Win%        P&L    Balance     DD%
  ───────────────────────────────────────────────────────
  2024-Q2         11    55%      +302      10302    2.2%  📈
  2024-Q3        108    51%     +1816      12118   20.4%  📈
  2024-Q4        101    49%     +3128      15247   20.3%  📈
  2025-Q1         89    49%     +3916      19163    8.4%  📈
  2025-Q2         85    53%    +10741      29904   19.7%  📈
  2025-Q3         97    46%     +4897      34800   12.5%  📈
  2025-Q4         70    61%    +30216      65017    4.1%  📈
  2026-Q1         77    52%    +14614      79631   14.1%  📈
  2026-Q2         64    56%    +34381     114012    0.0%  📈
  ───────────────────────────────────────────────────────
  TOTAL          702          +104012     114012
2026-06-24 00:03:38 | INFO     | __main__ - Running walk-forward validation ...
2026-06-24 00:03:38 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 1/3: train=10724, test=4596
2026-06-24 00:03:38 | INFO     | phase7_backtest.backtest_engine - Backtest started: XAUUSD 15m — 15320 candles
2026-06-24 00:03:41 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-609.64) — disabling trading
2026-06-24 00:03:44 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 2/3: train=10724, test=4596
2026-06-24 00:03:44 | INFO     | phase7_backtest.backtest_engine - Backtest started: XAUUSD 15m — 15320 candles
2026-06-24 00:03:50 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 3/3: train=10724, test=4596
2026-06-24 00:03:50 | INFO     | phase7_backtest.backtest_engine - Backtest started: XAUUSD 15m — 15320 candles
  Walk-Forward:
    avg_winrate: 0.5137
    avg_profit_factor: 1.62
    avg_max_dd: 0.1559
    avg_net_profit_pct: 0.3132
    consistent: False
  Monte Carlo (1000 simulations):
    median_final_balance: 114011.71
    p5_final_balance: 114011.71
    p95_final_balance: 114011.71
    median_max_dd: 0.3661
    p95_max_dd: 0.8973
    ruin_probability: 0.0
[INFO] Kết nối DB: XAUUSD 15m ...
[INFO] Loaded 84555 records từ DB
══════════════════════════════════════════════════════════
  TRACKER ANALYSIS — XAUUSD 15m
  Records trong DB: 84,555
══════════════════════════════════════════════════════════
  Tổng signals xử lý                      : 84,555
  Signals đủ điều kiện (eligible)         : 907
  ── Phân loại lệnh ──────────────────────────────
  MARKET (khớp ngay)                      : 299
  LIMIT (đặt chờ — pending)               : 205
  LIMIT (đã khớp lệnh)                    : 403
  Tổng lệnh khớp (MARKET + LIMIT filled)  : 702
  ── Lý do hủy LIMIT ──────────────────────────────
    structure_broken                      : 0
    ob_invalidated                        : 0
    limit_timeout (safety fallback)       : 205
    limit_expired_eob                     : 0
    lmt_already_pending (2nd LIMIT skip)  : 19
  ── Lý do bị lọc (tất cả stop_reason) ──────────
    l1_trend_fail                         : 15,482
    no_zone                               : 13,839
    l2_zone_fail                          : 9,046
    risk_rejected                         : 4,052
    adx_low_14                            : 2,947
    adx_low_15                            : 2,811
    adx_low_12                            : 2,715
    adx_low_17                            : 2,640
    adx_low_18                            : 2,618
    adx_low_16                            : 2,607
  ── Kết quả trades ───────────────────────────────
  Tổng trades đã đóng                     : 702
  TP / SL / BE                            : 366 / 281 / 55
  Winrate                                 : 51.7%
  Net PnL                                 : +104011.71 USD
  Avg win                                 : +858.15
  Avg loss                                : -612.08
══════════════════════════════════════════════════════════
[OK] CSV chi tiết: /Users/ngocdang/Claude/Projects/API_MT5/backtest_detail_XAUUSD_15m.csv
     84,555 rows — mở bằng Excel để lọc theo order_type, stop_reason, pnl
[OK] Tóm tắt theo tháng: /Users/ngocdang/Claude/Projects/API_MT5/backtest_monthly_XAUUSD_15m.csv
(.venv) ngocdang@MacBook-Pro API_MT5 %