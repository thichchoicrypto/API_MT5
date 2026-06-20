"""
Phase 1.9 — Dukascopy Historical CSV Importer.

Dukascopy Bank SA cung cấp Forex history miễn phí, chất lượng cao (bid price).
Download tại: https://www.dukascopy.com/swiss/english/marketwatch/historical/

CSV format (từ Dukascopy web export):
    Gmt time,Open,High,Low,Close,Volume
    01.01.2024 00:00:00.000,1.10500,1.10520,1.10480,1.10510,100

Filename pattern (auto-detect symbol & timeframe):
    EURUSD_15 Mins_BID_2024.01.01_2024.12.31.csv
    XAUUSD_Hourly_BID_2024.01.01_2024.12.31.csv
    USDJPY_Daily_BID_2024.01.01_2024.12.31.csv

Usage:
    # Single file
    python3 phase1_data/dukascopy_importer.py --file EURUSD_15m.csv --symbol EURUSD --tf 15m

    # Auto-detect symbol/tf từ filename
    python3 phase1_data/dukascopy_importer.py --file EURUSD_15 Mins_BID_2024.01.01_2024.12.31.csv

    # Batch import toàn bộ thư mục
    python3 phase1_data/dukascopy_importer.py --dir ./dukascopy_data/
"""
import asyncio
import csv
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import logger
from phase1_data.validator import validate_candles

# ─────────────────────────────────────────────
# SYMBOL MAP  (Dukascopy name → internal name)
# ─────────────────────────────────────────────
DUKA_SYMBOL_MAP = {
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD", "USDCAD": "USDCAD", "USDCHF": "USDCHF",
    "NZDUSD": "NZDUSD", "EURGBP": "EURGBP", "EURJPY": "EURJPY",
    "GBPJPY": "GBPJPY", "XAUUSD": "XAUUSD", "XAGUSD": "XAGUSD",
    # Dukascopy aliases
    "GOLD":   "XAUUSD", "SILVER": "XAGUSD",
}

# ─────────────────────────────────────────────
# TIMEFRAME MAP  (Dukascopy label → internal)
# ─────────────────────────────────────────────
DUKA_TF_MAP = {
    "1 min":   "1m",  "1min":  "1m",  "1m":  "1m",
    "5 mins":  "5m",  "5mins": "5m",  "5m":  "5m",
    "15 mins": "15m", "15min": "15m", "15m": "15m",
    "30 mins": "30m", "30min": "30m", "30m": "30m",
    "hourly":  "1h",  "1h":    "1h",  "1hour": "1h",
    "4 hours": "4h",  "4h":    "4h",  "4hours": "4h",
    "daily":   "1d",  "1d":    "1d",  "day": "1d",
}


# ─────────────────────────────────────────────
# AUTO-DETECT symbol + tf từ filename
# ─────────────────────────────────────────────
def _parse_filename(path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (symbol, timeframe) from Dukascopy filename.

    Patterns:
      EURUSD_15 Mins_BID_2024.01.01_2024.12.31.csv  → (EURUSD, 15m)
      XAUUSD_Hourly_BID_Ask_2023.csv                → (XAUUSD, 1h)
      USDJPY_Daily_2024.csv                          → (USDJPY, 1d)
      GBPUSD_15m_2024.csv                            → (GBPUSD, 15m)
    """
    stem = path.stem.upper()  # e.g. "EURUSD_15 MINS_BID_2024.01.01_2024.12.31"

    # Extract symbol (first 6 chars or before first underscore)
    symbol = None
    parts = stem.replace("-", "_").split("_")
    raw_sym = parts[0][:6]
    symbol = DUKA_SYMBOL_MAP.get(raw_sym)

    # Extract timeframe — search all parts for known tf labels
    tf = None
    full_stem_lower = path.stem.lower()
    # Try combined parts (e.g. "15 mins")
    for duka_label, internal_tf in sorted(DUKA_TF_MAP.items(), key=lambda x: -len(x[0])):
        if duka_label in full_stem_lower:
            tf = internal_tf
            break

    return symbol, tf


# ─────────────────────────────────────────────
# DATE PARSERS
# ─────────────────────────────────────────────
_DATE_FORMATS = [
    "%d.%m.%Y %H:%M:%S.%f",   # Dukascopy: 01.01.2024 00:00:00.000
    "%d.%m.%Y %H:%M:%S",      # Dukascopy no-ms: 01.01.2024 00:00:00
    "%Y-%m-%d %H:%M:%S",      # ISO: 2024-01-01 00:00:00
    "%Y.%m.%d %H:%M:%S",      # Alt: 2024.01.01 00:00:00
    "%Y/%m/%d %H:%M:%S",      # Alt: 2024/01/01 00:00:00
    "%Y-%m-%d %H:%M",          # Short ISO
]

def _parse_dt(raw: str) -> Optional[datetime]:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ─────────────────────────────────────────────
# CSV PARSER
# ─────────────────────────────────────────────
def parse_dukascopy_csv(file_path: Path, symbol: str, timeframe: str) -> List[dict]:
    """
    Parse Dukascopy CSV → list of candle dicts.

    Supports:
      - Header row detection (flexible column names)
      - European date format (DD.MM.YYYY)
      - ISO date format (YYYY-MM-DD)
      - Comma or semicolon delimiters
    """
    candles = []
    errors  = 0

    with open(file_path, "r", encoding="utf-8-sig") as f:
        # Auto-detect delimiter
        sample = f.read(1024)
        f.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","

        reader = csv.reader(f, delimiter=delimiter)

        # Find header row
        col_time = col_open = col_high = col_low = col_close = col_vol = None
        header_found = False

        for row in reader:
            if not row or not row[0].strip():
                continue

            row = [c.strip() for c in row]
            row_lower = [c.lower() for c in row]

            # Header detection
            if not header_found:
                time_keywords  = {"gmt time", "datetime", "date", "time", "timestamp"}
                open_keywords  = {"open"}
                high_keywords  = {"high"}
                low_keywords   = {"low"}
                close_keywords = {"close"}
                vol_keywords   = {"volume", "vol"}

                if any(kw in " ".join(row_lower) for kw in time_keywords):
                    for i, cell in enumerate(row_lower):
                        if any(kw in cell for kw in time_keywords) and col_time is None:
                            col_time = i
                        elif cell in open_keywords:
                            col_open = i
                        elif cell in high_keywords:
                            col_high = i
                        elif cell in low_keywords:
                            col_low = i
                        elif cell in close_keywords:
                            col_close = i
                        elif any(kw in cell for kw in vol_keywords):
                            col_vol = i
                    if col_time is not None and col_open is not None:
                        header_found = True
                        logger.debug(f"Header detected: time={col_time} O={col_open} H={col_high} L={col_low} C={col_close} V={col_vol}")
                    continue

            # Default column order if no header detected: time,open,high,low,close,volume
            if not header_found:
                col_time, col_open, col_high, col_low, col_close, col_vol = 0, 1, 2, 3, 4, 5
                header_found = True

            # Parse data row
            try:
                if len(row) < 5:
                    continue

                dt = _parse_dt(row[col_time])
                if dt is None:
                    errors += 1
                    continue

                candles.append({
                    "symbol":    symbol,
                    "timeframe": timeframe,
                    "open_time": dt,
                    "open":      float(row[col_open]),
                    "high":      float(row[col_high]) if col_high is not None else float(row[col_open]),
                    "low":       float(row[col_low])  if col_low  is not None else float(row[col_open]),
                    "close":     float(row[col_close]) if col_close is not None else float(row[col_open]),
                    "volume":    int(float(row[col_vol])) if col_vol is not None and col_vol < len(row) else 0,
                })
            except (ValueError, IndexError) as e:
                errors += 1
                if errors <= 3:
                    logger.debug(f"Row parse error: {row} — {e}")

    if errors > 0:
        logger.warning(f"  Skipped {errors} unparseable rows in {file_path.name}")

    logger.info(f"  Parsed {len(candles)} raw rows from {file_path.name}")
    return candles


# ─────────────────────────────────────────────
# MAIN IMPORT FUNCTION
# ─────────────────────────────────────────────
async def import_csv(file_path: Path, symbol: str = None, timeframe: str = None,
                     dry_run: bool = False) -> int:
    """
    Import một CSV file vào DB.
    Returns số candles đã save.
    """
    from phase1_data.database import Database
    from dotenv import load_dotenv
    load_dotenv()

    # Auto-detect symbol/tf từ filename nếu không truyền
    if symbol is None or timeframe is None:
        auto_sym, auto_tf = _parse_filename(file_path)
        symbol    = symbol    or auto_sym
        timeframe = timeframe or auto_tf

    if not symbol:
        logger.error(f"Cannot detect symbol from {file_path.name} — dùng --symbol")
        return 0
    if not timeframe:
        logger.error(f"Cannot detect timeframe từ {file_path.name} — dùng --tf")
        return 0

    symbol    = symbol.upper()
    timeframe = timeframe.lower()

    logger.info(f"Importing {file_path.name} → {symbol} {timeframe}")

    # Parse
    raw = parse_dukascopy_csv(file_path, symbol, timeframe)
    if not raw:
        logger.warning(f"  No data parsed from {file_path.name}")
        return 0

    # Validate
    validated = validate_candles(raw, symbol, timeframe)
    logger.info(f"  Validated: {len(validated)} / {len(raw)} candles")

    if dry_run:
        logger.info(f"  [DRY RUN] Would save {len(validated)} candles")
        if validated:
            logger.info(f"  Range: {validated[0]['open_time'].date()} → {validated[-1]['open_time'].date()}")
        return len(validated)

    # Save to DB
    db = Database()
    await db.connect()
    try:
        cnt = await db.upsert_candles_bulk(symbol, timeframe, validated)
        logger.info(f"  ✅ Saved {cnt} candles for {symbol} {timeframe} "
                    f"({validated[0]['open_time'].date()} → {validated[-1]['open_time'].date()})")
        return cnt
    finally:
        await db.disconnect()


async def import_directory(dir_path: Path, symbol: str = None, timeframe: str = None,
                           dry_run: bool = False):
    """Import tất cả CSV files trong một thư mục."""
    csv_files = sorted(dir_path.glob("*.csv")) + sorted(dir_path.glob("*.CSV"))
    if not csv_files:
        logger.error(f"Không tìm thấy CSV files trong {dir_path}")
        return

    logger.info(f"Found {len(csv_files)} CSV files in {dir_path}")
    total = 0
    for f in csv_files:
        cnt = await import_csv(f, symbol=symbol, timeframe=timeframe, dry_run=dry_run)
        total += cnt

    logger.info(f"✅ Total imported: {total} candles from {len(csv_files)} files")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Import Dukascopy historical CSV data into MT5 scalper DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file, auto-detect symbol/tf từ filename
  python3 phase1_data/dukascopy_importer.py --file "EURUSD_15 Mins_BID_2024.01.01_2024.12.31.csv"

  # Single file, specify symbol/tf manually
  python3 phase1_data/dukascopy_importer.py --file data.csv --symbol EURUSD --tf 15m

  # Batch import directory
  python3 phase1_data/dukascopy_importer.py --dir ./dukascopy_data/

  # Dry run (không save vào DB)
  python3 phase1_data/dukascopy_importer.py --file data.csv --dry-run

Download data tại:
  https://www.dukascopy.com/swiss/english/marketwatch/historical/
        """
    )
    parser.add_argument("--file",    type=str, help="Path đến CSV file")
    parser.add_argument("--dir",     type=str, help="Path đến thư mục chứa CSV files")
    parser.add_argument("--symbol",  type=str, help="Symbol (EURUSD, XAUUSD...) — auto-detect nếu bỏ trống")
    parser.add_argument("--tf",      type=str, help="Timeframe (15m, 1h...) — auto-detect nếu bỏ trống")
    parser.add_argument("--dry-run", action="store_true", help="Parse nhưng không save vào DB")

    args = parser.parse_args()

    if not args.file and not args.dir:
        parser.print_help()
        sys.exit(1)

    async def run():
        if args.file:
            p = Path(args.file)
            if not p.exists():
                logger.error(f"File không tồn tại: {p}")
                sys.exit(1)
            await import_csv(p, symbol=args.symbol, timeframe=args.tf, dry_run=args.dry_run)
        elif args.dir:
            d = Path(args.dir)
            if not d.is_dir():
                logger.error(f"Thư mục không tồn tại: {d}")
                sys.exit(1)
            await import_directory(d, symbol=args.symbol, timeframe=args.tf, dry_run=args.dry_run)

    asyncio.run(run())


if __name__ == "__main__":
    main()
