# Forex SMC Scalper Bot — Developer Guideline
> Tài liệu tham khảo đầy đủ.
> **Cập nhật:** 2026-06-12 (Conv 2 — thêm IBC auto-login)

---

## Mục lục
1. [Kiến trúc tổng quan](#1-kiến-trúc-tổng-quan)
2. [Cấu trúc folder & file](#2-cấu-trúc-folder--file)
3. [IB Gateway — bắt buộc phải chạy](#3-ib-gateway--bắt-buộc-phải-chạy)
4. [Luồng call giữa các file](#4-luồng-call-giữa-các-file)
5. [Khi nào bot vào lệnh](#5-khi-nào-bot-vào-lệnh)
6. [Session Filter — Forex-specific](#6-session-filter--forex-specific)
7. [Position sizing — IBKR units](#7-position-sizing--ibkr-units)
8. [Stop Loss & Take Profit](#8-stop-loss--take-profit)
9. [Database — schema, query mẫu](#9-database--schema-query-mẫu)
10. [Chạy download data](#10-chạy-download-data)
11. [Chạy backtest](#11-chạy-backtest)
12. [Chạy live trading](#12-chạy-live-trading)
13. [Kill Switch & Safe Mode](#13-kill-switch--safe-mode)
14. [Deploy VPS (Linux headless)](#14-deploy-vps-linux-headless)
15. [Debug khi bot không vào lệnh](#15-debug-khi-bot-không-vào-lệnh)
16. [Khác biệt với API_OKX](#16-khác-biệt-với-api_okx)
17. [Theo dõi & cải tiến tiếp theo](#17-theo-dõi--cải-tiến-tiếp-theo)

---

## 1. Kiến trúc tổng quan

```
IB Gateway (chạy trên máy, port 7497)
    │
    │  reqRealTimeBars (5-second bars)
    ▼
IBKRStreamingCollector           phase1_data/ibkr_collector.py
    │  5s → 15m/1h candle (CandleAggregator)
    ▼
LiveTradingEngine                phase9_live/live_engine.py
    │
    ├─ StructureEngine            phase2_structure/
    ├─ Liquidity detect           phase3_liquidity/
    ├─ FVG + OB detect            phase4_fvg_ob/
    ├─ EntryEngine (session check) phase5_entry/
    ├─ ForexRiskEngine            phase6_risk/
    │
    ▼
IBKROrderManager                 phase9_live/ibkr_order_manager.py
    │  MarketOrder / LimitOrder / StopOrder
    ▼
IBKR IDEALPRO (paper/live)
```

---

## 2. Cấu trúc folder & file

```
API_FOREX/
├── main.py                         ← Entry point: download/backtest/paper/live/debug
├── config/
│   └── settings.py                 ← TẤT CẢ config
├── utils/
│   ├── logger.py                   ← Loguru setup
│   ├── telegram.py                 ← Telegram alerts
│   ├── session_filter.py           ← Forex session hours (London/NY)
│   └── news_filter.py              ← (disabled) news filter
├── phase1_data/
│   ├── ibkr_downloader.py          ← IBKR historical data (reqHistoricalData)
│   ├── ibkr_collector.py           ← IBKR real-time 5s bars → candles
│   ├── rest_downloader.py          ← OANDA REST (fallback/reference)
│   ├── ws_collector.py             ← OANDA streaming (fallback/reference)
│   ├── mt5_downloader.py           ← MT5 (Windows only, disabled)
│   ├── database.py                 ← PostgreSQL CRUD
│   ├── validator.py                ← OHLCV validation + weekend filter
│   └── backfill.py                 ← Gap detection + fill
├── phase2_structure/               ← BOS, swing, trend (từ OKX, không sửa)
├── phase3_liquidity/               ← sweep, CHoCH (từ OKX, không sửa)
├── phase4_fvg_ob/                  ← FVG, OB, zones (từ OKX, không sửa)
├── phase5_entry/
│   ├── entry_engine.py             ← 5 layers + session filter + tick volume fix
│   └── trigger_detector.py        ← Pin bar, hammer, engulfing
├── phase6_risk/
│   └── risk_engine.py              ← Forex: pip SL, units sizing, PnL calc
├── phase7_backtest/
│   └── backtest_engine.py          ← Spread cost thay fees, symbol param
├── phase8_paper/                   ← Paper simulation (từ OKX)
├── phase9_live/
│   ├── ibkr_order_manager.py       ← IBKR order execution
│   ├── live_engine.py              ← Orchestrator (adapt từ OKX)
│   ├── kill_switch.py              ← Emergency stop
│   └── position_monitor.py        ← Track open positions
└── tests/
    └── test_forex_specific.py      ← Tests riêng cho Forex
```

---

## 3. IB Gateway — bắt buộc phải chạy

**IB Gateway là cầu nối bắt buộc.** Bot không kết nối trực tiếp với IBKR server được.

```
Bot → [TCP localhost:7497] → IB Gateway → IBKR Server
```

### Setup ban đầu (1 lần — đã làm xong trên VPS 69.12.65.42)
```
1. Download: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
2. Login: chọn IB API → Paper Trading → nhập username/password IBKR
3. Configure → API → Settings:
   - BỎ TICK "Read-Only API"
   - Socket port: 7497
   - Apply → OK
```

---

### IBC (IBController) — Auto-login, không cần VNC (Conv 2 — 2026-06-12)

VPS đã cài **IBC v3.19.0** (`/opt/ibc/`) để IB Gateway **tự động login** sau mỗi lần reboot/crash — không cần VNC thủ công nữa. Chạy qua **systemd service `ibgateway.service`**: tự start khi boot, tự restart nếu crash (`Restart=always`).

> 🔄 **Update Conv 3 — VNC đã bật lại (optional)**: `x11vnc` được thêm vào `/root/start_ibgateway.sh` (chạy sau `export DISPLAY=:1`), nghe ở port **5901**. Auto-login qua IBC vẫn hoạt động bình thường — VNC chỉ để **xem GUI Gateway khi cần** (không bắt buộc). Connect bằng RealVNC Viewer → `69.12.65.42:5901`. Verify: `ss -tlnp | grep 5901`.

#### Quản lý service
```bash
systemctl status ibgateway      # check trạng thái (active/running)
systemctl restart ibgateway     # restart (sau khi đổi config.ini)
systemctl stop ibgateway
journalctl -u ibgateway -f      # log realtime
tail -f /tmp/ibgw.log           # log file IBC
ss -tlnp | grep 7497            # verify port API đang LISTEN
```

#### File liên quan

| File | Vai trò |
|---|---|
| `/opt/ibc/config.ini` | Config IBC: `IbLoginId`, `IbPassword`, `TradingMode=paper`, `LoginDialogDisplayTimeout=180` |
| `/root/start_ibgateway.sh` | Wrapper: start Xvfb `:1` nếu chưa chạy, rồi `exec ibcstart.sh` |
| `/etc/systemd/system/ibgateway.service` | systemd unit — `Restart=always`, `RestartSec=15`, log → `/tmp/ibgw.log` |
| `/root/ibgateway/1045/` | IB Gateway 10.45 install dir (`gateway_program_path`) |
| `/root/ibgateway/1045/ibgateway.vmoptions` | JVM options — đã thêm `--add-opens` cho Java 17 |
| `/root/Jts/launcher.log` | Log chi tiết của IB Gateway (khác `/tmp/ibgw.log`, xem khi cần debug UI) |

#### Lệnh start thủ công (debug, ngoài systemd)
```bash
export DISPLAY=:1
/opt/ibc/scripts/ibcstart.sh 1045 --gateway \
  --tws-path=/root --tws-settings-path=/root/Jts \
  --ibc-path=/opt/ibc --ibc-ini=/opt/ibc/config.ini \
  --mode=paper --java-path=/usr/bin
```

#### Các fix bắt buộc để IBC chạy được trên Java 17 / Ubuntu 24.04

IB Gateway 10.45 không tương thích thẳng với OpenJDK 17 + Ubuntu 24.04 — đã fix 3 vấn đề (đã áp dụng trên VPS rồi, KHÔNG cần làm lại — chỉ tham khảo nếu phải cài VPS mới từ đầu).

> 📌 Cách dùng: SSH vào VPS (`ssh root@69.12.65.42`) trước, rồi copy nguyên block lệnh paste vào terminal, Enter. Mục 1 là sửa nội dung file (dùng lệnh `cat >>` để append, không cần mở editor); mục 2 và 3 là lệnh cài package/copy file chạy thẳng.

1. **`InaccessibleObjectException` (module javax.swing)** — Java 17 module system chặn reflection legacy của Swing LAF.
   → Append 7 dòng `--add-opens` vào cuối `/root/ibgateway/1045/ibgateway.vmoptions` bằng lệnh sau (chạy thẳng trên VPS):
   ```bash
   cat >> /root/ibgateway/1045/ibgateway.vmoptions <<'EOF'
   --add-opens=java.desktop/javax.swing=ALL-UNNAMED
   --add-opens=java.desktop/java.awt=ALL-UNNAMED
   --add-opens=java.desktop/sun.awt=ALL-UNNAMED
   --add-opens=java.desktop/sun.swing=ALL-UNNAMED
   --add-opens=java.desktop/com.sun.java.swing.plaf.windows=ALL-UNNAMED
   --add-opens=java.base/java.lang=ALL-UNNAMED
   --add-opens=java.base/java.util=ALL-UNNAMED
   EOF
   ```
   ⚠️ Phải sửa file `ibgateway.vmoptions` (ibcstart.sh đọc file này để build JVM args) — biến env `JAVA_TOOL_OPTIONS` KHÔNG có tác dụng.

2. **`NoClassDefFoundError: javafx/embed/swing/JFXPanel` và `javafx/scene/web/WebView`** — login UI của Gateway 10.45 dùng JavaFX (JFXPanel + WebView), nhưng OpenJDK 17 không bundle JavaFX nữa.
   → Cài package `openjfx` rồi copy jar vào classpath của Gateway:
   ```bash
   apt-get install -y openjfx
   cp /usr/share/openjfx/lib/javafx.base.jar /usr/share/openjfx/lib/javafx.graphics.jar \
      /usr/share/openjfx/lib/javafx.swing.jar /usr/share/openjfx/lib/javafx.controls.jar \
      /usr/share/openjfx/lib/javafx.fxml.jar /usr/share/openjfx/lib/javafx.web.jar \
      /usr/share/openjfx/lib/javafx.media.jar /root/ibgateway/jars/
   ```

3. **Missing GTK3/audio libs** (Ubuntu 24.04 đổi tên package):
   ```bash
   apt-get install -y libgtk-3-0 libasound2t64
   ```

#### Triệu chứng cũ (đã fix) — "login dialog not displayed"

Nếu thấy log lặp mỗi `LoginDialogDisplayTimeout` giây:
```
IBC: Starting Gateway
IBC: IBC will restart shortly
... lặp lại ...
```
→ Check `/root/Jts/launcher.log` (KHÔNG phải `/tmp/ibgw.log`), tìm dòng `ERROR [AWT-EventQueue-0] - Error` → thường là `NoClassDefFoundError` thiếu javafx jar (xem mục 2 trên). Sau khi copy jar đủ → `systemctl restart ibgateway`.

---

### Test kết nối
```bash
python3 -c "
import asyncio
from ib_insync import IB
async def test():
    ib = IB()
    await ib.connectAsync('127.0.0.1', 7497, clientId=1)
    print('✅ Connected:', ib.managedAccounts())
    ib.disconnect()
asyncio.run(test())
"
```

---

## 4. Luồng call giữa các file

### Khi candle 15m đóng (live)
```
IBKRStreamingCollector._on_candle_close(candle)
  → db.upsert_candle()
  → live_engine.on_candle(candle)
    → _process_signal(symbol, candles)
      → structure_engine.update(candles[-201:])
      → detect_sweep() / detect_choch() + TTL memory
      → detect_fvg() / detect_all_obs() / find_confluence_zones()
      → build_entry_zone()
      → for side in (LONG, SHORT):
          → risk_engine.evaluate(side, symbol, entry, candles, struct, liq_zones)
          → entry_engine.evaluate(candles, struct, liq_output, zone, risk_out)
            → session_filter.is_trading_session(symbol, candle_time)  ← Forex-specific
            → ADX check (15m only)
            → L1 trend → L2 zone touch → L3 liquidity → L4 volume → L5 trigger
          → if signal: _execute_signal()
            → ibkr_order_manager.place_order()
```

---

## 5. Khi nào bot vào lệnh

Bot chỉ vào lệnh khi **tất cả** pass:

```
Layer 0 — Session filter (Forex-specific)
  EURUSD/GBPUSD: 08:00–22:00 UTC
  USDJPY: 00:00–22:00 UTC
  Dead zone 22:00–00:00: SKIP tất cả

Layer 1 — Trend đúng chiều
  LONG: trend=UP hoặc 1h bias=LONG
  SHORT: trend=DOWN hoặc 1h bias=SHORT
  RANGE: cần sweep + CHoCH đúng chiều

Layer 2 — Giá chạm zone FVG/OB
  Nến phải overlap với zone (proximity 3×ATR)

Layer 3 — Có sweep hoặc CHoCH
  Sự kiện tồn tại 20 candles (TTL=20)

Layer 4 — Volume/momentum OK
  Tick count ≥ 30% avg 20 bars
  Fallback: candle body ≥ 30% ATR

Layer 5 — Trigger candle
  Pin bar / hammer / engulfing
  Confirm window: 3 candles

Layer 6 — Risk OK
  RR ≥ 1.5, SL distance hợp lý
  Units ≥ 20,000 (IBKR minimum)
```

---

## 6. Session Filter — Forex-specific

File: `utils/session_filter.py`

| Symbol | Active hours (UTC) | Session |
|---|---|---|
| EURUSD, GBPUSD | 08:00–22:00 | London + NY |
| USDJPY, EURJPY, GBPJPY | 00:00–22:00 | Tokyo + London + NY |
| AUDUSD, NZDUSD | 08:00–22:00 | London + NY |
| USDCAD | 13:00–22:00 | NY only (most liquid) |
| XAUUSD | 08:00–22:00 | London + NY |
| **Dead zone** | 22:00–00:00 | Tất cả skip |
| **Weekend** | Sat/Sun | Tất cả skip |

**Tắt session filter** (debug/backtest):
```env
SESSION_FILTER_ENABLED=false
```

---

## 7. Position sizing — IBKR units

```python
# Công thức
risk_amount = account_balance × risk_pct   # $10,000 × 0.5% = $50
sl_distance = abs(entry - sl)              # EURUSD: 10 pips = 0.0010
units = risk_amount / sl_distance          # $50 / 0.001 = 50,000 units

# Giới hạn
minimum_units = 20_000    # IBKR IDEALPRO minimum
maximum_units = balance × MAX_LEVERAGE / entry

# Pip sizes
EURUSD/GBPUSD: pip = 0.0001
USDJPY/EURJPY: pip = 0.01
XAUUSD: pip = 0.01
```

**1 standard lot = 100,000 units = $10/pip (EURUSD)**

---

## 8. Stop Loss & Take Profit

```python
# SL: beyond swing level + buffer
SL_BUFFER = 0.0003      # 3 pips minimum OR 0.03% of price
minimum SL = 3 pips     # dưới đây → reject trade (units = 0)

# TP: multi-level
TP1 = entry + 2.0 × SL_distance  (50% size)
TP2 = entry + 2.5 × SL_distance  (30% size, hoặc liquidity target)
TP3 = entry + 4.0 × SL_distance  (20% size, hoặc liquidity target)

# IBKR: SL/TP đặt như child orders (StopOrder + LimitOrder)
# Attached vào parent order via parentId
```

---

## 9. Database — schema, query mẫu

```sql
-- Candles
SELECT symbol, timeframe, COUNT(*), MIN(open_time), MAX(open_time)
FROM candles GROUP BY symbol, timeframe ORDER BY symbol, timeframe;

-- Xem signal funnel (live)
SELECT stop_reason, COUNT(*), ROUND(COUNT(*)*100.0/SUM(COUNT(*)) OVER(),1) pct
FROM candle_tracker_live
WHERE candle_time > NOW() - INTERVAL '24 hours'
GROUP BY stop_reason ORDER BY count DESC;

-- Lệnh đã vào
SELECT candle_time, symbol, side, entry_price, sl, tp1, rr, pnl, exit_reason
FROM candle_tracker_live WHERE order_placed=TRUE ORDER BY candle_time DESC;

-- PnL summary
SELECT symbol, COUNT(*) trades,
       ROUND(AVG(CASE WHEN pnl>0 THEN 1.0 ELSE 0 END)*100,1) winrate,
       ROUND(SUM(pnl)::numeric, 2) total_pnl
FROM candle_tracker_live WHERE trade_closed=TRUE GROUP BY symbol;
```

---

## 10. Chạy download data

```bash
# Download tất cả symbols trong TRADING_PROFILE
python3 main.py download

# Download symbol cụ thể
python3 main.py download --symbol XAUUSD

# IBKR pacing: ~10s giữa các request
# 2 symbols × 2 TF × 2 năm ≈ 15 phút
# AGGRESSIVE (6 symbols) ≈ 45 phút
```

**Lưu ý IBKR pacing:**
- Max 60 historical data requests / 10 phút
- `IB_REQUEST_DELAY = 10s` giữa các request
- Nếu bị lỗi "pacing violation" → tăng `IB_REQUEST_DELAY` lên 15s trong `.env`

---

## 11. Chạy backtest

```bash
# Backtest 1 symbol
python3 main.py backtest --symbol EURUSD --tf 1h

# Backtest nhiều symbol
python3 main.py backtest --symbol EURUSD,GBPUSD --tf 1h

# Debug signal funnel
python3 main.py debug --symbol EURUSD --tf 1h --limit 1000

# Backtest với date range
python3 main.py backtest --symbol EURUSD --tf 1h --from 2025-01-01 --to 2026-01-01
```

**Target Forex backtest:**
- Profit Factor > 1.5
- Max Drawdown < 15%
- Winrate > 35% (SMC là low winrate, high RR)

---

## 12. Chạy live trading

### Trên Mac (local, test)
```bash
# Prerequisite: IB Gateway đang chạy trên Mac, port 7497
cd /Users/ngocdang/Claude/Projects/API_FOREX
source .venv/bin/activate

python3 main.py paper   # paper simulation
python3 main.py live    # live IBKR paper account
```

### Trên VPS 24/7 — dùng systemd (khuyến nghị)

Bot Forex chạy qua `forex-bot.service` — tự restart khi crash, tự start khi reboot VPS.

```bash
# Xem trạng thái
systemctl status forex-bot

# Start / Stop / Restart
systemctl start forex-bot
systemctl stop forex-bot
systemctl restart forex-bot   # dùng khi update code

# Xem log realtime
journalctl -u forex-bot -f

# Xem log file trực tiếp
tail -f /root/API_FOREX/logs/scalper.log
tail -f /root/API_FOREX/logs/scalper_errors.log
```

### Dừng hoàn toàn bot + Gateway (không auto-restart)
```bash
# Dừng tức thì (vẫn auto-restart nếu reboot):
systemctl stop forex-bot
systemctl stop ibgateway.service

# Disable luôn (không start khi reboot):
systemctl disable forex-bot
systemctl disable ibgateway.service
```

### Khởi động lại sau khi dừng
```bash
systemctl enable ibgateway.service forex-bot
systemctl start ibgateway.service
sleep 90                        # chờ Gateway login xong
ss -tlnp | grep 7497            # verify port 7497 đang listen
systemctl start forex-bot
```

### IBKR Maintenance / Gateway không connect được
- IBKR maintenance thường **18:00–18:30 ET (22:00–22:30 UTC)** hàng ngày
- Gateway tự restart lúc **00:30 UTC** mỗi đêm (daily session reset của IBKR)
- Nếu `ss -tlnp | grep 7497` trống → Gateway chưa login xong, đợi 60–90s
- Kiểm tra lỗi: `cat /root/Jts/launcher.log | tail -30`
  - `DISCONNECT_AUTHORIZATION_FAILED` → sai password hoặc đang maintenance
  - `loginFailFrequency.txt > 3` → account bị tạm lock, đợi vài phút
```

### Nội dung `/etc/systemd/system/forex-bot.service`
```ini
[Unit]
Description=Forex SMC Scalper Bot
After=network.target postgresql.service
OnFailure=forex-bot-alert.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/API_FOREX
ExecStart=/root/API_FOREX/.venv/bin/python3 main.py live
Restart=on-failure
RestartSec=30
StandardOutput=append:/root/API_FOREX/logs/scalper.log
StandardError=append:/root/API_FOREX/logs/scalper_errors.log

[Install]
WantedBy=multi-user.target
```

> **Trạng thái hiện tại (2026-06-15 Conv 10, CHG-FX-013):** `forex-bot.service` đang
> chạy `main.py live` — đặt lệnh THẬT qua IBKR API trên paper/demo account DUQ686904
> (port 7497, không phải tiền thật). Trước đó là `main.py paper` (chỉ mô phỏng nội bộ,
> không gửi lệnh qua IBKR). Đổi qua lại: `sudo sed -i 's/main.py live/main.py paper/'
> /etc/systemd/system/forex-bot.service` (hoặc ngược lại) rồi `systemctl daemon-reload
> && systemctl restart forex-bot`. Theo dõi account qua `scripts/check_account.py`
> (xem `BACKUP_CONTEXT.md` mục 12c) — tránh login Client Portal web khi bot đang chạy.

### Telegram alert khi service fail (`forex-bot-alert.service`)
Crash kiểu `ImportError`/syntax error xảy ra TRƯỚC khi code Python kịp gửi Telegram
"⚠️ IBKR Streaming Disconnected" (nằm trong `finally`, không chạy tới khi process bị
kill/SIGTERM hoặc die lúc import). Để bắt được các trường hợp này, dùng `OnFailure=`:

```ini
# /etc/systemd/system/forex-bot-alert.service
[Unit]
Description=Telegram alert when forex-bot.service fails (rate-limited)

[Service]
Type=oneshot
ExecStart=/bin/bash /root/API_FOREX/scripts/forex_bot_alert.sh
```

`scripts/forex_bot_alert.sh` gửi Telegram "🔴 forex-bot.service FAILED ..." qua curl,
cooldown 10 phút (lưu timestamp tại `/root/API_FOREX/.alert_cooldown`) để không spam khi
crash-loop. Setup:
```bash
chmod +x /root/API_FOREX/scripts/forex_bot_alert.sh
cp /root/API_FOREX/systemd/forex-bot-alert.service /etc/systemd/system/
systemctl daemon-reload
```

### Logrotate cho `logs/*.log`
`logs/scalper.log`, `logs/scalper_errors.log`, `logs/paper.log` tăng vô hạn nếu không
xoay → đầy disk theo thời gian. Setup `logrotate` (chạy tự động qua
`/etc/cron.daily/logrotate` có sẵn trên Ubuntu, không cần thêm cron job):

```bash
cp /root/API_FOREX/systemd/forex-bot-logrotate /etc/logrotate.d/forex-bot
logrotate -f /etc/logrotate.d/forex-bot   # test rotate ngay lần đầu (optional)
```

Config (`daily`, `rotate 14`, `maxsize 100M`, `compress`, `copytruncate`) — `copytruncate`
giúp rotate KHÔNG cần restart bot vì process Python giữ file descriptor mở liên tục.

### Update code lên VPS
```bash
# Chạy trên Mac terminal — LUÔN sync TOÀN BỘ thư mục (dấu / cuối cả 2 path bắt buộc),
# giữ nguyên cấu trúc cây con (config/, phase1_data/, ...)
rsync -avzc --exclude '.venv' --exclude '__pycache__' --exclude 'logs' --exclude '.env' \
    /Users/ngocdang/Claude/Projects/API_FOREX/ \
    root@69.12.65.42:/root/API_FOREX/

# Sau đó restart bot trên VPS
ssh root@69.12.65.42 "systemctl restart forex-bot"
```

> ⚠️ **KHÔNG** truyền nhiều file riêng lẻ kiểu `rsync ... fileA fileB dest/` mà thiếu
> `-R`/`--relative` — rsync sẽ copy "phẳng" theo basename vào `dest/`, làm sai vị trí
> file đích (vd `config/settings.py` → `/root/API_FOREX/settings.py`) và gây
> `ImportError` crash-loop dù rsync báo "thành công". Dùng `-c` (checksum) để rsync luôn
> so sánh nội dung thật, tránh bị "quick check" (size+mtime) bỏ qua file đã sửa.

> ⚠️ **LUÔN có `--exclude '.env'`** khi full-sync. `.env` trên Mac (dev local,
> `DB_USER=ngocdang`/`DB_PASSWORD=your_password`) khác hoàn toàn `.env` trên VPS
> (`DB_USER=forexbot`/`DB_PASSWORD=forexbot123`, xem CHG-VPS-002). Nếu quên exclude,
> `.env` VPS bị đè bằng bản Mac → bot mất kết nối DB (`password authentication failed
> for user "ngocdang"`), chỉ lộ ra sau khi bot đã chạy được vài phút (xem CHG-FX-006).

### Web Dashboard — monitor + đóng lệnh tay qua web (CHG-FX-015)

`phase9_live/web_dashboard.py` — trang web xem balance/position/open orders
(SL-TP)/recent fills, có nút **Đóng** position và **Cancel** order. Dùng
`IBKROrderManager(client_id_offset=40)` → clientId riêng (= IB_CLIENT_ID+40),
không đụng `forex-bot.service` (offset=20) hay `test_order.py` (offset=30).

**Setup lần đầu:**
```bash
# 1) Thêm DASHBOARD_USER / DASHBOARD_PASS vào .env trên VPS
cat >> /root/API_FOREX/.env << 'EOF'

DASHBOARD_USER=admin
DASHBOARD_PASS=<đặt password mạnh>
EOF

# 2) Cài fastapi/uvicorn (đã có trong requirements.txt)
cd /root/API_FOREX && source .venv/bin/activate
pip install -r requirements.txt

# 3) Mở port 8080 trên firewall (nếu dùng ufw)
ufw allow 8080/tcp
```

**Tạo systemd service** `/etc/systemd/system/forex-dashboard.service`:
```ini
[Unit]
Description=Forex Bot Web Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/API_FOREX
ExecStart=/root/API_FOREX/.venv/bin/uvicorn phase9_live.web_dashboard:app --host 0.0.0.0 --port 8080 --loop asyncio
Restart=on-failure
RestartSec=10
StandardOutput=append:/root/API_FOREX/logs/dashboard.log
StandardError=append:/root/API_FOREX/logs/dashboard_errors.log

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now forex-dashboard
systemctl status forex-dashboard
```

Truy cập: `http://<VPS_IP>:8080` — login Basic Auth bằng `DASHBOARD_USER`/`DASHBOARD_PASS`.

> ⚠️ Đây là HTTP (không phải HTTPS) — Basic Auth gửi credentials không mã hoá.
> Nếu cần bảo mật cao hơn, nên dùng SSH tunnel (`ssh -L 8080:localhost:8080
> root@69.12.65.42`) rồi truy cập `http://localhost:8080` thay vì mở port 8080
> ra internet, hoặc đặt Nginx reverse proxy + Let's Encrypt phía trước.

---

## 13. Kill Switch & Safe Mode

Bot tự động dừng khi:
- Daily loss ≥ 2% (CONSERVATIVE) / 4% (MODERATE)
- Max drawdown ≥ 10% / 15%
- 5 lệnh thua liên tiếp

```bash
# Kiểm tra trạng thái
grep "KILL\|disabled\|drawdown" logs/scalper.log

# Reset (đợi ngày mới UTC hoặc restart bot)
# daily_pnl reset tự động lúc 00:00 UTC
```

---

## 14. Deploy VPS từ A→Z (69.12.65.42)

> **VPS này chạy song song OKX bot + Forex bot.**
> PostgreSQL dùng chung 1 service, khác database: OKX=`scalper_db`, Forex=`forex_scalper_db` → không conflict.

---

### BƯỚC 1 — Chuẩn bị VPS (chỉ làm 1 lần)

```bash
# SSH vào VPS
ssh root@69.12.65.42

# Cài packages cần thiết
sudo apt update && sudo apt install -y \
    xvfb x11vnc default-jre \
    python3 python3-pip python3-venv \
    postgresql postgresql-contrib \
    git curl wget unzip

# Verify Java (IB Gateway cần Java 11+)
java -version
```

---

### BƯỚC 2 — Cài IB Gateway (chỉ làm 1 lần)

```bash
# Download IB Gateway
cd /tmp
wget "https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh"
chmod +x ibgateway-stable-standalone-linux-x64.sh

# Cần Xvfb để installer chạy GUI
Xvfb :1 -screen 0 1024x768x24 &
export DISPLAY=:1
./ibgateway-stable-standalone-linux-x64.sh -q

# Verify cài xong
ls /root/ibgateway/
```

---

### BƯỚC 3 — Login IB Gateway lần đầu qua VNC

> IB Gateway là Java app cần GUI để login. Dùng VNC để thao tác từ Mac.

```bash
# Trên VPS: start IB Gateway + VNC
Xvfb :1 -screen 0 1024x768x24 &
export DISPLAY=:1
/root/ibgateway/ibgateway &

# Tạo VNC password (nhập 2 lần khi hỏi)
x11vnc -storepasswd /root/.vnc_pass

# Start VNC server
x11vnc -display :1 -rfbauth /root/.vnc_pass -rfbport 5901 -bg -forever -quiet

# Verify VNC đang listen
ss -tlnp | grep 5901
```

```bash
# Trên Mac: connect VNC
# Dùng RealVNC Viewer (https://www.realvnc.com/en/connect/download/viewer/)
# Nhập: 69.12.65.42:5901 → nhập VNC password
# Trong GUI IB Gateway:
#   - API Type: IB API
#   - Trading Mode: Paper Trading
#   - Username: imatinyyy → copy-paste bằng Ctrl+V
#   - Click "Paper Log In"
# Configure → API → Settings:
#   - Bỏ tick "Read-Only API"
#   - Socket port: 7497
#   - Click OK
```

> Sau khi login xong, IB Gateway chạy ngầm trên Xvfb. Không cần VNC nữa cho đến khi reboot.

---

### BƯỚC 4 — Transfer code + Setup Python

```bash
# Chạy trên Mac terminal
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude 'logs' --exclude '.env' \
    /Users/ngocdang/Claude/Projects/API_FOREX/ \
    root@69.12.65.42:/root/API_FOREX/

# SSH vào VPS setup venv
ssh root@69.12.65.42
cd /root/API_FOREX
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install tzdata   # ← bắt buộc trên Ubuntu 24.04, thiếu = lỗi ZoneInfoNotFoundError
mkdir -p logs
```

---

### BƯỚC 5 — Setup PostgreSQL

```bash
sudo -u postgres psql << 'EOF'
CREATE USER forexbot WITH PASSWORD 'forexbot123';
CREATE DATABASE forex_scalper_db OWNER forexbot;
GRANT ALL PRIVILEGES ON DATABASE forex_scalper_db TO forexbot;
EOF

# Test kết nối
psql -U forexbot -d forex_scalper_db -h localhost -c "SELECT version();"
```

---

### BƯỚC 6 — Tạo file .env

```bash
cat > /root/API_FOREX/.env << 'EOF'
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=1
IB_PAPER_MODE=true

DB_HOST=localhost
DB_PORT=5432
DB_NAME=forex_scalper_db
DB_USER=forexbot
DB_PASSWORD=forexbot123

TRADING_PROFILE=MODERATE
ENTRY_TIMEFRAME=15m
SESSION_FILTER_ENABLED=true

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF
```

---

### BƯỚC 7 — Test kết nối IB Gateway

```bash
cd /root/API_FOREX && source .venv/bin/activate
python3 -c "
import asyncio
from ib_insync import IB
async def test():
    ib = IB()
    await ib.connectAsync('127.0.0.1', 7497, clientId=99)
    print('Connected:', ib.managedAccounts())
    ib.disconnect()
asyncio.run(test())
"
# Output mong đợi: Connected: ['DUQ686904']
```

---

### BƯỚC 8 — Download data lịch sử

```bash
cd /root/API_FOREX && source .venv/bin/activate
python3 main.py download
# Mất ~15-20 phút cho MODERATE profile (EURUSD, GBPUSD, USDJPY, XAUUSD)
```

---

### BƯỚC 9 — Setup systemd (chạy 24/7, tự restart)

```bash
cat > /etc/systemd/system/forex-bot.service << 'EOF'
[Unit]
Description=Forex SMC Scalper Bot
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/API_FOREX
ExecStart=/root/API_FOREX/.venv/bin/python3 main.py paper
Restart=on-failure
RestartSec=30
StandardOutput=append:/root/API_FOREX/logs/scalper.log
StandardError=append:/root/API_FOREX/logs/scalper_errors.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable forex-bot   # tự start khi reboot
systemctl start forex-bot
systemctl status forex-bot
```

> **Khi KYC live duyệt:** đổi `main.py paper` → `main.py live`, rồi `systemctl daemon-reload && systemctl restart forex-bot`

---

### Sau reboot VPS — không cần làm gì (Conv 2 — IBC auto-login)

✅ Từ khi cài IBC (mục 3), `ibgateway.service` tự start Xvfb + IB Gateway + auto-login sau mỗi lần reboot — VNC không bắt buộc, chỉ bật sẵn (port 5901) để xem GUI khi cần.

```bash
# Verify sau reboot (optional)
systemctl status ibgateway      # active (running)
ss -tlnp | grep 7497             # port API đã listen

# Start forex-bot (nếu chưa tự start)
systemctl status forex-bot
systemctl start forex-bot
```

---

### Reconnect tự động khi mất kết nối

- **OKX bot:** WebSocket watchdog tự reconnect khi mất kết nối (không cần can thiệp)
- **Forex bot (ib_insync):** tự reconnect TCP socket khi IB Gateway bị ngắt tạm thời
- **Systemd:** tự restart cả 2 bot nếu process crash (`Restart=on-failure`)
- **IB Gateway:** `ibgateway.service` (`Restart=always`) tự restart + IBC tự re-login nếu Gateway bị logout/crash — không cần VNC thủ công nữa
- **Candle gaps (`candles` table):** `run_paper()` chạy `_periodic_backfill_loop()` nền — mỗi giờ tự quét 2h gần nhất và fill candle bị thiếu (vd: do IB Gateway down giữa giờ), không cần restart bot. Xem mục "Periodic Backfill" bên dưới.

---

### Periodic Backfill (paper mode) — Conv 3 — 2026-06-12

**Vấn đề:** `BackfillService.run_all()` trước đây chỉ chạy 1 lần lúc bot start. Nếu IB Gateway mất kết nối tạm thời *sau khi* bot đã chạy (ví dụ lúc IBC chưa fix xong), gap trong `candles` table không bao giờ được tự fill — phải `systemctl restart forex-bot` thủ công.

**Fix:** thêm `_periodic_backfill_loop(db, lookback_hours=2, interval_s=3600)` trong `main.py`:
- Chạy nền qua `asyncio.create_task(...)` ngay trước `await collector.start()` trong `run_paper()`.
- Mỗi 3600s (1 giờ): mở `IBKRDownloader`, chạy `BackfillService.run_all(lookback_hours=2)` để quét + fill gap trong 2h gần nhất cho tất cả symbol × timeframe.
- Log: `[PeriodicBackfill] Checking last 2h for gaps ...` / `[PeriodicBackfill] Check complete`.

File liên quan: `main.py` (hàm `_periodic_backfill_loop`, gọi trong `run_paper()`), `phase1_data/backfill.py` (`BackfillService`).

> ℹ️ `run_live()` (`phase9_live/live_engine.py`) đã có gap-fill riêng: gap-fill 1 lần lúc start (lookback tính theo downtime) + `_backfill_gap()` reactive mỗi khi `on_candle` phát hiện candle bị nhảy gap — không cần thêm periodic loop cho live mode.

---

### Monitor thường ngày

```bash
# Status 2 bots
systemctl status forex-bot smc-live

# Log Forex realtime
journalctl -u forex-bot -f

# Chỉ xem lệnh vào/ra
grep -E "ENTRY|CLOSED|KILL|ERROR" /root/API_FOREX/logs/scalper.log | tail -20

# RAM
free -h
```

### Connect DB từ Mac

```bash
# Terminal Mac — tạo SSH tunnel
ssh -L 5433:localhost:5432 root@69.12.65.42 -N

# TablePlus / DBeaver: localhost:5433 | user: forexbot | pass: forexbot123 | db: forex_scalper_db
```

```sql
-- Paper trades gần nhất
SELECT symbol, side, entry_price, sl, tp, pnl, status, opened_at
FROM paper_trades ORDER BY opened_at DESC LIMIT 20;

-- Signal funnel hôm nay
SELECT stop_reason, COUNT(*) FROM candle_tracker_live
WHERE candle_time > NOW() - INTERVAL '24 hours'
GROUP BY stop_reason ORDER BY count DESC;
```

### Update code lên VPS

```bash
# Mac terminal
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude 'logs' --exclude '.env' \
    /Users/ngocdang/Claude/Projects/API_FOREX/ \
    root@69.12.65.42:/root/API_FOREX/

# Restart bot
ssh root@69.12.65.42 "systemctl restart forex-bot"
```

---

## 15. Debug khi bot không vào lệnh

### Bước 0: Health check nhanh (bot / IB Gateway / kết nối)

**1. Bot đang chạy?**
```bash
systemctl status forex-bot --no-pager | head -5
```
→ `Active: active (running)` + PID.

**2. IB Gateway đang chạy?**
```bash
systemctl status ibgateway --no-pager | head -5
ps aux | grep -i ibgateway | grep -v grep
```

**3. IB Gateway đã login + đang connect với bot?**
```bash
ss -tlnp | grep 7497      # LISTEN → Gateway đã login, mở API port
ss -tnp | grep 7497       # 2 dòng ESTAB → bot (python3) đã connect vào Gateway (java)
```

Hoặc check nhanh qua log:
```bash
tail -5 /root/API_FOREX/logs/scalper.log
grep "IBKR Streaming Connected" /root/API_FOREX/logs/scalper.log | tail -1
```

---

### Bước 1: Kiểm tra session filter
```bash
grep "session" logs/scalper.log | tail -20
# Nếu thấy "session_pre_session" hay "session_dead_zone" → đúng rồi, ngoài giờ
```

### Bước 2: Query stop_reason
```sql
SELECT stop_reason, COUNT(*) FROM candle_tracker_live
WHERE candle_time > NOW() - INTERVAL '24 hours'
GROUP BY stop_reason ORDER BY count DESC;
```

| stop_reason | Nguyên nhân | Fix |
|---|---|---|
| `session_pre_session` | Ngoài giờ giao dịch | Bình thường |
| `no_zone` | Không có FVG/OB gần giá | Thị trường trending, bình thường |
| `l1_trend_fail` | 1h trend = RANGE | Chờ trend rõ |
| `l3_liquidity_fail` | Chưa có sweep/CHoCH | Chờ liquidity event |
| `adx_low_XX` | ADX < 25 (15m only) | Market ranging |
| `l4_volume_fail` | Tick count thấp | Low liquidity period |

### Bước 3: Kiểm tra IB Gateway
```bash
python3 -c "
import asyncio
from ib_insync import IB
async def test():
    ib = IB()
    await ib.connectAsync('127.0.0.1', 7497, clientId=99)
    print('Connected:', ib.managedAccounts())
    ib.disconnect()
asyncio.run(test())
"
```

---

## 16. Khác biệt với API_OKX

| Aspect | API_OKX (Crypto) | API_FOREX |
|---|---|---|
| Broker | OKX | IBKR |
| API type | REST + WebSocket | TWS socket (ib_insync) |
| Real-time | OKX WS candle channel | IBKR reqRealTimeBars (5s) |
| Auth | HMAC-SHA256 | Không cần (socket local) |
| Needs local app | Không | ✅ IB Gateway phải chạy |
| Position size | Contracts | Units (100k = 1 lot) |
| Fees | Maker/Taker 0.02-0.04% | Spread (~1 pip) |
| Market hours | 24/7 | Mon–Fri (+ session filter) |
| Funding rate | Có | Không |
| Leverage | 10x futures | 20-30x Forex |
| Phases 2-5 | OKX version | Giống hệt (copy) |

---

## 17. Theo dõi & cải tiến tiếp theo

### IBKRDownloader connect timeout đơn lẻ (Conv 7 — 2026-06-13)

**Hiện tượng:** `_periodic_backfill_loop` (chạy mỗi giờ, dùng `IBKRDownloader` với
clientId riêng 1-3, KHÁC với streaming chính clientId 11) đôi khi connect fail cả
3/3 lần với message rỗng (`asyncio.TimeoutError`):

```
2026-06-13 16:22:07 | ERROR | phase1_data.ibkr_downloader:_connect:116 - IBKR connect attempt 1/3:
2026-06-13 16:22:20 | ERROR | phase1_data.ibkr_downloader:_connect:116 - IBKR connect attempt 2/3:
2026-06-13 16:22:33 | ERROR | phase1_data.ibkr_downloader:_connect:116 - IBKR connect attempt 3/3:
2026-06-13 16:22:33 | ERROR | __main__:_periodic_backfill_loop:349 - [PeriodicBackfill] error: Cannot connect to IB Gateway at 127.0.0.1:7497
```

**Đã check (16:22 case):**
- Streaming chính (clientId 11) KHÔNG bị ảnh hưởng — `ss -tnp | grep 7497` vẫn
  `ESTAB` cả 2 chiều xuyên suốt.
- `/tmp/ibc.log` không có gì bất thường quanh thời điểm đó (không login/2FA/reconnect).
- Các cycle trước/sau (13:21–15:21, và các cycle tiếp theo) đều chạy OK.
- Kết luận: 1 lần blip ngẫu nhiên (có thể do GC pause của Java hoặc network blip ngắn
  trên VPS), KHÔNG crash bot, KHÔNG mất data — bị catch exception và tự retry ở cycle
  giờ kế tiếp.

**Tại sao Telegram không báo:** `forex-bot-alert.service` (`OnFailure=`) chỉ trigger
khi `forex-bot.service` **fail hẳn** (process chết). Lỗi này chỉ là exception bị catch
bên trong 1 task con đang chạy — process vẫn `active (running)` → không trigger alert.
Đây là behavior **đã quyết định giữ nguyên** (không ảnh hưởng trading nên không cần
thêm alert).

**Cải tiến có thể làm SAU nếu lỗi này lặp lại thường xuyên (vd vài lần/ngày):**
1. Tăng timeout connect trong `phase1_data/ibkr_downloader.py` `_connect()` (vd 4s →
   8s) để giảm khả năng bị timeout do CPU/network blip ngắn.
2. Thêm retry sớm hơn trong `_periodic_backfill_loop` nếu connect fail toàn bộ 3/3
   (thử lại sau vài phút thay vì đợi 1h).
3. **Restart Gateway định kỳ** (vd 1 lần/ngày, giờ ít hoạt động) qua IBC
   `autoRestartTime` trong `/opt/ibc/config.ini` — phòng memory leak Java tích lũy theo
   thời gian (nguyên nhân khả nghi gây timeout 16:22). User đã đặt restart 20:00 nhưng
   chưa verify được hiệu lực (không thấy log disconnect/reconnect quanh giờ đó — cần
   check lại timezone của `autoRestartTime` so với giờ UTC của VPS).

**Cách theo dõi:** nếu thấy `IBKR connect attempt` ERROR xuất hiện > 1 lần/ngày trong
`logs/scalper.log`, quay lại làm cải tiến #1/#2 ở trên.

---

### Candle bị mất sau weekend reopen — CHG-FX-008 + CHG-FX-009 (Conv 8-9 — 2026-06-14/15)

**Hiện tượng:** Sau khi thị trường mở lại đầu tuần (Sunday ~21:00 UTC), candle mới
KHÔNG được lưu vào `candles` table — cả live streaming và backfill đều bị ảnh hưởng.
Log "Bar closed" vẫn xuất hiện đều (chứng minh stream còn sống) nhưng không có
"Candle saved", và `_periodic_backfill_loop`/startup backfill báo "Backfill complete:
0 candles" dù query DB thấy `MAX(open_time)` vẫn dừng ở Friday.

**Đã check & fix (2 lớp bug riêng biệt):**

1. **CHG-FX-008** (`phase1_data/ibkr_collector.py`): `_process_candle()` được
   schedule qua `asyncio.ensure_future()` nhưng task lỗi bị "biến mất" âm thầm sau
   reconnect — fix bằng done-callback `_log_task_error` để log lỗi task con.

2. **CHG-FX-009** (`phase1_data/validator.py`) — **root cause chính**:
   `is_weekend_candle()` check `.weekday()`/`.hour` của `open_time` nhưng `open_time`
   từ IBKR có tzinfo là giờ Eastern (-04:00), KHÔNG phải UTC. Candle ngay sau reopen
   (vd 22:00 UTC Sunday = 18:00 -04:00 Sunday, `hour<21`) bị tính nhầm là weekend
   candle → `validate_candle()` loại bỏ âm thầm (chỉ log ở mức `debug`). Bug này ảnh
   hưởng CẢ live stream (`_process_candle`) VÀ backfill (`fetch_range` cũng gọi
   `validate_candles`). Fix: convert `open_time` sang UTC (`.astimezone(timezone.utc)`)
   trước khi check.

**Đã confirm fix CHG-FX-009 hoạt động** (2026-06-15 ~22:30 UTC): DB có candle mới
21:15-22:00 UTC cho EURUSD/GBPUSD/USDJPY (15m+1h) và XAUUSD (15m).

**Còn đang theo dõi (chưa kết luận được):**

1. **XAUUSD 1h vẫn 0 candles** dù đã fix CHG-FX-009 (XAUUSD 15m đã có data, 1h thì
   không) — nghi do khác biệt data pipeline IBKR cho contract `CMDTY/SMART` (XAUUSD)
   so với `CASH/IDEALPRO` (các pair Forex). Cần thêm thời gian/log để xác nhận liệu
   đây là lag tạm thời hay vấn đề thường trực với contract loại này.

2. **Candle 1h mới có `open_time=21:15 UTC`** (lệch 15 phút so với giờ tròn) cho
   EURUSD/GBPUSD/USDJPY — chưa rõ candle 1h tiếp theo sẽ giữ lệch (23:15 UTC) hay tự
   realign về giờ tròn (22:00/23:00 UTC).

**Cách theo dõi:**
```bash
# XAUUSD 1h có candle mới chưa?
grep "Candle saved: XAUUSD 1h" /root/API_FOREX/logs/paper.log | tail -5

# Candle 1h tiếp theo của EURUSD đóng ở open_time nào — 23:15 (offset) hay 23:00 (realign)?
grep "Bar closed: EURUSD 1h" /root/API_FOREX/logs/paper.log | tail -5
```
Nếu XAUUSD 1h vẫn 0 sau vài giờ nữa, kiểm tra lại `_make_forex_contract()` trong
`ibkr_downloader.py` (contract `CMDTY/SMART`) — có thể cần `whatToShow="TRADES"` thay
`"MIDPOINT"` cho commodity, hoặc IBKR đơn giản là không có 1h bars cho contract này.

---

*GUIDELINE.md — tạo: 2026-06-09 (Conv 1 — Forex)*
