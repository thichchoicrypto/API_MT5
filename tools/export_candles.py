"""
Export candles từ DB ra CSV — chạy trên Windows sau khi download xong.
Copy các file CSV sang Mac rồi dùng import_candles.py để import.

Usage:
    python tools/export_candles.py
    python tools/export_candles.py --dir ./export_data
"""
import asyncio
import csv
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

async def export(output_dir: Path):
    from dotenv import load_dotenv
    load_dotenv()
    from phase1_data.database import Database
    from config.settings import SYMBOLS, TIMEFRAMES

    db = Database()
    await db.connect()

    output_dir.mkdir(parents=True, exist_ok=True)
    total = 0

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            candles = await db.get_candles(symbol, tf, limit=500_000)
            if not candles:
                print(f"No data: {symbol} {tf}")
                continue

            fname = output_dir / f"{symbol}_{tf}.csv"
            with open(fname, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["open_time", "open", "high", "low", "close", "volume"])
                for c in candles:
                    writer.writerow([
                        c["open_time"].strftime("%Y-%m-%d %H:%M:%S"),
                        c["open"], c["high"], c["low"], c["close"], c["volume"]
                    ])

            print(f"✅ {symbol} {tf}: {len(candles)} candles → {fname.name}")
            total += len(candles)

    await db.disconnect()
    print(f"\nDone: {total:,} total candles exported to {output_dir}/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="./export_data", help="Output directory")
    args = parser.parse_args()
    asyncio.run(export(Path(args.dir)))
