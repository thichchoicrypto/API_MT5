# Forex SMC Scalper Bot — Backup Context
> Tài liệu ghi lại toàn bộ quá trình xây dựng dự án.
> Dùng để restore context khi bắt đầu conversation mới với AI.
>
> **Lần cuối cập nhật:** 2026-06-15 (Conv 11) — CHG-FX-024: fix cancel
> cross-client trên dashboard (xem mục 12f). CHG-FX-025: áp dụng luồng đó cho
> nút Cancel từng order — code xong, CHƯA deploy. 🔴 CHG-FX-026: fix bug
> SL/TP KHÔNG ĐƯỢC ĐẶT khi LIVE (xem 12f) — code xong, CHƯA deploy/test, cần
> làm TRƯỚC khi chạy LIVE với tiền thật. 🔴 CHG-FX-027: fix "naked position"
> khi LIMIT entry fill MUỘN (sau 2s check) — không có SL/TP — + fix false
> "CLOSED" event cho LIMIT order chưa fill (xem 12f) — code xong, CHƯA
> deploy/test. Còn 1 việc cần test: cancel SL/TP order của
> `forex-bot.service` (clientId=21 đang chạy 24/7).

---

## 0. Changelog (đọc đây trước)

| Date | Conv | Nội dung |
|---|---|---|
| 2026-06-08 | Conv 1 | Clone từ API_OKX, build Forex bot với IBKR API |
| 2026-06-09 | Conv 1 | IBKR account tạo xong (DUQ686904 paper), IB Gateway kết nối OK, data đang download |
| 2026-06-09 | Conv 1 | Thêm session filter (London/NY), fix volume layer cho tick data |
| 2026-06-09 | Conv 2 | Backtest xong, paper trading running |
| 2026-06-09 | Conv 2 | Fix 1h không preload vào paper engine (CHG-005) |
| 2026-06-09 | Conv 2 | Fix timezone bug EDT→UTC trong session_filter (CHG-006) |
| 2026-06-09 | Conv 2 | Fix MTFBias dùng chung cho tất cả symbols → per-symbol (CHG-007) |
| 2026-06-09 | Conv 2 | Fix TAKER_FEE=0 trong portfolio_tracker (CHG-008) |
| 2026-06-09 | Conv 2 | Viết VPS_DEPLOY.md, đang chờ upgrade VPS lên 2GB |
| 2026-06-09 | Conv 3 | IB Gateway login thành công trên VPS qua VNC (RealVNC + copy-paste) |
| 2026-06-09 | Conv 3 | Transfer code, setup venv, fix tzdata, setup PostgreSQL trên VPS |
| 2026-06-09 | Conv 3 | Download data + backtest + paper trading chạy OK trên VPS |
| 2026-06-09 | Conv 3 | RAM phân tích: 804MB/961MB, swap 399MB — nên nâng lên 2GB |
| 2026-06-14 | Conv 8 | Fix candle save bị rớt sau reconnect — lỗi asyncio task scheduling trong `_process_candle` (CHG-FX-008) |
| 2026-06-15 | Conv 9 | Fix root cause: `is_weekend_candle()` so sánh giờ Eastern với UTC → filter sai toàn bộ candle reopen đầu tuần (CHG-FX-009) |
| 2026-06-15 | Conv 10 | Thêm `set_position_mode`/`set_leverage`/`get_order` vào `IBKROrderManager` (CHG-FX-010), fix `NameError IBKRDownloader` trong gap-fill (CHG-FX-011), fix event-loop errors `get_position`/`get_account_balance` (CHG-FX-012) |
| 2026-06-15 | Conv 10 | **Switch `forex-bot.service` từ `main.py paper` → `main.py live`** — bot giờ đặt lệnh thật qua IBKR API trên demo account DUQ686904 (CHG-FX-013) |
| 2026-06-15 | Conv 10 | Fix SL/TP order bị reject "Parent order is being cancelled" — đổi bracket (`parentId`) sang OCA group (CHG-FX-014); thêm Web Dashboard monitor + đóng lệnh tay qua browser (CHG-FX-015) |
| 2026-06-15 | Conv 11 | Dashboard: thêm giá hiện tại/PnL/leverage/SL/TP vào "Position đang mở" (CHG-FX-018); fix `get_open_trades()` không thấy SL/TP cross-client + cancel `Error 10147` (CHG-FX-019); fix dashboard treo vô hạn (`_call_ib` timeout) + test script cancel nhầm order client khác (CHG-FX-020); fix AUDUSD (và symbol ngoài SYMBOLS) thiếu trong "Position đang mở" (CHG-FX-021) |
| 2026-06-15 | Conv 11 | Fix `cancel_order()` để tìm thấy order cross-client (CHG-FX-022, deployed) — test thật vẫn FAIL (CHG-FX-023: `PendingCancel` revert về `PreSubmitted`). **Fixed (CHG-FX-024)**: cancel "as owner" (connect tạm bằng clientId gốc) + nút "Cancel toàn bộ" trên dashboard — verify OK cho order client đã ngừng chạy; chưa test cho SL/TP order của bot (clientId=21 đang chạy 24/7) |

---

## 1. Tổng quan dự án

**Tên:** Forex SMC Scalper Bot
**Mục tiêu:** Scalping Forex dựa trên Smart Money Concepts (SMC)
**Exchange data:** IBKR TWS API (via IB Gateway)
**Exchange orders:** IBKR TWS API (IDEALPRO — ECN Forex)
**Database:** PostgreSQL (`forex_scalper_db`)
**Language:** Python 3.10+
**Location:** `/Users/ngocdang/Claude/Projects/API_FOREX`

**Khác với API_OKX:**
- Broker: IBKR thay OKX
- API: TWS socket (ib_insync) thay REST/WebSocket
- Real-time: 5s bars từ reqRealTimeBars thay OKX WebSocket candles
- Position size: IBKR units (1 lot = 100,000 units) thay OKX contracts
- Phải chạy IB Gateway trên cùng máy với bot

---

## 2. Kiến trúc hệ thống

```
IB Gateway (port 7497 paper / 7496 live)
    │
    │  5-second real-time bars
    ▼
phase1_data/ibkr_collector.py     ← IBKRStreamingCollector
    │  aggregate 5s → 15m/1h candles
    ▼
phase9_live/live_engine.py        ← orchestrator chính
    │
    ├── phase2_structure/          ← BOS, swing, trend (copy từ OKX)
    ├── phase3_liquidity/          ← sweep, CHoCH (copy từ OKX)
    ├── phase4_fvg_ob/             ← FVG, OB, confluence (copy từ OKX)
    ├── phase5_entry/              ← entry validation + session filter
    ├── phase6_risk/               ← SL/TP/units sizing (Forex adapted)
    │
    ▼
phase9_live/ibkr_order_manager.py ← đặt lệnh qua IB Gateway
    │
    ▼
IBKR IDEALPRO (paper hoặc live)
    │
    ▼
phase1_data/database.py           ← PostgreSQL
```

---

## 3. Cấu trúc 9 giai đoạn

| Phase | Tên | File | Từ OKX |
|---|---|---|---|
| 1 | Market Data (IBKR) | `phase1_data/ibkr_downloader.py`, `ibkr_collector.py` | Viết mới |
| 2 | Market Structure | `phase2_structure/` | Copy nguyên |
| 3 | Liquidity + CHoCH | `phase3_liquidity/` | Copy nguyên |
| 4 | FVG + Order Block | `phase4_fvg_ob/` | Copy nguyên |
| 5 | Entry Engine | `phase5_entry/` | Copy + session filter |
| 6 | Risk Engine | `phase6_risk/risk_engine.py` | Rewrite cho Forex |
| 7 | Backtest | `phase7_backtest/` | Copy + spread cost |
| 8 | Paper Trading | `phase8_paper/` | Copy nguyên |
| 9 | Live (IBKR) | `phase9_live/ibkr_order_manager.py`, `live_engine.py` | Viết mới + adapt |

---

## 4. Config quan trọng (`config/settings.py`)

```python
# IBKR Connection
IB_HOST      = "127.0.0.1"
IB_PORT      = 7497          # paper; 7496 = live
IB_CLIENT_ID = 1
IB_PAPER_MODE = True

# Trading Profile (CONSERVATIVE)
SYMBOLS    = ["EURUSD", "GBPUSD"]
TIMEFRAMES = ["15m", "1h"]
ENTRY_TIMEFRAME = "1h"

RISK_PER_TRADE  = 0.005    # 0.5%
MAX_DAILY_LOSS  = 0.02     # 2%
MAX_DRAWDOWN    = 0.10     # 10%
MIN_RR          = 1.5
MAX_LEVERAGE    = 20

# Session filter
SESSION_FILTER_ENABLED = True
# EURUSD/GBPUSD: 08:00–22:00 UTC
# USDJPY: 00:00–22:00 UTC

# Pip sizes
PIP_SIZE = {
    "EURUSD": 0.0001,
    "USDJPY": 0.01,
    "XAUUSD": 0.01, ...
}
```

---

## 5. IBKR Account

- **Paper Account ID:** `DUQ686904`
- **Paper port:** `7497`
- **Balance:** $1,000,000 virtual
- **Server:** OANDA_Global-Demo-1 (MT5 — khác với IBKR)
- **IB Gateway:** Đang chạy trên Mac, port 7497

**Live Account:** `U26205658` — đang chờ KYC duyệt (đã nộp ID + address)

---

## 6. Forex-specific logic

### Session Filter (`utils/session_filter.py`)
```
EURUSD, GBPUSD, XAUUSD → 08:00–22:00 UTC (London + NY)
USDJPY                 → 00:00–22:00 UTC (+ Tokyo)
Dead zone              → 22:00–00:00 UTC (tất cả skip)
Weekend                → skip
```

### Position Sizing (IBKR Units)
```
risk_amount = balance × risk_pct       ($10,000 × 0.5% = $50)
sl_distance = |entry - sl|             (EURUSD: 10 pips = 0.001)
units = risk_amount / sl_distance      = $50 / 0.001 = 50,000 units
Minimum: 20,000 units (IBKR requirement)
```

### Volume Layer (Forex)
```
IBKR trả về tick count (không phải real volume)
Threshold: 30% (thấp hơn OKX 50%)
Fallback: nếu volume=0 → dùng body size ≥ 30% ATR
```

---

## 7. Setup & Chạy

### Setup lần đầu
```bash
cd /Users/ngocdang/Claude/Projects/API_FOREX
source .venv/bin/activate
pip install -r requirements.txt

# Tạo DB
createdb forex_scalper_db

# Copy .env
cp .env.example .env
# Điền: IB_PORT=7497, IB_PAPER_MODE=true, DB_USER=ngocdang, DB_PASSWORD=...
```

### Prerequisite: IB Gateway phải đang chạy
```
1. Mở IB Gateway (hoặc TWS)
2. Login bằng IBKR username + password
3. Chọn Paper Trading
4. Configure → API → Settings:
   - Bỏ tick "Read-Only API"
   - Socket port: 7497
   - Apply → OK
```

### Các lệnh chính
```bash
# Download 2 năm data lịch sử
python3 main.py download

# Backtest
python3 main.py backtest --symbol EURUSD --tf 1h

# Backtest nhiều symbol
python3 main.py backtest --symbol EURUSD,GBPUSD --tf 1h

# Debug signal funnel
python3 main.py debug --symbol EURUSD --tf 1h --limit 1000

# Paper trading (internal simulation)
python3 main.py paper

# Live (IBKR paper account)
python3 main.py live
```

### .env cần thiết
```env
IB_HOST=127.0.0.1
IB_PAPER_MODE=true
IB_PORT=7497
IB_CLIENT_ID=1

DB_HOST=localhost
DB_PORT=5432
DB_NAME=forex_scalper_db
DB_USER=ngocdang
DB_PASSWORD=

TRADING_PROFILE=MODERATE
ENTRY_TIMEFRAME=15m
SESSION_FILTER_ENABLED=true

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## 8. Database schema

```sql
candles (symbol, timeframe, open_time, open, high, low, close, volume)
live_trades (order_id, symbol, side, entry_price, exit_price, sl, tp, size, pnl, ...)
paper_trades (...)
candle_tracker_backtest (symbol, timeframe, candle_time, side, l1_trend ... stop_reason)
candle_tracker_live (same)
-- Không có: funding_rates, open_interest (Forex không cần)
```

---

## 9. Trạng thái hiện tại (2026-06-09 Conv 3 — cuối session)

- ✅ 9 phases implemented
- ✅ IBKR TWS API integration (downloader + collector + order manager)
- ✅ IB Gateway login thành công trên VPS (paper account DUQ686904, port 7497)
- ✅ x11vnc cài xong, VNC connect từ Mac bằng RealVNC Viewer (copy-paste OK)
- ✅ Session filter (London/NY) — fix timezone EDT→UTC (CHG-006)
- ✅ Volume layer fix cho tick data
- ✅ Risk engine Forex (pip/lot/units)
- ✅ Weekend filter trong validator + DB
- ✅ PostgreSQL setup trên VPS: user=forexbot, db=forex_scalper_db
- ✅ Code transfer từ Mac → VPS (`/root/API_FOREX/`)
- ✅ Python venv setup trên VPS + tzdata fix
- ✅ Data download xong trên VPS (EURUSD, GBPUSD, USDJPY, XAUUSD)
- ✅ Backtest đã chạy xong trên VPS (all symbols, 15m)
- ✅ Paper trading chạy 24/7 qua `forex-bot.service` (systemd, auto-restart)
- ✅ Paper engine fixes: 1h preload (CHG-005), MTFBias per-symbol (CHG-007), TAKER_FEE=0 (CHG-008), order timeout (CHG-009)
- ✅ OKX bot + Forex bot chạy song song OK (PostgreSQL dùng chung, DB riêng)
- ✅ RAM 2GB — dùng ~620MB, swap 0B
- ✅ Telegram alerts hoạt động (cả OKX + Forex bot)
- ⏳ Monitor paper trades — chờ signal + fill vào paper_trades
- ⏳ IBKR live account đang chờ KYC duyệt (U26205658)
- ✅ (Conv 8-9, 2026-06-14/15) Fix candle bị mất sau reconnect (CHG-FX-008) + fix root cause candle bị mất sau weekend reopen do timezone bug trong `is_weekend_candle()` (CHG-FX-009) — xem mục 12b
- ✅ (Conv 10, 2026-06-15) **`forex-bot.service` đang chạy `python3 main.py live`** (active running từ 10:04 UTC, PID 151331) — bot đặt lệnh THẬT qua IBKR API trên demo/paper account DUQ686904 (port 7497, không phải tiền thật), thay cho `main.py paper` (mô phỏng nội bộ) trước đây. Đã fix CHG-FX-010/011/012 + verify end-to-end qua `scripts/test_order.py` và `scripts/check_account.py` — xem mục 12c
- ✅ (Conv 10, 2026-06-15) **Fix SL/TP bị reject** (CHG-FX-014) — `place_order()` đổi từ bracket `parentId` sang OCA group, verify lại qua `test_order.py`: SL/TP `status=PreSubmitted`, cancel sạch sau khi đóng lệnh — xem mục 12d
- ⏳ (Conv 10, 2026-06-15) **Web Dashboard** (CHG-FX-015) — `phase9_live/web_dashboard.py` đã viết xong, syntax OK, NHƯNG chưa deploy/test trên VPS (cần pip install fastapi/uvicorn, thêm DASHBOARD_USER/PASS vào .env, tạo `forex-dashboard.service`, mở port 8080) — xem mục 12d
- ⏳ Theo dõi: XAUUSD 1h backfill (0 candles) + alignment candle 1h (21:15 UTC offset) — xem `GUIDELINE.md` mục 17

---

## 10. Việc cần làm tiếp

1. **Monitor paper trades** — chờ signal fill vào paper_trades, xem winrate
   - Xem hướng dẫn chi tiết tại `VPS_DEPLOY.md` Bước 9
3. **Monitor paper trading** — theo dõi qua DB:
   ```sql
   SELECT symbol, side, entry_price, sl, tp, pnl, status, opened_at
   FROM paper_trades ORDER BY opened_at DESC LIMIT 20;
   ```
4. **IBKR live account KYC** — chờ duyệt (U26205658), khi duyệt xong → switch sang live

---

## 11. VPS State (69.12.65.42)

```
/root/ibgateway/          ← IB Gateway installed (version 10.45) — đã login OK
/root/API_FOREX/          ← Forex bot code
/root/API_FOREX/.venv/    ← Python venv
/root/API_FOREX/.env      ← config (IB_PORT=7497, DB=forex_scalper_db)
/opt/ibc/                 ← IBC installed (3.19.0) — chưa dùng, login thủ công qua VNC
/root/.vnc_pass           ← VNC password file

# Start IB Gateway (mỗi lần reboot):
Xvfb :1 -screen 0 1024x768x24 &
export DISPLAY=:1
/root/ibgateway/ibgateway &

# VNC để login thủ công (nếu cần):
x11vnc -display :1 -rfbauth /root/.vnc_pass -rfbport 5901 -bg -forever -quiet
# Mac: open vnc://69.12.65.42:5901 (dùng RealVNC Viewer, copy-paste để nhập)

# Chạy Forex bot:
cd /root/API_FOREX && source .venv/bin/activate
python3 main.py paper

# PostgreSQL:
# forex_scalper_db (user: forexbot / forexbot123)
# scalper_db (OKX bot — không đụng vào)
```

---

## 12. Bugs đã fix trong Conv 2

| CHG | File | Fix |
|---|---|---|
| CHG-005 | `main.py` | Preload cả 1h vào paper engine (thiếu → MTF bias NEUTRAL mãi) |
| CHG-006 | `utils/session_filter.py` | Convert EDT→UTC trước khi check session hour |
| CHG-007 | `main.py` | MTFBias per-symbol (tránh cross-symbol pollution) |
| CHG-008 | `phase8_paper/portfolio_tracker.py` | TAKER_FEE=0 (Forex không có fee, chỉ spread) |

---

## 12b. Bugs đã fix trong Conv 8-9 (live data pipeline — candle bị mất sau weekend reopen)

> Chi tiết đầy đủ xem `CHANGED.md` — Conv 8 (CHG-FX-008) và Conv 9 (CHG-FX-009).
> Lưu ý: numbering ở đây là `CHG-FX-XXX` (CHANGED.md), KHÁC với `CHG-00X` ở mục 12 (BACKUP_CONTEXT.md cũ).

| CHG | File | Triệu chứng | Fix |
|---|---|---|---|
| CHG-FX-008 | `phase1_data/ibkr_collector.py` | Sau khi mất kết nối/reconnect, candle mới không được lưu vào DB nữa (live stream vẫn chạy, log "Bar closed" vẫn ra nhưng không có "Candle saved") | `_process_candle()` được schedule qua `asyncio.ensure_future()` + done-callback `_log_task_error` để task lỗi không bị "biến mất" âm thầm |
| CHG-FX-009 | `phase1_data/validator.py` | Toàn bộ candle trong khoảng Sunday 21:00 → Monday 00:00 UTC (cửa sổ mở lại thị trường đầu tuần) bị `validate_candle()` loại bỏ âm thầm — kể cả live stream và backfill | `is_weekend_candle()` convert `open_time` sang UTC (`.astimezone(timezone.utc)`) trước khi check `.weekday()`/`.hour` — trước đó so sánh trực tiếp trên giờ Eastern (-04:00) trả về từ IBKR nên Sunday 22:00 UTC (=18:00 -04:00, hour<21) bị tính nhầm là weekend |

**Đã confirm fix CHG-FX-009 hoạt động** (2026-06-15 ~22:30 UTC): DB có candle mới 21:15-22:00 UTC cho EURUSD/GBPUSD/USDJPY (15m+1h) và XAUUSD (15m).

**Còn đang theo dõi (chưa giải quyết xong):**
- XAUUSD 1h vẫn chưa backfill được (0 candles) dù đã fix CHG-FX-009 — nghi do khác biệt data pipeline của IBKR cho contract `CMDTY/SMART` (XAUUSD) so với `CASH/IDEALPRO` (các pair Forex khác).
- Candle 1h mới của EURUSD/GBPUSD/USDJPY có `open_time=21:15 UTC` (lệch giờ tròn) — chưa rõ candle 1h tiếp theo sẽ giữ lệch 15p (23:15 UTC) hay tự realign về giờ tròn (22:00/23:00 UTC).
- Xem chi tiết theo dõi tại `GUIDELINE.md` mục 17.

---

## 12c. Switch sang `main.py live` — IBKR demo order routing (Conv 10, 2026-06-15)

> Chi tiết đầy đủ xem `CHANGED.md` — Conv 10 (CHG-FX-010, CHG-FX-011, CHG-FX-012, CHG-FX-013).

| CHG | File | Triệu chứng | Fix |
|---|---|---|---|
| CHG-FX-010 | `phase9_live/ibkr_order_manager.py` | `live_engine.py` gọi `set_position_mode`/`set_leverage`/`get_order` nhưng `IBKROrderManager` chưa có → `AttributeError` | Thêm 3 method: `set_position_mode`/`set_leverage` no-op (IBKR netting account + account-level leverage), `get_order` đọc `self._ib.trades()` trả `state: filled/open/cancelled` |
| CHG-FX-011 | `phase9_live/live_engine.py` | `NameError: name 'IBKRDownloader' is not defined` — crash ngay khi gap-fill lúc startup | Bỏ alias `as OANDARestDownloader` còn sót từ thời OANDA, import thẳng `IBKRDownloader` (2 chỗ: `start()` + `_backfill_gap()`) |
| CHG-FX-012 | `phase9_live/ibkr_order_manager.py` | `get_position`/`get_account_balance` raise `RuntimeError: This event loop is already running` | Đổi sang `await ib.reqPositionsAsync()` và `await ib.accountSummaryAsync()` (không phải `reqAccountSummaryAsync` — method đó return `[]` ngay, chưa có data) |
| CHG-FX-013 | `/etc/systemd/system/forex-bot.service` (VPS) | — | `ExecStart` đổi `main.py paper` → `main.py live`; verify `active (running)`, backfill OK, monitoring loop chạy với balance thật |

**Đã verify (2026-06-15):**
- `scripts/test_order.py` — place→fill→get_order→get_position→close end-to-end OK trên EURUSD (paper account DUQ686904).
- `scripts/check_account.py` — đọc balance (NetLiquidation=10005.74), positions, open orders, fills không cần login web portal.
- `forex-bot.service` chạy `main.py live`, `active (running)`, monitoring loop `{'balance': ..., 'open_positions': 0, 'daily_pnl_pct': 0.0, 'api_errors': 0}`.

**Lưu ý quan trọng:**
- Đây vẫn là **paper/demo account** (DUQ686904, port 7497) — KHÔNG phải tiền thật. Khác biệt với `main.py paper` (mô phỏng nội bộ, không gửi IBKR) là `main.py live` gửi order THẬT lên IBKR (demo), có SL/TP child orders, theo dõi được qua `check_account.py` hoặc Client Portal.
- Tránh login web Client Portal khi bot đang chạy (có thể trigger session-conflict, kick IB Gateway) — dùng `scripts/check_account.py` để theo dõi an toàn.

---

## 12d. Fix SL/TP bị reject + Web Dashboard (Conv 10, 2026-06-15)

> Chi tiết đầy đủ xem `CHANGED.md` — CHG-FX-014..017.

| CHG | File | Triệu chứng | Fix |
|---|---|---|---|
| CHG-FX-014 | `phase9_live/ibkr_order_manager.py` | Test `test_order.py` (MARKET BUY + SL/TP) → SL/TP bị IBKR reject `Error 201: Order rejected - reason: Parent order is being cancelled`. Position mở ra KHÔNG có SL/TP bảo vệ | `place_order()`: bỏ `parentId` bracket (vì MarketOrder transmit+fill ngay trước khi SL/TP được tạo), đặt SL/TP độc lập cùng `ocaGroup`+`ocaType=1` — khi 1 khớp, IBKR tự cancel cái còn lại |
| CHG-FX-015 | `phase9_live/web_dashboard.py` (mới) | Cần xem position/open orders/đóng lệnh tay mà không login Client Portal (rủi ro session-conflict) và không cần SSH | FastAPI app, `IBKROrderManager(client_id_offset=40)`, Basic Auth, trang HTML auto-refresh 5s + nút Đóng/Cancel. Chạy qua `forex-dashboard.service` port 8080 |
| CHG-FX-016 | `phase9_live/web_dashboard.py` | Sau khi deploy CHG-FX-015: `forex-dashboard.service` crash-loop — `RuntimeError: ... attached to a different loop` khi `IB().connectAsync()` chạy trong loop của uvicorn | Chạy `IBKROrderManager`/`IB()` trên 1 event loop riêng trong 1 thread riêng (`threading.Thread` + `run_forever()`), FastAPI gọi qua `_call_ib()` = `run_coroutine_threadsafe` + `wrap_future` |
| CHG-FX-017 | `phase9_live/web_dashboard.py` + VPS `.env` | Mọi request → `500 Internal Server Error`. `TypeError: comparing strings with non-ASCII characters is not supported` trong `check_auth()` — do `.env` còn placeholder `DASHBOARD_PASS=<mật khẩu mạnh của bạn>` (dấu tiếng Việt) | `check_auth()`: `.encode("utf-8")` trước `secrets.compare_digest()`; xoá placeholder trùng trong `.env`, set password ASCII thật |

**Đã verify CHG-FX-014** (2026-06-15, `scripts/test_order.py`, clientId offset=30):
MARKET BUY 20,000 EURUSD @ 1.16118 → SL #13 (1.15618) + TP #14 (1.17118) đều
`PreSubmitted`, có trong `get_open_trades()`. Đóng position → flat. `cancel_order()`
dọn sạch SL/TP còn lại.

**Lưu ý:** Client Portal Web API (`/portfolio/{accountId}/positions/all`) không thấy
position/order dù TWS API thấy đúng — do paper account không sync real-time vào hệ
thống mà Client Portal Web query (khác session với TWS API/IB Gateway). Không phải bug.

**CHG-FX-015..017 — đã deploy + verify đầy đủ** (2026-06-15): `forex-dashboard.service`
`active (running)`, không crash-loop. Truy cập `http://<VPS_IP>:8080`, login thành
công, dashboard hiển thị balance/positions/open orders/recent fills đúng, và **đóng
lệnh tay (nút Đóng) qua web hoạt động thành công**.

---

## 12e. Dashboard: enrich position table + fix cross-client orders + fix treo (Conv 11, 2026-06-15)

> Chi tiết đầy đủ xem `CHANGED.md` — CHG-FX-018..020.

| CHG | File | Triệu chứng | Fix |
|---|---|---|---|
| CHG-FX-018 | `ibkr_order_manager.py` (`get_position`), `web_dashboard.py` | Bảng "Position đang mở" thiếu giá hiện tại/PnL/leverage/SL/TP | `get_position()` trả thêm `market_price`/`unrealized_pnl`/`value_usd`; `_fetch_state()` gắn `sl_price`/`tp_price` từ `open_orders` (STP/LMT cùng symbol) + tính `leverage`; HTML thêm cột |
| CHG-FX-019 | `ibkr_order_manager.py` (`get_open_trades`) | SL/TP do client khác đặt không hiện trong "Open orders"; cancel order client khác → `ok:true` nhưng `Error 10147` (order vẫn còn) | `reqAllOpenOrders()` + clear `wrapper.trades`/`permId2Trade` trước mỗi snapshot (thấy order mọi client). Set **Master API Client ID = 41** trong IB Gateway (cần restart Gateway để có hiệu lực đầy đủ cho cancel). Workaround hiện tại: `scripts/cancel_orphan_orders.py <orderIds>` (connect lại bằng đúng clientId đã đặt order) |
| CHG-FX-020 | `web_dashboard.py` (`_call_ib`), `scripts/test_orders_batch.py` | Dashboard treo "Đang tải..." vô hạn (~21 phút) sau khi đóng lệnh, restart service cũng bị stuck; test script cleanup cancel nhầm order #160 của dashboard (race) | `_call_ib(coro, timeout=10.0)` dùng `asyncio.wait_for` → timeout raise `HTTPException(503)`, giải phóng `_lock`. Test script lưu `placed_order_ids` (entry+SL+TP của chính nó), cleanup chỉ cancel orderId trong set này, skip order của client khác |
| CHG-FX-021 | `ibkr_order_manager.py` (`get_all_positions`, `_position_dict`, `_IBKR_SYMBOL_MAP_REV`), `web_dashboard.py` (`_fetch_state`) | AUDUSD (position có SL/TP mở #107/#108) không hiện trong "Position đang mở" — chỉ GBPUSD hiện | `_fetch_state()` đổi từ `for sym in SYMBOLS: get_position(sym)` → `for pos in await _om.get_all_positions()`: method mới gọi `reqPositionsAsync()` 1 lần, lặp TOÀN BỘ position CASH != 0, resolve symbol qua `_IBKR_SYMBOL_MAP_REV` (fallback `f"{ib_symbol}{currency}"`). Bỏ import `SYMBOLS` (không còn dùng) |

**Đã verify CHG-FX-018/019** (2026-06-15, `scripts/test_orders_batch.py`: 2 MARKET +
2 LIMIT, đủ SL/TP = 10 order): "Position đang mở" hiển thị đúng GBPUSD (avg cost,
giá hiện tại, PnL, leverage, SL, TP). "Open orders" hiện đủ 10 order với
`order_type`/`price` đúng. Cancel cross-client từ dashboard bị 10147 →
`cancel_orphan_orders.py` (offset=30) cancel sạch, `get_open_trades() = []`.

**CHG-FX-020/021 — code đã viết + `py_compile` OK, CHƯA deploy/test trên VPS** (cần
rsync `web_dashboard.py`, `ibkr_order_manager.py`, `test_orders_batch.py`, restart
`forex-dashboard.service`, chạy lại `test_orders_batch.py` để verify end-to-end —
kiểm tra cả GBPUSD VÀ AUDUSD hiện trong "Position đang mở").

**Việc còn cần làm (Conv 11):**
- Restart IB Gateway (lúc bot flat, ít rủi ro) để Master Client ID=41 có hiệu lực
  đầy đủ cho cancel cross-client — sau đó không cần `cancel_orphan_orders.py` nữa.

---

## 12f. ✅ Fix cancel cross-client: "cancel as owner" + nút "Cancel toàn bộ" (CHG-FX-023/024, Conv 11, 2026-06-15)

> Chi tiết đầy đủ xem `CHANGED.md` — CHG-FX-023 (root cause) / CHG-FX-024 (fix).

- **Root cause (CHG-FX-023):** Cancel cross-client từ dashboard (clientId=41)
  chỉ đưa order về `PendingCancel` rồi KHÔNG finalize — dù Master API Client
  ID=41 + Read-Only API=off đã set đúng trên Gateway (verify qua VNC, đã set từ
  trước). `OverrideTwsMasterClientID` trong `/opt/ibc/config.ini` không có
  evidence apply (jts.ini không có key master/client). Cancel bằng ĐÚNG
  clientId gốc đã đặt order (`cancel_orphan_orders.py`, same-owner) thì
  finalize `Cancelled` ngay.
- **Fix (CHG-FX-024):**
  - `get_open_trades()` trả thêm `clientId` của order.
  - Hàm mới `cancel_order_as_owner(order_id, raw_client_id)` — connect TẠM
    bằng đúng clientId gốc, cancel, disconnect. Trả `None` nếu clientId đó
    đang busy (process khác đang chạy, vd forex-bot clientId=21).
  - `web_dashboard.py`: endpoint `POST /api/cancel_all` + nút **"Cancel toàn
    bộ"** — tự chọn `direct` (order của dashboard) / `as-owner` (connect tạm
    bằng clientId gốc) / `cross-client-fallback` (clientId gốc busy).
- **✅ Verify:** Deploy VPS, test order #174 (NZDUSD, clientId=31, không có
  process nào dùng clientId 31) → bấm "Cancel toàn bộ" → `cancel_order_as_owner`
  connect clientId=31 → `#174 status=Cancelled -> ok=True`, biến mất khỏi Open
  orders.
- **⚠️ Chưa test:** Order do `forex-bot.service` (clientId=21, đang chạy 24/7)
  đặt — case này `cancel_order_as_owner` sẽ trả `None` (clientId 21 busy) →
  fallback cross-client thường → nhiều khả năng vẫn `PendingCancel` không
  finalize. Đây là use case CHÍNH của CHG-FX-019 (cancel SL/TP của bot) — **cần
  test khi có SL/TP order thật của bot đang mở**.
- **CHG-FX-025 (Conv 11, cùng ngày):** Áp dụng CÙNG luồng "as-owner /
  fallback" (qua hàm chung `_cancel_order_dict`) cho nút **Cancel riêng từng
  Open Order** (`/api/cancel`), không chỉ "Cancel toàn bộ". Code xong,
  `py_compile` OK — **chưa deploy/verify trên VPS**. Chi tiết: `CHANGED.md`.
- **🔴 CHG-FX-026 (Conv 11, cùng ngày) — BUG NGHIÊM TRỌNG đã fix:**
  `live_engine._execute_signal()` đặt SL bằng `place_order(..., stop_price=
  ...)` — tham số SAI (`ibkr_order_manager.place_order()` chỉ nhận `price=`
  cho `STOP_MARKET`) → raise TypeError → **SL KHÔNG BAO GIỜ được đặt lên
  IBKR** khi LIVE. Đồng thời `order_id` lấy sai key (`ordId`/`clOrdId` kiểu
  OKX cũ, IBKR trả `orderId`) → `get_order()` luôn fail → SL/TP deferred vĩnh
  viễn cho LIMIT entry. TP cũng chưa từng được đặt thành order thật. Đã fix:
  MARKET entry đặt kèm SL+TP cùng lúc (OCA); LIMIT entry đặt SL+TP sau khi
  confirm fill, dùng `price=risk["sl"]` đúng. **CHƯA deploy/test với tín hiệu
  LIVE thật** — cần làm TRƯỚC khi để bot chạy với tiền thật. Chi tiết:
  `CHANGED.md`.
- **🔴 CHG-FX-027 (Conv 11, cùng ngày) — fix tiếp 2 vấn đề còn lại sau
  CHG-FX-026:**
  1. Nếu LIMIT entry CHƯA fill trong 2s check đầu tiên, code cũ chỉ
     `logger.warning` rồi bỏ quên — nếu order fill SAU đó, position không có
     SL/TP ("naked position"). Fix: lưu vào `self._pending_limit_orders`,
     `_check_pending_limit_orders()` (mới, gọi mỗi 60s từ
     `_monitoring_loop`) poll lại, đặt SL/TP + finalize khi fill.
  2. `_finalize_entry` (telegram/DB/`position_monitor.track`) trước đây bị
     gọi NGAY CẢ KHI LIMIT order chưa fill → `position_monitor.open_positions`
     có symbol dù chưa có position thật trên IBKR →
     `_check_closed_positions()` (60s sau) thấy `get_position()=None` → tưởng
     "đã bị TP/SL đóng" → gửi Telegram "CLOSED" giả + lưu DB sai. Fix: chỉ gọi
     `_finalize_entry` khi entry CONFIRMED FILLED (MARKET ngay, LIMIT fill
     trong 2s, hoặc LIMIT fill muộn qua `_check_pending_limit_orders`).
  `MAX_OPEN_POSITIONS` check cũng được cập nhật để tính cả
  `_pending_limit_orders`. **CHƯA deploy/test với tín hiệu LIVE thật.** Chi
  tiết: `CHANGED.md`.

---

## 13. VPS Info

- **VPS (dùng chung OKX + Forex):** 69.12.65.42, Ubuntu 24.04, **2GB RAM** (đã upgrade)
- **RAM thực tế sau upgrade:**
  - IB Gateway: ~370MB
  - PostgreSQL: ~200MB
  - Forex bot: ~41MB
  - OKX bot: ~34MB
  - **Tổng: ~620MB/1.9GB — Swap: 0B ✅**
- **Reboot VPS:** phải dùng SolusVM panel (không dùng `sudo reboot` — không apply RAM mới)
- **Deploy guide:** Xem `VPS_DEPLOY.md`

---

## 14. Liên lạc với AI trong conversation mới

Khi bắt đầu conversation mới, paste đoạn này:

> "Tôi có project Forex SMC Scalper Bot tại `/Users/ngocdang/Claude/Projects/API_FOREX`.
> Đọc file `BACKUP_CONTEXT.md` và `CHANGED.md` để hiểu context.
> VPS 69.12.65.42 (2GB RAM): IB Gateway login OK, forex-bot.service chạy 24/7, Telegram alerts OK.
> Paper trading đang chạy — chờ signal fill vào paper_trades để monitor.
> IBKR live account U26205658 chờ KYC duyệt.
> Tiếp tục từ đây."
