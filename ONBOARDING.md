# Forex SMC Scalper Bot — Developer Onboarding Guide

> Dành cho developer mới join dự án.
> Đọc file này TRƯỚC khi đọc bất kỳ file code nào khác.
> **Created:** 2026-06-08 (Conv 1 — Forex)

---

## 1. Dự án này là gì?

**Forex SMC Scalper Bot** là một trading bot tự động giao dịch Forex trên sàn **OANDA**, dựa trên chiến lược **Smart Money Concepts (SMC)**.

- **Data source:** OANDA v20 REST API (lịch sử) + OANDA Streaming (real-time ticks)
- **Secondary data:** MetaTrader 5 Python API (Windows only, optional)
- **Order execution:** OANDA v20 REST API
- **Database:** PostgreSQL
- **Ngôn ngữ:** Python 3.10+, async

Bot được clone từ dự án OKX (crypto), giữ nguyên toàn bộ SMC strategy logic (Phases 2–5), chỉ thay thế API layer.

---

## 2. Khác biệt chính so với OKX version

| | OKX (Crypto) | OANDA (Forex) |
|---|---|---|
| Symbols | BTCUSDT, ETHUSDT... | EURUSD, GBPUSD, USDJPY... |
| API auth | HMAC-SHA256 sign | Bearer token |
| Real-time | WebSocket (OKX) | HTTP Streaming (SSE) |
| Order size | Contracts | Units (1 lot = 100,000 units) |
| PnL | USDT per contract | USD (pip × units) |
| Fees | Maker/Taker (0.02-0.04%) | Spread only (~1 pip) |
| Market hours | 24/7 | Mon–Fri (weekend closed) |
| Funding rate | Yes | No |
| Leverage | Up to 10x (OKX) | Up to 30x (OANDA regulated) |

---

## 3. Setup môi trường

### 3.1 Yêu cầu
```
Python 3.10+
PostgreSQL 14+
OANDA Practice account (tạo tại oanda.com)
```

### 3.2 Cài dependencies
```bash
cd /path/to/API_FOREX
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.3 Tạo database
```bash
# PostgreSQL
createdb forex_scalper_db
# Hoặc:
sudo -u postgres psql -c "CREATE DATABASE forex_scalper_db;"
```

### 3.4 Tạo file .env
```env
# OANDA Practice (tạo API key tại: https://www.oanda.com/account/tpa/personal_token)
OANDA_API_KEY=your_access_token
OANDA_ACCOUNT_ID=your_account_id
OANDA_PRACTICE_MODE=true      # true = practice (không tiền thật)

# MetaTrader 5 (Windows only, skip on Linux/Mac)
MT5_ENABLED=false

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=forex_scalper_db
DB_USER=postgres
DB_PASSWORD=your_password

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Trading
TRADING_PROFILE=CONSERVATIVE
ENTRY_TIMEFRAME=1h
```

### 3.5 Tìm OANDA Account ID
```python
import requests
headers = {"Authorization": "Bearer YOUR_TOKEN"}
r = requests.get("https://api-fxpractice.oanda.com/v3/accounts", headers=headers)
print(r.json())  # → list of accounts with "id"
```

---

## 4. Chạy thử từng bước

### Bước 1: Download data
```bash
python3 main.py download
# Downloads EURUSD, GBPUSD 15m + 1h for 2 years
# OANDA: 5000 candles/request, ~10-15 min for 2 symbols
```

### Bước 2: Verify data
```bash
python3 -c "
import asyncio
from phase1_data.database import Database
async def check():
    db = Database()
    await db.connect()
    rows = await db.pool.fetch('''
        SELECT symbol, timeframe, COUNT(*) n, MIN(open_time), MAX(open_time)
        FROM candles GROUP BY symbol, timeframe ORDER BY symbol, timeframe
    ''')
    for r in rows:
        print(dict(r))
    await db.disconnect()
asyncio.run(check())
"
# EURUSD 1h: ~17,500 rows; EURUSD 15m: ~70,000 rows
```

### Bước 3: Backtest
```bash
python3 main.py backtest --symbol EURUSD --tf 1h
# Expect: profit_factor > 1.5, max_drawdown < 15%
```

### Bước 4: Debug signal funnel
```bash
python3 main.py debug --symbol EURUSD --tf 1h --limit 1000
```

### Bước 5: Paper trading
```bash
python3 main.py paper
# Runs strategy on live OANDA prices, no orders placed
```

### Bước 6: Live (practice account)
```bash
python3 main.py live
# Places orders on OANDA practice — no real money
```

---

## 5. Kiến trúc real-time (khác OKX!)

### OKX (WebSocket candles)
```
OKX WS → closed candle → process signal
```

### OANDA (HTTP Streaming ticks → candle builder)
```
OANDA Streaming (ticks) → CandleAggregator → closed candle → process signal
```

`CandleAggregator` (`phase1_data/ws_collector.py`) gom ticks thành OHLCV bars:
- Mỗi (symbol, timeframe) có 1 aggregator riêng
- Khi tick mới vượt qua boundary → emit candle đã đóng
- Volume = số tick (proxy, không phải lot volume thật)

**Lưu ý:** OANDA streaming trả về **mid price** (bid+ask)/2, không phải giá giao dịch thật. Spread được tính vào cost khi backtest (SPREAD_COST_PCT trong backtest_engine.py).

---

## 6. Position sizing (Forex / OANDA units)

```python
# Công thức:
risk_amount = account_balance × risk_pct   # e.g. $10,000 × 1% = $100
sl_distance = abs(entry - sl)              # e.g. 1.1000 - 1.0990 = 0.0010 (10 pips)
units = risk_amount / sl_distance          # = $100 / 0.0010 = 100,000 units (1 lot)

# EURUSD ở 1.10: 1 pip = $10 cho 100,000 units
# Nếu SL = 10 pips → risk = 10 × $10 = $100 ✓
```

**Minimum SL:** 3 pips (0.0003 EURUSD). Nếu SL nhỏ hơn → position size = 0 (rejected).

---

## 7. Pip size theo pair

| Pair | Pip size | Note |
|---|---|---|
| EURUSD, GBPUSD, AUDUSD | 0.0001 | Standard |
| USDJPY, EURJPY, GBPJPY | 0.01 | JPY pairs |
| XAUUSD (Gold) | 0.01 | Commodity |
| XAGUSD (Silver) | 0.001 | Commodity |

---

## 8. Forex-specific gotchas

### Gotcha 1: Không có WebSocket candles
OANDA không có WS channel cho candles. Bot dùng HTTP Streaming (ticks) để build candles realtime. Nếu không có tick trong X giây → watchdog sẽ alert nhưng không có "zombie disconnect" như OKX WS.

### Gotcha 2: Weekend filter
`validate_candle()` tự động reject candles trong thời gian weekend (Sat 00:00 – Sun 21:00 UTC). Nếu muốn include weekend candles (testing only), pass `allow_weekend=True`.

### Gotcha 3: Volume = tick count
OANDA streaming không trả về lot volume thật. `CandleAggregator` dùng số tick trong bar làm volume. Layer 4 (volume check) vẫn hoạt động đúng vì dùng tỷ lệ tương đối (current/avg), nhưng con số tuyệt đối không có ý nghĩa.

### Gotcha 4: OANDA units là integer
`calc_position_size()` trả về `round(units)` — OANDA chấp nhận số nguyên. Không có "lot" concept trong OANDA API, chỉ dùng units trực tiếp.

### Gotcha 5: Practice vs Live endpoint khác nhau
```python
# Practice:
REST_BASE_URL   = "https://api-fxpractice.oanda.com"
STREAM_BASE_URL = "https://stream-fxpractice.oanda.com"

# Live:
REST_BASE_URL   = "https://api-fxtrade.oanda.com"
STREAM_BASE_URL = "https://stream-fxtrade.oanda.com"
```
Chỉ cần set `OANDA_PRACTICE_MODE=false` trong .env — settings.py tự switch URL.

### Gotcha 6: Account NAV vs Balance
`get_account_balance()` trả về `NAV` (Net Asset Value = balance + unrealized PnL). Đây là giá trị đúng nhất cho risk sizing. Balance (cash) có thể khác NAV nếu đang có open positions.

### Gotcha 7: MT5 chỉ chạy trên Windows
`MT5Downloader` yêu cầu MetaTrader5 package, chỉ hoạt động trên Windows với MT5 terminal đang chạy. Trên Mac/Linux VPS: `MT5_ENABLED=false` (default).

---

## 9. Checklist trước khi deploy VPS

```
□ OANDA Practice API key hoạt động
□ Download data: python3 main.py download
□ Backtest pass (PF > 1.5, DD < 15%): python3 main.py backtest --symbol EURUSD,GBPUSD --tf 1h
□ Chạy tests: python3 tests/run_tests.py
□ .env có OANDA_PRACTICE_MODE=true
□ .env có TRADING_PROFILE=CONSERVATIVE
□ Telegram bot token hoạt động
□ PostgreSQL forex_scalper_db đã tạo

Sau 1 tuần practice OK:
□ Kiểm tra candle_tracker_live: số lệnh, PnL distribution
□ So sánh practice PnL với backtest
□ Đổi OANDA_PRACTICE_MODE=false (live thật)
```

---

## 10. Quick Reference

```bash
# Download data
python3 main.py download

# Backtest
python3 main.py backtest --symbol EURUSD,GBPUSD --tf 1h

# Debug signal funnel
python3 main.py debug --symbol EURUSD --tf 1h --limit 1000

# Paper trading
python3 main.py paper

# Live (practice)
python3 main.py live

# Tests
python3 tests/run_tests.py

# Log
tail -f logs/scalper.log
```

---

*ONBOARDING.md — created: 2026-06-08 (Conv 1 — Forex)*
