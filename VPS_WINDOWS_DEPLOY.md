# Windows VPS Deployment Guide — MT5 SMC Scalper

## Prerequisites

| Software | Link | Note |
|---|---|---|
| Python 3.10+ (64-bit) | python.org/downloads | Must be 64-bit |
| MetaTrader 5 Terminal | metatrader5.com/en/download | Install + login to broker |
| PostgreSQL 16 | postgresql.org/download/windows | Set password during install |
| Git (optional) | git-scm.com | For pulling updates |

## Step 1 — MT5 Terminal Setup

1. Install MT5, login to your broker account (demo recommended first)
2. Enable DLL imports: **Tools → Options → Expert Advisors → Allow DLL imports ✓**
3. Keep MT5 terminal running — Python API requires it

## Step 2 — Install Python Dependencies

```bat
cd C:\bots\API_MT5
pip install -r requirements.txt
pip install MetaTrader5   # Windows only — NOT in requirements.txt by default
```

## Step 3 — PostgreSQL Setup

```bat
# In psql or pgAdmin:
CREATE DATABASE mt5_scalper_db;
CREATE USER postgres WITH PASSWORD 'yourpassword';
GRANT ALL ON DATABASE mt5_scalper_db TO postgres;
```

## Step 4 — Configure .env

```bat
copy .env.example .env
notepad .env
```

Key settings:
```
MT5_LOGIN=12345678
MT5_PASSWORD=broker_password
MT5_SERVER=ICMarkets-Demo        # check exact server name in MT5
MT5_DEMO_MODE=true
DB_PASSWORD=yourpgpassword
TRADING_PROFILE=CONSERVATIVE
```

## Step 5 — Download Historical Data

```bat
python3 main.py download
```

## Step 6 — Run Backtest

```bat
python3 main.py backtest
```

## Step 7 — Live Trading

```bat
python3 main.py live
```

---

## Auto-Start with Task Scheduler

1. Open **Task Scheduler** → Create Basic Task
2. Trigger: At startup / Daily at 00:05
3. Action: Start a program
   - Program: `C:\Python312\python.exe`
   - Arguments: `C:\bots\API_MT5\main.py live`
   - Start in: `C:\bots\API_MT5`
4. Check "Run whether user is logged on or not"

Alternative — NSSM (Non-Sucking Service Manager):
```bat
nssm install mt5-scalper "C:\Python312\python.exe" "C:\bots\API_MT5\main.py live"
nssm set mt5-scalper AppDirectory C:\bots\API_MT5
nssm start mt5-scalper
```

---

## Web Dashboard

```bat
uvicorn phase9_live.web_dashboard:app --host 0.0.0.0 --port 8000
```

Access: `http://YOUR_VPS_IP:8000` (login: admin / changeme)

---

## Broker Symbol Suffixes

Some brokers add suffixes. Set in `.env`:

| Broker | EURUSD | XAUUSD |
|---|---|---|
| IC Markets | EURUSD | XAUUSD |
| Pepperstone | EURUSD | XAUUSD |
| XM | EURUSDm | XAUUSDm |
| FBS | EURUSD | XAUUSD |
| Exness | EURUSDr | XAUUSDr |

Example `.env` for XM:
```
MT5_SYM_EURUSD=EURUSDm
MT5_SYM_XAUUSD=XAUUSDm
```

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `initialize() failed` | MT5 not running | Open MT5 terminal first |
| `login() failed 10013` | Wrong credentials | Check MT5_LOGIN/PASSWORD/SERVER |
| `copy_rates_from_pos None` | Symbol not in Market Watch | Right-click symbol → Show in Market Watch |
| `ORDER_TYPE_BUY error` | AutoTrading disabled | Click AutoTrading button in MT5 toolbar |
| DB connection refused | PostgreSQL not running | `net start postgresql-x64-16` |
| `MetaTrader5 not found` | Wrong Python arch | Install 64-bit Python + pip install MetaTrader5 |

---

## Mac / Linux (Local Testing)

Mac uses yfinance automatically — no MT5 needed:

```bash
# Install deps
pip install -r requirements.txt

# PostgreSQL
brew install postgresql@16
brew services start postgresql@16
createdb mt5_scalper_db

# Copy and edit .env
cp .env.example .env

# Download data (yfinance)
python3 main.py download

# Backtest
python3 main.py backtest

# Paper trading (⚠️ data delay ~1-15 min)
python3 main.py paper

# Live trading NOT available on Mac
# python main.py live   ← will print error and exit
```
