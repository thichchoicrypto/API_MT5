# Windows VPS Deployment Guide — MT5 SMC Scalper

## VPS Specs (tested)

| Item | Value |
|---|---|
| Provider | DatabaseMart |
| OS | Windows Server 2025 Standard x64 |
| CPU | 2 cores (Intel Xeon Gold 6144 @ 3.5GHz) |
| RAM | 4GB |
| Disk | 60GB SSD |
| Network | 100Mbps Unmetered |
| Price | $5.80/month |
| Location | Dallas, TX (low latency to US brokers) |

---

## Prerequisites

| Software | Version | Install method |
|---|---|---|
| Python | 3.11 (64-bit) | `winget install Python.Python.3.11 --source winget` |
| Git | latest | `winget install Git.Git --source winget` |
| PostgreSQL | 16 | `winget install PostgreSQL.PostgreSQL.16 --source winget` |
| MetaTrader 5 | 5836+ | Download from broker website |

> **Note:** Always add `--source winget` on Windows Server — msstore source often fails with certificate error.

---

## Step 1 — Connect to VPS from Mac

Install **Microsoft Remote Desktop** from Mac App Store, then:
- Add new PC → IP: `YOUR_VPS_IP`
- Username: `Administrator`
- Password: from DatabaseMart email

---

## Step 2 — Install Software (PowerShell as Administrator)

```powershell
# Python 3.11
winget install Python.Python.3.11 --source winget --accept-source-agreements --accept-package-agreements

# Git
winget install Git.Git --source winget --accept-source-agreements --accept-package-agreements

# PostgreSQL 16
winget install PostgreSQL.PostgreSQL.16 --source winget --accept-source-agreements --accept-package-agreements
```

> After installing, close and reopen PowerShell to refresh PATH.

Verify:
```powershell
python --version   # Python 3.11.x
git --version
psql --version
```

---

## Step 3 — PostgreSQL Setup

```powershell
# Check service is running
Get-Service postgresql-x64-16

# Start if not running
Start-Service postgresql-x64-16
```

### Reset postgres password (if forgotten)

1. Stop service: `Stop-Service postgresql-x64-16`
2. Edit `C:\Program Files\PostgreSQL\16\data\pg_hba.conf`
   - Change `scram-sha-256` → `trust` for IPv4 and IPv6 local lines
3. Start service: `Start-Service postgresql-x64-16`
4. Reset password:
   ```powershell
   psql -U postgres -h 127.0.0.1
   # In psql:
   ALTER USER postgres WITH PASSWORD 'Postgres123';
   \q
   ```
5. Revert pg_hba.conf: change `trust` back to `scram-sha-256`
6. Restart: `Restart-Service "postgresql-x64-16"`

### Create database and user

```powershell
psql -U postgres -h 127.0.0.1 -c "CREATE USER ngocdang WITH PASSWORD 'Ngocdang123';"
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE mt5_scalper_db OWNER ngocdang;"
psql -U postgres -h 127.0.0.1 -c "GRANT ALL PRIVILEGES ON DATABASE mt5_scalper_db TO ngocdang;"
```

> **IMPORTANT:** Do NOT use `@` in DB_PASSWORD — it breaks the PostgreSQL connection URL.
> Use: `Ngocdang123` not `Ngocdang@123`

---

## Step 4 — Install MT5 Terminal (ICMarkets)

```powershell
# Download ICMarkets MT5 installer
Invoke-WebRequest -Uri "https://download.mql5.com/cdn/web/icmarkets.group.sc/mt5/icmarketssc5setup.exe" -OutFile "$env:TEMP\mt5setup.exe"
Start-Process "$env:TEMP\mt5setup.exe" -Wait
```

MT5 installs to: `C:\Program Files\MetaTrader 5\terminal64.exe`

### Login to broker account

1. Open MT5 Terminal
2. **File** → **Open an Account**
3. Search for **"IC Markets"** → select **Raw Trading Ltd (ICMarketsSC-MT5)**
4. Select **ICMarketsSC-Demo** server
5. Create new demo account OR login with existing credentials
6. Verify: bottom of terminal shows account number and balance

### Enable algorithmic trading

- **Tools** → **Options** → **Expert Advisors**
- Check ✅ **Allow algorithmic trading**
- Check ✅ **Allow DLL imports**
- Click **OK**

> **IMPORTANT:** MT5 Terminal must be running and logged in for Python API to work.
> The Python MT5 library connects via IPC (local named pipe) — it does NOT connect directly to the broker.

---

## Step 5 — Clone Project

```powershell
git clone https://github.com/thichchoicrypto/API_MT5.git C:\Projects\API_MT5
cd C:\Projects\API_MT5
```

### Setup Python virtual environment

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Step 6 — Configure .env

```powershell
notepad C:\Projects\API_MT5\.env
```

```env
DATA_SOURCE=MT5
DATA_PROVIDER=MT5
MT5_ENABLED=true

MT5_LOGIN=52926435
MT5_PASSWORD=YOUR_MT5_PASSWORD
MT5_SERVER=ICMarketsSC-Demo

DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=mt5_scalper_db
DB_USER=ngocdang
DB_PASSWORD=Ngocdang123

TRADING_PROFILE=AGGRESSIVE
```

> Use `DB_HOST=127.0.0.1` not `localhost` — Windows may fail to resolve `localhost` for asyncpg.

---

## Step 7 — Test Connections

### Test MT5 connection

```powershell
cd C:\Projects\API_MT5
venv\Scripts\activate
python -c "
import MetaTrader5 as mt5
from dotenv import load_dotenv
import os
load_dotenv()
mt5.initialize(path='C:\\Program Files\\MetaTrader 5\\terminal64.exe')
login = mt5.login(int(os.getenv('MT5_LOGIN')), os.getenv('MT5_PASSWORD'), os.getenv('MT5_SERVER'))
print('Connected:', login)
print('Error:', mt5.last_error())
info = mt5.account_info()
print('Balance:', info.balance if info else 'N/A')
mt5.shutdown()
"
```

Expected output:
```
Connected: True
Error: (1, 'Success')
Balance: 20000.0
```

### Test DB connection

```powershell
python -c "
import asyncio
from dotenv import load_dotenv
load_dotenv()
from phase1_data.database import Database

async def test():
    db = Database()
    await db.connect()
    print('DB connected OK')
    await db.disconnect()

asyncio.run(test())
"
```

---

## Step 8 — Download Historical Data

MT5 Terminal must be open and logged in first.

```powershell
cd C:\Projects\API_MT5
venv\Scripts\activate
python main.py download
```

Downloads 7 symbols × 2 timeframes (15m + 1h) × 2 years history.
Estimated time: 15-30 minutes.

Symbols (AGGRESSIVE profile): `EURUSD, GBPUSD, USDJPY, XAUUSD, USDCAD, AUDUSD, EURJPY`

---

## Step 9 — Export Data to CSV (for Mac backtest)

```powershell
python tools/export_candles.py --dir C:\Projects\API_MT5\export_data
```

Then copy CSV files to Mac:

**Option A — SCP from Mac terminal:**
```bash
scp -r Administrator@YOUR_VPS_IP:C:/Projects/API_MT5/export_data ~/Downloads/mt5_data/
```

**Option B — Copy via Remote Desktop:**
- Right-click export_data folder → Copy
- Paste on Mac shared folder in Remote Desktop session

---

## Step 10 — Import Data on Mac

```bash
cd /Users/ngocdang/Claude/Projects/API_MT5
python3 tools/import_candles.py --dir ~/Downloads/mt5_data/
```

Then run backtest:
```bash
python3 main.py backtest
```

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `Terminal: Authorization failed` | MT5 Terminal not open | Open MT5 and login first |
| `No IPC connection` | MT5 not running | `Start-Process "C:\Program Files\MetaTrader 5\terminal64.exe"` |
| `getaddrinfo failed` | `localhost` DNS fail | Use `DB_HOST=127.0.0.1` in .env |
| `password authentication failed` | Wrong DB password or `@` in password | Remove `@` from DB_PASSWORD |
| `Cannot import MT5_ENABLED` | Missing var in settings.py | Add `MT5_ENABLED = os.getenv("MT5_ENABLED", "true").lower() == "true"` to config/settings.py |
| `winget msstore error` | Certificate issue | Add `--source winget` flag |
| `requirements.txt not found` | Encoding issue or clone incomplete | Re-clone repo: `Remove-Item -Recurse -Force API_MT5` then `git clone ...` |
| `UnicodeDecodeError cp1252` | Special chars in requirements.txt | Use ASCII-only characters in requirements.txt (no `═`, `─` etc.) |
| MT5 server only shows MetaQuotes-Demo | Wrong server selected | File → Open an Account → search "IC Markets" → select Raw Trading Ltd |
| `authorization on MetaQuotes-Demo failed` | MT5 logged into wrong server | Re-login via File → Login to Trade Account, select ICMarketsSC-Demo |

---

## Auto-Start with Task Scheduler

1. Open **Task Scheduler** → **Create Basic Task**
2. Trigger: At startup (delay 2 min to let MT5 start)
3. Action: Start a program
   - Program: `C:\Projects\API_MT5\venv\Scripts\python.exe`
   - Arguments: `C:\Projects\API_MT5\main.py live`
   - Start in: `C:\Projects\API_MT5`
4. Check **"Run whether user is logged on or not"**

> MT5 Terminal must also auto-start. Add it to Task Scheduler separately with earlier trigger.

---

## Broker Symbol Info

| Broker | Server (Demo) | EURUSD | XAUUSD |
|---|---|---|---|
| IC Markets SC | ICMarketsSC-Demo | EURUSD | XAUUSD |
| IC Markets (Global) | ICMarkets-Demo | EURUSD | XAUUSD |
| Pepperstone | Pepperstone-Demo | EURUSD | XAUUSD |
| XM | XMGlobal-Demo | EURUSDm | XAUUSDm |
| Exness | Exness-Demo | EURUSDr | XAUUSDr |

---

## Data Flow Summary

```
ICMarkets Broker
      ↓ (market data)
MT5 Terminal (Windows VPS, always running)
      ↓ (IPC / named pipe)
Python MT5 API (mt5_downloader.py)
      ↓
PostgreSQL DB (mt5_scalper_db)
      ↓
export_candles.py → CSV files
      ↓ (SCP / copy)
Mac: import_candles.py → PostgreSQL DB
      ↓
main.py backtest → Results
```
