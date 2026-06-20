"""
Import CSV candles vào DB Mac — chạy sau khi copy file từ Windows sang.

Usage:
    python tools/import_candles.py --dir ./export_data
"""
import asyncio
import csv
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

async def import_all(input_dir: Path):
    from dotenv import load_dotenv
    load_dotenv()
    from phase1_data.database import Database
    from phase1_data.validator import validate_candles

    db = Database()
    await db.connect()

    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {input_dir}")
        return

    total = 0
    for fpath in csv_files:
        # Parse symbol + tf từ filename: EURUSD_15m.csv
        stem = fpath.stem  # "EURUSD_15m"
        parts = stem.split("_")
        if len(parts) < 2:
            print(f"Skip {fpath.name} (can't detect symbol/tf)")
            continue

        symbol = parts[0]
        tf     = parts[1]

        candles = []
        with open(fpath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    candles.append({
                        "symbol":    symbol,
                        "timeframe": tf,
                        "open_time": datetime.strptime(
                            row["open_time"], "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=timezone.utc),
                        "open":   float(row["open"]),
                        "high":   float(row["high"]),
                        "low":    float(row["low"]),
                        "close":  float(row["close"]),
                        "volume": int(float(row["volume"])),
                    })
                except Exception as e:
                    continue

        validated = validate_candles(candles, symbol, tf)
        if validated:
            cnt = await db.upsert_candles_bulk(symbol, tf, validated)
            print(f"✅ {symbol} {tf}: {cnt} candles imported")
            total += cnt
        else:
            print(f"⚠️  {symbol} {tf}: no valid candles")

    await db.disconnect()
    print(f"\nDone: {total:,} total candles imported")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="./export_data", help="Folder chứa CSV files")
    args = parser.parse_args()
    asyncio.run(import_all(Path(args.dir)))
