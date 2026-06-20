# VPS Deployment Guide — Forex SMC Scalper Bot
> Ubuntu 20.04 / 22.04 LTS
> IB Gateway headless + IBC auto-login + PostgreSQL + systemd
> **Cập nhật:** 2026-06-09 (Conv 2)

---

## Tổng quan kiến trúc VPS

```
VPS Ubuntu
├── Xvfb :1          ← virtual display (IB Gateway cần GUI)
├── IBC              ← auto-login IB Gateway (không cần gõ tay)
├── IB Gateway       ← kết nối IBKR server, port 7497
├── PostgreSQL       ← lưu candles + trades
└── forex-bot        ← python3 main.py paper/live
```

---

## Bước 1 — Chuẩn bị server

```bash
# Update + install packages
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    xvfb \
    x11vnc \
    default-jre \
    python3 python3-pip python3-venv \
    postgresql postgresql-contrib \
    git curl wget unzip \
    screen tmux \
    net-tools

# Verify Java (IB Gateway yêu cầu Java 11+)
java -version
```

**Spec tối thiểu:**
- RAM: 2GB (IB Gateway ~500MB + bot ~200MB + PostgreSQL ~200MB)
- CPU: 1 vCPU đủ
- Storage: 10GB
- OS: Ubuntu 20.04 hoặc 22.04

---

## Bước 2 — Cài IB Gateway

```bash
# Download IB Gateway (stable version)
cd /tmp
wget "https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh"
chmod +x ibgateway-stable-standalone-linux-x64.sh

# Install headless (DISPLAY=:1 cần Xvfb chạy trước)
Xvfb :1 -screen 0 1024x768x24 &
export DISPLAY=:1
./ibgateway-stable-standalone-linux-x64.sh -q   # -q = quiet/non-interactive

# Default install path: ~/Jts/ibgateway/<version>/
ls ~/Jts/ibgateway/
```

---

## Bước 3 — Cài IBC (Auto-Login)

IBC = IBController — tự động nhập username/password khi IB Gateway khởi động.
Không có IBC → phải login tay mỗi 24h khi session expire.

```bash
# Download IBC
cd /opt
sudo mkdir ibc && sudo chown $USER:$USER ibc
cd ibc
wget "https://github.com/IbcAlpha/IBC/releases/latest/download/IBCLinux-3.19.0.zip"
unzip IBCLinux-3.19.0.zip
chmod +x *.sh scripts/*.sh

# Config file
cp config.ini.sample config.ini
nano config.ini
```

**Chỉnh sửa `config.ini`:**
```ini
# Tài khoản IBKR
IbLoginId=YOUR_IBKR_USERNAME
IbPassword=YOUR_IBKR_PASSWORD

# Paper trading
TradingMode=paper

# Tắt 2FA (dùng trusted device trên VPS)
# Nếu có 2FA → dùng IbLoginId2=... hoặc tắt 2FA trên account IBKR

# Không hiện dialog confirm
AcceptIncomingConnectionAction=accept
ExistingSessionDetectedAction=primary

# IB Gateway settings
ReadonlyLogin=no
OverrideProxyDefaults=yes
ForceTwoFactorAuth=no
```

**Script khởi động IBC:**
```bash
# /opt/ibc/start_ibgateway.sh
#!/bin/bash
export DISPLAY=:1

# Path tới IB Gateway
IB_GATEWAY_PATH="/root/Jts/ibgateway/1030"   # ← đổi version number

/opt/ibc/scripts/ibcstart.sh \
    /opt/ibc/config.ini \
    "$IB_GATEWAY_PATH" \
    "" \
    "paper"
```

```bash
chmod +x /opt/ibc/start_ibgateway.sh
```

---

## Bước 4 — Transfer project

```bash
# Option A: git clone (nếu có repo)
cd /root
git clone https://github.com/YOUR_USER/API_FOREX.git
cd API_FOREX

# Option B: rsync từ Mac
# (chạy trên Mac)
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude 'logs/*' \
    /Users/ngocdang/Claude/Projects/API_FOREX/ \
    root@YOUR_VPS_IP:/root/API_FOREX/
```

---

## Bước 5 — Setup Python environment

```bash
cd /root/API_FOREX
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Verify
python3 -c "import ib_insync; print('ib_insync OK')"
python3 -c "import asyncpg; print('asyncpg OK')"
```

---

## Bước 6 — Setup PostgreSQL

```bash
# Tạo user + database
sudo -u postgres psql << 'EOF'
CREATE USER forexbot WITH PASSWORD 'YOUR_DB_PASSWORD';
CREATE DATABASE forex_scalper_db OWNER forexbot;
GRANT ALL PRIVILEGES ON DATABASE forex_scalper_db TO forexbot;
EOF

# Test connection
psql -U forexbot -d forex_scalper_db -h localhost -c "SELECT version();"
```

---

## Bước 7 — Tạo file .env

```bash
nano /root/API_FOREX/.env
```

```env
# IBKR
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=1
IB_PAPER_MODE=true

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=forex_scalper_db
DB_USER=forexbot
DB_PASSWORD=YOUR_DB_PASSWORD

# Trading
TRADING_PROFILE=MODERATE
ENTRY_TIMEFRAME=15m
SESSION_FILTER_ENABLED=true

# Telegram (optional nhưng khuyến khích)
TELEGRAM_BOT_TOKEN=YOUR_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
```

---

## Bước 8 — Test thủ công trước khi setup service

```bash
# Terminal 1: Start Xvfb
Xvfb :1 -screen 0 1024x768x24 &

# Terminal 2: Start IB Gateway via IBC
export DISPLAY=:1
/opt/ibc/start_ibgateway.sh

# Chờ 30-60 giây, check log
tail -f /opt/ibc/logs/ibc.log

# Terminal 3: Test IB Gateway connection
cd /root/API_FOREX
source .venv/bin/activate
python3 -c "
import asyncio
from ib_insync import IB
async def test():
    ib = IB()
    await ib.connectAsync('127.0.0.1', 7497, clientId=99)
    print('✅ Connected:', ib.managedAccounts())
    ib.disconnect()
asyncio.run(test())
"

# Nếu connect OK → chạy download data
python3 main.py download

# Test paper trading
python3 main.py paper
```

---

## Bước 9 — Systemd services (auto-start on reboot)

### Service 1: Xvfb

```bash
sudo nano /etc/systemd/system/xvfb.service
```

```ini
[Unit]
Description=Virtual Display (Xvfb)
After=network.target

[Service]
ExecStart=/usr/bin/Xvfb :1 -screen 0 1024x768x24
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Service 2: IB Gateway (via IBC)

```bash
sudo nano /etc/systemd/system/ibgateway.service
```

```ini
[Unit]
Description=IB Gateway (via IBC)
After=xvfb.service
Requires=xvfb.service

[Service]
Environment=DISPLAY=:1
User=root
ExecStart=/opt/ibc/start_ibgateway.sh
Restart=always
RestartSec=30
# IB Gateway tự restart sau 24h (session expire) → systemd restart lại
StartLimitInterval=0

[Install]
WantedBy=multi-user.target
```

### Service 3: Forex Bot

```bash
sudo nano /etc/systemd/system/forex-bot.service
```

```ini
[Unit]
Description=Forex SMC Scalper Bot
After=ibgateway.service postgresql.service
Requires=ibgateway.service

[Service]
User=root
WorkingDirectory=/root/API_FOREX
Environment=DISPLAY=:1
ExecStartPre=/bin/sleep 30
ExecStart=/root/API_FOREX/.venv/bin/python3 main.py paper
Restart=always
RestartSec=15
StandardOutput=append:/root/API_FOREX/logs/scalper.log
StandardError=append:/root/API_FOREX/logs/scalper.log

[Install]
WantedBy=multi-user.target
```

### Enable tất cả

```bash
sudo systemctl daemon-reload
sudo systemctl enable xvfb ibgateway forex-bot
sudo systemctl start xvfb
sleep 5
sudo systemctl start ibgateway
sleep 60   # chờ IB Gateway login xong
sudo systemctl start forex-bot

# Kiểm tra status
sudo systemctl status xvfb ibgateway forex-bot
```

---

## Bước 10 — Monitor

```bash
# Log bot
tail -f /root/API_FOREX/logs/scalper.log

# Chỉ xem signal/trade
grep -E "Order placed|ENTRY|CLOSED|KILL|ERROR" /root/API_FOREX/logs/scalper.log | tail -20

# Status services
sudo systemctl status forex-bot

# Restart bot (khi update code)
sudo systemctl restart forex-bot

# Xem paper trades trong DB
psql -U forexbot -d forex_scalper_db -h localhost -c "
SELECT symbol, side, entry_price, sl, tp, size, pnl, status, opened_at
FROM paper_trades ORDER BY opened_at DESC LIMIT 20;"
```

---

## Bước 11 — Switch sang Live (khi KYC duyệt)

```bash
# 1. Đổi .env
nano /root/API_FOREX/.env
# IB_PAPER_MODE=false
# IB_PORT=7496

# 2. Đổi IBC config
nano /opt/ibc/config.ini
# TradingMode=live

# 3. Đổi bot mode
sudo nano /etc/systemd/system/forex-bot.service
# ExecStart=... main.py live   ← đổi paper → live

# 4. Restart
sudo systemctl daemon-reload
sudo systemctl restart ibgateway
sleep 60
sudo systemctl restart forex-bot
```

---

## Troubleshoot thường gặp

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `Cannot connect to IB Gateway` | Gateway chưa start xong | Tăng `ExecStartPre=/bin/sleep 60` trong forex-bot.service |
| `Xvfb: error` | Port :1 đang dùng | `pkill Xvfb` rồi start lại |
| `pacing violation` | Quá nhiều IBKR request | Tăng `IB_REQUEST_DELAY=15` trong .env |
| IB Gateway log out sau 24h | Session expire | Systemd tự restart → IBC login lại |
| Bot crash | Exception chưa handle | Check log, fix code, `systemctl restart forex-bot` |

---

## Quick commands reference

```bash
# Start tất cả
sudo systemctl start xvfb ibgateway && sleep 60 && sudo systemctl start forex-bot

# Stop tất cả
sudo systemctl stop forex-bot ibgateway xvfb

# Restart chỉ bot (sau khi update code)
sudo systemctl restart forex-bot

# Xem log realtime
journalctl -u forex-bot -f

# Check IB Gateway đang connect không
/root/API_FOREX/.venv/bin/python3 -c "
import asyncio; from ib_insync import IB
async def t():
    ib=IB(); await ib.connectAsync('127.0.0.1',7497,clientId=99)
    print('OK:', ib.managedAccounts()); ib.disconnect()
asyncio.run(t())"
```

---

*VPS_DEPLOY.md — tạo: 2026-06-09 (Conv 2)*
