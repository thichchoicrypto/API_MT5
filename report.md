(.venv) ngocdang@MacBook-Pro API_MT5 % python3 main.py backtest --symbol AUDUSD --tf 15m
python3 main.py backtest --symbol NZDUSD --tf 15m
python3 main.py backtest --symbol USDCAD --tf 15m
python3 main.py backtest --symbol USDCHF --tf 15m
python3 main.py backtest --symbol EURJPY --tf 15m
python3 main.py backtest --symbol GBPJPY --tf 15m
python3 main.py backtest --symbol XAUUSD --tf 1h
2026-06-24 13:25:35 | INFO     | __main__ - MT5 Scalper | mode=backtest | OS=Mac/Linux | DATA_SOURCE=YFINANCE
2026-06-24 13:25:36 | INFO     | phase1_data.database - Database connected and schema ensured
2026-06-24 13:25:36 | INFO     | __main__ - Loading candles for AUDUSD 15m ...
2026-06-24 13:25:36 | INFO     | __main__ - Running backtest on 48342 candles (2024-06-21 → 2026-06-19)
2026-06-24 13:25:36 | INFO     | __main__ - candle_tracker_backtest truncated ✅
2026-06-24 13:25:36 | INFO     | phase7_backtest.backtest_engine - Backtest started: AUDUSD 15m — 48342 candles
2026-06-24 13:26:05 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-904.02) — disabling trading
2026-06-24 13:26:27 | INFO     | __main__ - Saving 93320 candle_tracker records ...
2026-06-24 13:27:00 | INFO     | phase1_data.database - Saved 93320 candle_tracker_backtest records
2026-06-24 13:27:00 | INFO     | __main__ - candle_tracker saved ✅
2026-06-24 13:27:00 | INFO     | phase1_data.database - Database disconnected

══════════════════════════════════════════════════
  BACKTEST RESULTS — AUDUSD 15m
  Period: 2024-06-21 → 2026-06-19
══════════════════════════════════════════════════
  total_trades             : 303
  winrate                  : 0.462
  net_profit               : 2502.47
  net_profit_pct           : 0.2502
  profit_factor            : 1.07
  max_drawdown             : 4866.11
  max_drawdown_pct         : 0.3256
  avg_R                    : 1.25
  sharpe_ratio             : 0.52
  tp_count                 : 140
  sl_count                 : 144
  be_count                 : 18
  avg_win                  : 265.83
  avg_loss                 : -212.97
  PASSED                   : ❌ NO
══════════════════════════════════════════════════

  ── Quarterly Breakdown ──────────────────────────────
  Quarter     Trades   Win%        P&L    Balance     DD%
  ───────────────────────────────────────────────────────
  2024-Q2          3     0%      -653       9347    6.5%  📉
  2024-Q3         29    41%      -310       9037   16.0%  📉
  2024-Q4         40    45%      -806       8231   17.8%  📉
  2025-Q1         30    53%     +1313       9544    6.8%  📈
  2025-Q2         35    63%     +4316      13860    0.0%  📈
  2025-Q3         42    36%     -2765      11095   27.5%  📉
  2025-Q4         42    43%      -208      10887   14.2%  📉
  2026-Q1         38    47%     +1254      12141   10.5%  📈
  2026-Q2         44    48%      +393      12533    2.2%  📈
  ───────────────────────────────────────────────────────
  TOTAL          303            +2533      12533
2026-06-24 13:27:00 | INFO     | __main__ - Running walk-forward validation ...
2026-06-24 13:27:00 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 1/3: train=11279, test=4835
2026-06-24 13:27:00 | INFO     | phase7_backtest.backtest_engine - Backtest started: AUDUSD 15m — 16114 candles
2026-06-24 13:27:07 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 2/3: train=11279, test=4835
2026-06-24 13:27:07 | INFO     | phase7_backtest.backtest_engine - Backtest started: AUDUSD 15m — 16114 candles
2026-06-24 13:27:10 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-674.60) — disabling trading
2026-06-24 13:27:14 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 3/3: train=11279, test=4835
2026-06-24 13:27:14 | INFO     | phase7_backtest.backtest_engine - Backtest started: AUDUSD 15m — 16114 candles

  Walk-Forward:
    avg_winrate: 0.4102
    avg_profit_factor: 0.86
    avg_max_dd: 0.1851
    avg_net_profit_pct: -0.0657
    consistent: False

  Monte Carlo (1000 simulations):
    median_final_balance: 12502.47
    p5_final_balance: 12502.47
    p95_final_balance: 12502.47
    median_max_dd: 0.2917
    p95_max_dd: 0.4766
    ruin_probability: 0.0
2026-06-24 13:27:21 | INFO     | __main__ - MT5 Scalper | mode=backtest | OS=Mac/Linux | DATA_SOURCE=YFINANCE
2026-06-24 13:27:21 | INFO     | phase1_data.database - Database connected and schema ensured
2026-06-24 13:27:21 | INFO     | __main__ - Loading candles for NZDUSD 15m ...
2026-06-24 13:27:22 | INFO     | __main__ - Running backtest on 48283 candles (2024-06-21 → 2026-06-19)
2026-06-24 13:27:22 | INFO     | __main__ - candle_tracker_backtest truncated ✅
2026-06-24 13:27:22 | INFO     | phase7_backtest.backtest_engine - Backtest started: NZDUSD 15m — 48283 candles
2026-06-24 13:27:23 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-648.02) — disabling trading
2026-06-24 13:28:00 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-630.23) — disabling trading
2026-06-24 13:28:00 | WARNING  | phase6_risk.risk_engine - Max drawdown 36.4% hit — disabling trading
2026-06-24 13:28:08 | INFO     | __main__ - Saving 73048 candle_tracker records ...
2026-06-24 13:28:32 | INFO     | phase1_data.database - Saved 73048 candle_tracker_backtest records
2026-06-24 13:28:32 | INFO     | __main__ - candle_tracker saved ✅
2026-06-24 13:28:32 | INFO     | phase1_data.database - Database disconnected

══════════════════════════════════════════════════
  BACKTEST RESULTS — NZDUSD 15m
  Period: 2024-06-21 → 2026-06-19
══════════════════════════════════════════════════
  total_trades             : 248
  winrate                  : 0.4476
  net_profit               : -969.08
  net_profit_pct           : -0.0969
  profit_factor            : 0.97
  max_drawdown             : 5178.98
  max_drawdown_pct         : 0.3645
  avg_R                    : 1.2
  sharpe_ratio             : -0.24
  tp_count                 : 111
  sl_count                 : 126
  be_count                 : 11
  avg_win                  : 278.09
  avg_loss                 : -232.39
  PASSED                   : ❌ NO
══════════════════════════════════════════════════

  ── Quarterly Breakdown ──────────────────────────────
  Quarter     Trades   Win%        P&L    Balance     DD%
  ───────────────────────────────────────────────────────
  2024-Q2          1   100%      +224      10224    0.0%  📈
  2024-Q3         47    45%      +312      10537   13.3%  📈
  2024-Q4         44    50%      +616      11153    9.4%  📈
  2025-Q1         38    50%      +713      11865    6.3%  📈
  2025-Q2         33    55%     +2344      14210    0.0%  📈
  2025-Q3         38    39%     -1747      12463   12.6%  📉
  2025-Q4         39    33%     -2582       9881   24.7%  📉
  2026-Q1          8    25%      -850       9031   10.6%  📉
  ───────────────────────────────────────────────────────
  TOTAL          248             -969       9031
2026-06-24 13:28:32 | INFO     | __main__ - Running walk-forward validation ...
2026-06-24 13:28:32 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 1/3: train=11265, test=4829
2026-06-24 13:28:32 | INFO     | phase7_backtest.backtest_engine - Backtest started: NZDUSD 15m — 16094 candles
2026-06-24 13:28:38 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 2/3: train=11265, test=4829
2026-06-24 13:28:38 | INFO     | phase7_backtest.backtest_engine - Backtest started: NZDUSD 15m — 16094 candles
2026-06-24 13:28:45 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 3/3: train=11265, test=4829
2026-06-24 13:28:45 | INFO     | phase7_backtest.backtest_engine - Backtest started: NZDUSD 15m — 16094 candles

  Walk-Forward:
    avg_winrate: 0.4144
    avg_profit_factor: 0.82
    avg_max_dd: 0.139
    avg_net_profit_pct: -0.0686
    consistent: False

  Monte Carlo (1000 simulations):
    median_final_balance: 9030.92
    p5_final_balance: 9030.92
    p95_final_balance: 9030.92
    median_max_dd: 0.3989
    p95_max_dd: 0.5766
    ruin_probability: 0.0
2026-06-24 13:28:52 | INFO     | __main__ - MT5 Scalper | mode=backtest | OS=Mac/Linux | DATA_SOURCE=YFINANCE
2026-06-24 13:28:52 | INFO     | phase1_data.database - Database connected and schema ensured
2026-06-24 13:28:52 | INFO     | __main__ - Loading candles for USDCAD 15m ...
2026-06-24 13:28:52 | INFO     | __main__ - Running backtest on 35543 candles (2025-01-02 → 2026-06-19)
2026-06-24 13:28:52 | INFO     | __main__ - candle_tracker_backtest truncated ✅
2026-06-24 13:28:52 | INFO     | phase7_backtest.backtest_engine - Backtest started: USDCAD 15m — 35543 candles
2026-06-24 13:29:32 | INFO     | __main__ - Saving 68323 candle_tracker records ...
2026-06-24 13:29:53 | INFO     | phase1_data.database - Saved 68323 candle_tracker_backtest records
2026-06-24 13:29:53 | INFO     | __main__ - candle_tracker saved ✅
2026-06-24 13:29:53 | INFO     | phase1_data.database - Database disconnected

══════════════════════════════════════════════════
  BACKTEST RESULTS — USDCAD 15m
  Period: 2025-01-02 → 2026-06-19
══════════════════════════════════════════════════
  total_trades             : 225
  winrate                  : 0.4711
  net_profit               : -600.37
  net_profit_pct           : -0.06
  profit_factor            : 0.97
  max_drawdown             : 3045.02
  max_drawdown_pct         : 0.2761
  avg_R                    : 1.09
  sharpe_ratio             : -0.2
  tp_count                 : 106
  sl_count                 : 109
  be_count                 : 10
  avg_win                  : 215.78
  avg_loss                 : -197.25
  PASSED                   : ❌ NO
══════════════════════════════════════════════════

  ── Quarterly Breakdown ──────────────────────────────
  Quarter     Trades   Win%        P&L    Balance     DD%
  ───────────────────────────────────────────────────────
  2025-Q1         40    45%      +280      10280    9.0%  📈
  2025-Q2         30    30%     -2167       8113   23.9%  📉
  2025-Q3         49    53%      +830       8943   10.0%  📈
  2025-Q4         40    57%     +1358      10301    4.4%  📈
  2026-Q1         33    42%      -990       9310   10.4%  📉
  2026-Q2         33    48%       +89       9400    7.5%  📈
  ───────────────────────────────────────────────────────
  TOTAL          225             -600       9400
2026-06-24 13:29:53 | INFO     | __main__ - Running walk-forward validation ...
2026-06-24 13:29:53 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 1/3: train=8292, test=3555
2026-06-24 13:29:53 | INFO     | phase7_backtest.backtest_engine - Backtest started: USDCAD 15m — 11847 candles
2026-06-24 13:29:58 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 2/3: train=8292, test=3555
2026-06-24 13:29:58 | INFO     | phase7_backtest.backtest_engine - Backtest started: USDCAD 15m — 11847 candles
2026-06-24 13:30:03 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 3/3: train=8292, test=3555
2026-06-24 13:30:03 | INFO     | phase7_backtest.backtest_engine - Backtest started: USDCAD 15m — 11847 candles

  Walk-Forward:
    avg_winrate: 0.4174
    avg_profit_factor: 0.82
    avg_max_dd: 0.1297
    avg_net_profit_pct: -0.0536
    consistent: False

  Monte Carlo (1000 simulations):
    median_final_balance: 9399.63
    p5_final_balance: 9399.63
    p95_final_balance: 9399.63
    median_max_dd: 0.3128
    p95_max_dd: 0.4588
    ruin_probability: 0.0
2026-06-24 13:30:09 | INFO     | __main__ - MT5 Scalper | mode=backtest | OS=Mac/Linux | DATA_SOURCE=YFINANCE
2026-06-24 13:30:09 | INFO     | phase1_data.database - Database connected and schema ensured
2026-06-24 13:30:09 | INFO     | __main__ - Loading candles for USDCHF 15m ...
2026-06-24 13:30:09 | INFO     | __main__ - Running backtest on 48285 candles (2024-06-21 → 2026-06-19)
2026-06-24 13:30:09 | INFO     | __main__ - candle_tracker_backtest truncated ✅
2026-06-24 13:30:09 | INFO     | phase7_backtest.backtest_engine - Backtest started: USDCHF 15m — 48285 candles
2026-06-24 13:30:10 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-695.79) — disabling trading
2026-06-24 13:30:10 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-911.96) — disabling trading
2026-06-24 13:30:12 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-555.39) — disabling trading
2026-06-24 13:30:43 | WARNING  | phase6_risk.risk_engine - Daily loss limit hit (-737.30) — disabling trading
2026-06-24 13:31:01 | INFO     | __main__ - Saving 92070 candle_tracker records ...
2026-06-24 13:31:29 | INFO     | phase1_data.database - Saved 92070 candle_tracker_backtest records
2026-06-24 13:31:29 | INFO     | __main__ - candle_tracker saved ✅
2026-06-24 13:31:29 | INFO     | phase1_data.database - Database disconnected

══════════════════════════════════════════════════
  BACKTEST RESULTS — USDCHF 15m
  Period: 2024-06-21 → 2026-06-19
══════════════════════════════════════════════════
  total_trades             : 357
  winrate                  : 0.4846
  net_profit               : 4468.23
  net_profit_pct           : 0.4468
  profit_factor            : 1.11
  max_drawdown             : 3076.06
  max_drawdown_pct         : 0.2017
  avg_R                    : 1.18
  sharpe_ratio             : 0.77
  tp_count                 : 173
  sl_count                 : 167
  be_count                 : 17
  avg_win                  : 266.93
  avg_loss                 : -226.69
  PASSED                   : ❌ NO
══════════════════════════════════════════════════

  ── Quarterly Breakdown ──────────────────────────────
  Quarter     Trades   Win%        P&L    Balance     DD%
  ───────────────────────────────────────────────────────
  2024-Q2          3    67%      +204      10204    2.3%  📈
  2024-Q3         63    41%     -1457       8747   23.8%  📉
  2024-Q4         46    57%     +2104      10851   12.4%  📈
  2025-Q1         46    50%     +1318      12169    8.5%  📈
  2025-Q2         26    31%     -2129      10040   17.7%  📉
  2025-Q3         39    56%     +1758      11798    6.6%  📈
  2025-Q4         63    49%      +458      12256    6.8%  📈
  2026-Q1         40    50%     +1743      14000    8.2%  📈
  2026-Q2         31    48%      +469      14468   14.3%  📈
  ───────────────────────────────────────────────────────
  TOTAL          357            +4468      14468
2026-06-24 13:31:29 | INFO     | __main__ - Running walk-forward validation ...
2026-06-24 13:31:29 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 1/3: train=11266, test=4829
2026-06-24 13:31:29 | INFO     | phase7_backtest.backtest_engine - Backtest started: USDCHF 15m — 16095 candles
2026-06-24 13:31:36 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 2/3: train=11266, test=4829
2026-06-24 13:31:36 | INFO     | phase7_backtest.backtest_engine - Backtest started: USDCHF 15m — 16095 candles
2026-06-24 13:31:43 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 3/3: train=11266, test=4829
2026-06-24 13:31:43 | INFO     | phase7_backtest.backtest_engine - Backtest started: USDCHF 15m — 16095 candles

  Walk-Forward:
    avg_winrate: 0.4681
    avg_profit_factor: 1.13
    avg_max_dd: 0.134
    avg_net_profit_pct: 0.0247
    consistent: False

  Monte Carlo (1000 simulations):
    median_final_balance: 14468.23
    p5_final_balance: 14468.23
    p95_final_balance: 14468.23
    median_max_dd: 0.2821
    p95_max_dd: 0.4601
    ruin_probability: 0.0
2026-06-24 13:31:50 | INFO     | __main__ - MT5 Scalper | mode=backtest | OS=Mac/Linux | DATA_SOURCE=YFINANCE
2026-06-24 13:31:50 | INFO     | phase1_data.database - Database connected and schema ensured
2026-06-24 13:31:50 | INFO     | __main__ - Loading candles for EURJPY 15m ...
2026-06-24 13:31:50 | INFO     | __main__ - Running backtest on 48335 candles (2024-06-21 → 2026-06-19)
2026-06-24 13:31:50 | INFO     | __main__ - candle_tracker_backtest truncated ✅
2026-06-24 13:31:50 | INFO     | phase7_backtest.backtest_engine - Backtest started: EURJPY 15m — 48335 candles
2026-06-24 13:32:43 | INFO     | __main__ - Saving 95992 candle_tracker records ...
2026-06-24 13:33:20 | INFO     | phase1_data.database - Saved 95992 candle_tracker_backtest records
2026-06-24 13:33:20 | INFO     | __main__ - candle_tracker saved ✅
2026-06-24 13:33:20 | INFO     | phase1_data.database - Database disconnected

══════════════════════════════════════════════════
  BACKTEST RESULTS — EURJPY 15m
  Period: 2024-06-21 → 2026-06-19
══════════════════════════════════════════════════
  total_trades             : 46
  winrate                  : 0.4348
  net_profit               : -506.17
  net_profit_pct           : -0.0506
  profit_factor            : 0.9
  max_drawdown             : 1515.24
  max_drawdown_pct         : 0.1459
  avg_R                    : 1.17
  sharpe_ratio             : -0.82
  tp_count                 : 20
  sl_count                 : 23
  be_count                 : 3
  avg_win                  : 223.47
  avg_loss                 : -191.37
  PASSED                   : ❌ NO
══════════════════════════════════════════════════

  ── Quarterly Breakdown ──────────────────────────────
  Quarter     Trades   Win%        P&L    Balance     DD%
  ───────────────────────────────────────────────────────
  2024-Q2          2   100%      +387      10387    0.0%  📈
  2024-Q3          5    20%      -694       9693    4.6%  📉
  2024-Q4          9    44%      -223       9470    8.5%  📉
  2025-Q1          1     0%       -11       9459    0.0%  📉
  2025-Q2          6    50%        +6       9465    6.6%  📈
  2025-Q3          1   100%      +163       9628    0.0%  📈
  2025-Q4          7    43%       +30       9658    4.3%  📈
  2026-Q1         11    36%      -177       9481   10.9%  📉
  2026-Q2          4    50%       +13       9494    0.0%  📈
  ───────────────────────────────────────────────────────
  TOTAL           46             -506       9494
2026-06-24 13:33:20 | INFO     | __main__ - Running walk-forward validation ...
2026-06-24 13:33:20 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 1/3: train=11277, test=4834
2026-06-24 13:33:20 | INFO     | phase7_backtest.backtest_engine - Backtest started: EURJPY 15m — 16111 candles
2026-06-24 13:33:27 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 2/3: train=11277, test=4834
2026-06-24 13:33:27 | INFO     | phase7_backtest.backtest_engine - Backtest started: EURJPY 15m — 16111 candles
2026-06-24 13:33:35 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 3/3: train=11277, test=4834
2026-06-24 13:33:35 | INFO     | phase7_backtest.backtest_engine - Backtest started: EURJPY 15m — 16111 candles

  Walk-Forward:
    avg_winrate: 0.3889
    avg_profit_factor: 1.05
    avg_max_dd: 0.0228
    avg_net_profit_pct: 0.001
    consistent: False

  Monte Carlo (1000 simulations):
    median_final_balance: 9493.83
    p5_final_balance: 9493.83
    p95_final_balance: 9493.83
    median_max_dd: 0.156
    p95_max_dd: 0.2201
    ruin_probability: 0.0
2026-06-24 13:33:42 | INFO     | __main__ - MT5 Scalper | mode=backtest | OS=Mac/Linux | DATA_SOURCE=YFINANCE
2026-06-24 13:33:43 | INFO     | phase1_data.database - Database connected and schema ensured
2026-06-24 13:33:43 | INFO     | __main__ - Loading candles for GBPJPY 15m ...
2026-06-24 13:33:43 | INFO     | __main__ - Running backtest on 48285 candles (2024-06-21 → 2026-06-19)
2026-06-24 13:33:43 | INFO     | __main__ - candle_tracker_backtest truncated ✅
2026-06-24 13:33:43 | INFO     | phase7_backtest.backtest_engine - Backtest started: GBPJPY 15m — 48285 candles
2026-06-24 13:34:37 | INFO     | __main__ - Saving 96033 candle_tracker records ...
2026-06-24 13:35:06 | INFO     | phase1_data.database - Saved 96033 candle_tracker_backtest records
2026-06-24 13:35:06 | INFO     | __main__ - candle_tracker saved ✅
2026-06-24 13:35:06 | INFO     | phase1_data.database - Database disconnected

══════════════════════════════════════════════════
  BACKTEST RESULTS — GBPJPY 15m
  Period: 2024-06-21 → 2026-06-19
══════════════════════════════════════════════════
  total_trades             : 36
  winrate                  : 0.4722
  net_profit               : 464.8
  net_profit_pct           : 0.0465
  profit_factor            : 1.13
  max_drawdown             : 1330.2
  max_drawdown_pct         : 0.1128
  avg_R                    : 1.26
  sharpe_ratio             : 0.89
  tp_count                 : 17
  sl_count                 : 15
  be_count                 : 4
  avg_win                  : 243.07
  avg_loss                 : -193.02
  PASSED                   : ❌ NO
══════════════════════════════════════════════════

  ── Quarterly Breakdown ──────────────────────────────
  Quarter     Trades   Win%        P&L    Balance     DD%
  ───────────────────────────────────────────────────────
  2024-Q2          1   100%      +248      10248    0.0%  📈
  2024-Q3          2    50%       +13      10261    2.1%  📈
  2024-Q4          9    33%      -395       9865   10.5%  📉
  2025-Q1          3    67%      +445      10311    0.2%  📈
  2025-Q2          2    50%      +233      10543    0.0%  📈
  2025-Q3          6    67%      +334      10877    0.0%  📈
  2025-Q4          2    50%       -46      10832    0.0%  📉
  2026-Q1          4    75%      +722      11553    0.0%  📈
  2026-Q2          7    14%     -1089      10465   11.3%  📉
  ───────────────────────────────────────────────────────
  TOTAL           36             +465      10465
2026-06-24 13:35:06 | INFO     | __main__ - Running walk-forward validation ...
2026-06-24 13:35:06 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 1/3: train=11266, test=4829
2026-06-24 13:35:06 | INFO     | phase7_backtest.backtest_engine - Backtest started: GBPJPY 15m — 16095 candles
2026-06-24 13:35:13 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 2/3: train=11266, test=4829
2026-06-24 13:35:13 | INFO     | phase7_backtest.backtest_engine - Backtest started: GBPJPY 15m — 16095 candles
2026-06-24 13:35:20 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 3/3: train=11266, test=4829
2026-06-24 13:35:20 | INFO     | phase7_backtest.backtest_engine - Backtest started: GBPJPY 15m — 16095 candles

  Walk-Forward:
    avg_winrate: 0.5143
    avg_profit_factor: inf
    avg_max_dd: 0.0455
    avg_net_profit_pct: 0.0023
    consistent: True

  Monte Carlo (1000 simulations):
    median_final_balance: 10464.8
    p5_final_balance: 10464.8
    p95_final_balance: 10464.8
    median_max_dd: 0.1092
    p95_max_dd: 0.1669
    ruin_probability: 0.0
2026-06-24 13:35:28 | INFO     | __main__ - MT5 Scalper | mode=backtest | OS=Mac/Linux | DATA_SOURCE=YFINANCE
2026-06-24 13:35:28 | INFO     | phase1_data.database - Database connected and schema ensured
2026-06-24 13:35:28 | INFO     | __main__ - Loading candles for XAUUSD 1h ...
2026-06-24 13:35:28 | INFO     | __main__ - Running backtest on 11499 candles (2024-06-21 → 2026-06-19)
2026-06-24 13:35:28 | INFO     | __main__ - candle_tracker_backtest truncated ✅
2026-06-24 13:35:28 | INFO     | phase7_backtest.backtest_engine - Backtest started: XAUUSD 1h — 11499 candles
2026-06-24 13:35:34 | INFO     | __main__ - Saving 20732 candle_tracker records ...
2026-06-24 13:35:40 | INFO     | phase1_data.database - Saved 20732 candle_tracker_backtest records
2026-06-24 13:35:40 | INFO     | __main__ - candle_tracker saved ✅
2026-06-24 13:35:40 | INFO     | phase1_data.database - Database disconnected

══════════════════════════════════════════════════
  BACKTEST RESULTS — XAUUSD 1h
  Period: 2024-06-21 → 2026-06-19
══════════════════════════════════════════════════
  total_trades             : 236
  winrate                  : 0.6017
  net_profit               : 26051.66
  net_profit_pct           : 2.6052
  profit_factor            : 2.79
  max_drawdown             : 1076.14
  max_drawdown_pct         : 0.0298
  avg_R                    : 1.85
  sharpe_ratio             : 6.85
  tp_count                 : 143
  sl_count                 : 70
  be_count                 : 23
  avg_win                  : 285.91
  avg_loss                 : -154.76
  PASSED                   : ✅ YES
══════════════════════════════════════════════════

  ── Quarterly Breakdown ──────────────────────────────
  Quarter     Trades   Win%        P&L    Balance     DD%
  ───────────────────────────────────────────────────────
  2024-Q2          1   100%      +208      10208    0.0%  📈
  2024-Q3         33    61%     +1545      11753    1.1%  📈
  2024-Q4         26    58%     +1925      13678    0.0%  📈
  2025-Q1         23    70%     +2878      16556    2.1%  📈
  2025-Q2         32    56%     +2464      19020    4.0%  📈
  2025-Q3         36    50%     +2411      21431    4.0%  📈
  2025-Q4         32    66%     +3988      25419    0.0%  📈
  2026-Q1         26    54%     +3046      28464    0.0%  📈
  2026-Q2         27    70%     +7587      36052    0.0%  📈
  ───────────────────────────────────────────────────────
  TOTAL          236           +26052      36052
2026-06-24 13:35:40 | INFO     | __main__ - Running walk-forward validation ...
2026-06-24 13:35:40 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 1/3: train=2683, test=1150
2026-06-24 13:35:40 | INFO     | phase7_backtest.backtest_engine - Backtest started: XAUUSD 1h — 3833 candles
2026-06-24 13:35:41 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 2/3: train=2683, test=1150
2026-06-24 13:35:41 | INFO     | phase7_backtest.backtest_engine - Backtest started: XAUUSD 1h — 3833 candles
2026-06-24 13:35:42 | INFO     | phase7_backtest.walk_forward - Walk-forward fold 3/3: train=2683, test=1150
2026-06-24 13:35:42 | INFO     | phase7_backtest.backtest_engine - Backtest started: XAUUSD 1h — 3833 candles

  Walk-Forward:
    avg_winrate: 0.667
    avg_profit_factor: 3.64
    avg_max_dd: 0.0257
    avg_net_profit_pct: 0.1967
    consistent: True

  Monte Carlo (1000 simulations):
    median_final_balance: 36051.66
    p5_final_balance: 36051.66
    p95_final_balance: 36051.66
    median_max_dd: 0.0603
    p95_max_dd: 0.1074
    ruin_probability: 0.0
(.venv) ngocdang@MacBook-Pro API_MT5 % 