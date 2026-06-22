"""
Global configuration for the Forex SMC Scalper Bot — MT5 Edition.
Data source : MetaTrader 5 (Windows) / yfinance (Mac/Linux)
Order source: MetaTrader 5 Python API (Windows only)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRADING PROFILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CONSERVATIVE  — 0.5% risk, 2 pairs,  ~2%/tháng,  DD ~2%
  MODERATE      — 1.0% risk, 4 pairs,  ~5%/tháng,  DD ~5%
  AGGRESSIVE    — 3.0% risk, 7 pairs,  ~12%/tháng, DD ~15%

OS auto-detect:
  Mac/Linux → yfinance  (download + paper trading, không cần broker)
  Windows   → MT5       (download + live trading, cần MT5 terminal)
"""
import os
import platform as _platform
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# TRADING PROFILE
# ─────────────────────────────────────────────
PROFILE = os.getenv("TRADING_PROFILE", "CONSERVATIVE")

_PROFILES = {
    "CONSERVATIVE": {
        "symbols":            ["EURUSD", "GBPUSD"],
        "risk_per_trade":     0.005,
        "max_daily_loss":     0.02,
        "max_drawdown":       0.10,
        "max_open_positions": 2,
        "max_leverage":       20,
    },
    "MODERATE": {
        "symbols":            ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
        "risk_per_trade":     0.01,
        "max_daily_loss":     0.04,
        "max_drawdown":       0.15,
        "max_open_positions": 2,
        "max_leverage":       30,
    },
    "AGGRESSIVE": {
        "symbols":            ["GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "EURJPY", "GBPJPY"],
        "risk_per_trade":     0.03,
        "max_daily_loss":     0.06,
        "max_drawdown":       0.15,
        "max_open_positions": 2,
        "max_leverage":       30,
    },
}

_p = _PROFILES.get(PROFILE, _PROFILES["CONSERVATIVE"])

# ─────────────────────────────────────────────
# OS AUTO-DETECT
# ─────────────────────────────────────────────
_os = _platform.system()   # "Darwin" | "Windows" | "Linux"
IS_WINDOWS = _os == "Windows"

# DATA_SOURCE: "MT5" = MetaTrader5 (Windows), "YFINANCE" = yfinance (Mac/Linux)
DATA_SOURCE = os.getenv(
    "DATA_SOURCE",
    "MT5" if IS_WINDOWS else "YFINANCE"
)

# ─────────────────────────────────────────────
# METATRADER 5  (Windows VPS only)
# MT5 terminal phải đang chạy trên cùng máy.
# Download: https://www.metatrader5.com/en/download
# pip install MetaTrader5
# ─────────────────────────────────────────────
MT5_ENABLED   = os.getenv("MT5_ENABLED", "true").lower() == "true"
MT5_LOGIN     = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD  = os.getenv("MT5_PASSWORD", "")
MT5_SERVER    = os.getenv("MT5_SERVER", "")
MT5_PATH      = os.getenv("MT5_PATH", "")   # để trống = tự detect
MT5_DEMO_MODE = os.getenv("MT5_DEMO_MODE", "true").lower() == "true"

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ─────────────────────────────────────────────
# DATABASE
# Mac:  brew install postgresql@16 && brew services start postgresql@16
#       createdb mt5_scalper_db
# Win:  https://www.postgresql.org/download/windows/
# ─────────────────────────────────────────────
DB_HOST      = os.getenv("DB_HOST", "localhost")
DB_PORT      = int(os.getenv("DB_PORT", "5432"))
DB_NAME      = os.getenv("DB_NAME", "mt5_scalper_db")
DB_USER      = os.getenv("DB_USER", "postgres")
DB_PASSWORD  = os.getenv("DB_PASSWORD", "")
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ─────────────────────────────────────────────
# SYMBOLS & TIMEFRAMES
# ─────────────────────────────────────────────
SYMBOLS             = _p["symbols"]
TIMEFRAMES          = ["15m", "1h"]
ENTRY_TIMEFRAME     = os.getenv("ENTRY_TIMEFRAME", "1h")   # 15m | 1h
STRUCTURE_TIMEFRAME = ENTRY_TIMEFRAME
BIAS_TIMEFRAME      = "1h"

# ─────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────
HISTORICAL_YEARS        = 2
MAX_CANDLES_PER_REQUEST = 5000
DATA_DELAY_THRESHOLD    = 1800

# MT5 polling interval (giây) — Windows only
MT5_POLL_INTERVAL = float(os.getenv("MT5_POLL_INTERVAL", "5"))

# STALE threshold: nếu không có bar mới trong N giây → reconnect
STALE_CLOSED_BAR_THRESHOLD = 1500

# Broker server UTC offset (ICMarkets = UTC+3 EEST summer, UTC+2 EET winter)
# MT5 trả về candle time theo server local time, không phải UTC
# Set BROKER_TZ_OFFSET=2 vào mùa đông (tháng 11 - tháng 3)
BROKER_TZ_OFFSET = int(os.getenv("BROKER_TZ_OFFSET", "3"))

# LIMIT order timeout (số candle)
LIMIT_ORDER_TIMEOUT_CANDLES = int(os.getenv("LIMIT_ORDER_TIMEOUT_CANDLES", "3"))

WS_RECONNECT_DELAY = 5

# ─────────────────────────────────────────────
# RISK  (from profile)
# ─────────────────────────────────────────────
RISK_PER_TRADE     = _p["risk_per_trade"]
MAX_DAILY_LOSS     = _p["max_daily_loss"]
MAX_DRAWDOWN       = _p["max_drawdown"]
MAX_OPEN_POSITIONS = _p["max_open_positions"]
MAX_LEVERAGE       = _p["max_leverage"]
MIN_RR             = 1.5

# ─────────────────────────────────────────────
# SESSION FILTER (Forex-specific)
# ─────────────────────────────────────────────
SESSION_FILTER_ENABLED = os.getenv("SESSION_FILTER_ENABLED", "true").lower() == "true"

# ─────────────────────────────────────────────
# STRATEGY
# ─────────────────────────────────────────────
SWING_LOOKBACK        = 2
FVG_MIN_ATR_RATIO     = 0.3
OB_LOOKBACK           = 10
VOLUME_THRESHOLD      = 0.5
ENTRY_CONFIRM_CANDLES = 1
EQUAL_HIGH_THRESHOLD  = 0.0005
SL_BUFFER             = 0.0005   # 0.05% of price — wider buffer to avoid stop-hunting

# ─────────────────────────────────────────────
# PAPER TRADING
# ─────────────────────────────────────────────
PAPER_INITIAL_BALANCE    = 5_000.0
PAPER_SLIPPAGE_ATR_RATIO = 0.05
PAPER_LATENCY_MS         = 100

# ─────────────────────────────────────────────
# WEB DASHBOARD
# ─────────────────────────────────────────────
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "changeme")

# ─────────────────────────────────────────────
# MT5 SYMBOL MAP  (Windows / broker-specific)
# Một số broker dùng suffix: EURUSD.raw / XAUUSDm
# Set trong .env: MT5_SYM_XAUUSD=XAUUSDm
# ─────────────────────────────────────────────
MT5_SYMBOL_MAP = {
    "EURUSD": os.getenv("MT5_SYM_EURUSD", "EURUSD"),
    "GBPUSD": os.getenv("MT5_SYM_GBPUSD", "GBPUSD"),
    "USDJPY": os.getenv("MT5_SYM_USDJPY", "USDJPY"),
    "AUDUSD": os.getenv("MT5_SYM_AUDUSD", "AUDUSD"),
    "USDCAD": os.getenv("MT5_SYM_USDCAD", "USDCAD"),
    "USDCHF": os.getenv("MT5_SYM_USDCHF", "USDCHF"),
    "NZDUSD": os.getenv("MT5_SYM_NZDUSD", "NZDUSD"),
    "EURGBP": os.getenv("MT5_SYM_EURGBP", "EURGBP"),
    "EURJPY": os.getenv("MT5_SYM_EURJPY", "EURJPY"),
    "GBPJPY": os.getenv("MT5_SYM_GBPJPY", "GBPJPY"),
    "XAUUSD": os.getenv("MT5_SYM_XAUUSD", "XAUUSD"),
    "XAGUSD": os.getenv("MT5_SYM_XAGUSD", "XAGUSD"),
}

MT5_TF_MAP = {
    "1m":  "TIMEFRAME_M1",
    "5m":  "TIMEFRAME_M5",
    "15m": "TIMEFRAME_M15",
    "30m": "TIMEFRAME_M30",
    "1h":  "TIMEFRAME_H1",
    "4h":  "TIMEFRAME_H4",
    "1d":  "TIMEFRAME_D1",
}

# ─────────────────────────────────────────────
# YFINANCE SYMBOL MAP  (Mac/Linux)
# ─────────────────────────────────────────────
YFINANCE_SYMBOL_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
    "EURGBP": "EURGBP=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
    "XAUUSD": "GC=F",    # Gold futures
    "XAGUSD": "SI=F",    # Silver futures
}

# ─────────────────────────────────────────────
# CONFIRM REQUIRED PER SYMBOL
# ─────────────────────────────────────────────
CONFIRM_REQUIRED: dict = {
    "EURUSD": True,
    "GBPUSD": True,
    "USDJPY": False,
    "XAUUSD": True,
    "USDCAD": True,
    "USDCHF": True,
    "AUDUSD": True,
    "GBPJPY": True,
    "EURJPY": True,
}

# ─────────────────────────────────────────────
# PIP SIZE PER PAIR
# ─────────────────────────────────────────────
PIP_SIZE = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "AUDUSD": 0.0001,
    "NZDUSD": 0.0001,
    "USDCAD": 0.0001,
    "USDCHF": 0.0001,
    "EURGBP": 0.0001,
    "USDJPY": 0.01,
    "EURJPY": 0.01,
    "GBPJPY": 0.01,
    "XAUUSD": 0.01,
    "XAGUSD": 0.001,
}

STANDARD_LOT = 100_000
MINI_LOT     = 10_000
MICRO_LOT    = 1_000
