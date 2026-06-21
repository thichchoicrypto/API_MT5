"""
MT5 Watchdog — Windows VPS only.

Chạy song song với bot, check mỗi 60s:
  - Nếu terminal64.exe không chạy → start lại MT5
  - Nếu bot (main.py) không chạy → start lại bot
  - Gửi Telegram alert mỗi lần restart

Usage (chạy trong PowerShell riêng):
    python tools/mt5_watchdog.py

Hoặc thêm vào Task Scheduler để auto-start cùng VPS.
"""
import os
import sys
import time
import subprocess
import asyncio
from pathlib import Path

# Thêm project root vào path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from utils.logger import logger
from utils.telegram import telegram

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
MT5_EXE      = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
BOT_SCRIPT   = r"C:\Projects\API_MT5\main.py"
BOT_VENV     = r"C:\Projects\API_MT5\venv\Scripts\python.exe"
CHECK_INTERVAL = 60   # giây
MT5_STARTUP_WAIT = 15  # giây chờ MT5 khởi động xong


def is_process_running(name: str) -> bool:
    """Check xem process name có đang chạy không."""
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
        capture_output=True, text=True
    )
    return name.lower() in result.stdout.lower()


def count_process(name: str) -> int:
    """Đếm số lần process đang chạy."""
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
        capture_output=True, text=True
    )
    return result.stdout.lower().count(name.lower())


def start_mt5():
    """Start MT5 Terminal process."""
    if not Path(MT5_EXE).exists():
        logger.error(f"MT5 exe not found: {MT5_EXE}")
        return False
    try:
        subprocess.Popen([MT5_EXE], creationflags=subprocess.DETACHED_PROCESS)
        logger.info(f"MT5 Terminal started: {MT5_EXE}")
        return True
    except Exception as e:
        logger.error(f"Failed to start MT5: {e}")
        return False


def start_bot():
    """Start trading bot."""
    try:
        subprocess.Popen(
            [BOT_VENV, BOT_SCRIPT, "live"],
            cwd=str(Path(BOT_SCRIPT).parent),
            creationflags=subprocess.DETACHED_PROCESS,
        )
        logger.info("Bot started")
        return True
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        return False


async def send_alert(msg: str):
    await telegram.send(msg)


def main():
    logger.info("MT5 Watchdog started — checking every 60s")
    asyncio.run(send_alert("🐶 MT5 Watchdog started"))

    mt5_restarts = 0
    bot_restarts = 0

    while True:
        try:
            # ── Check MT5 Terminal ──────────────────────
            if not is_process_running("terminal64.exe"):
                mt5_restarts += 1
                logger.warning(f"MT5 Terminal not running! Restarting... (#{mt5_restarts})")
                ok = start_mt5()
                if ok:
                    asyncio.run(send_alert(
                        f"⚠️ MT5 Terminal crashed — restarted (#{mt5_restarts})\n"
                        f"Chờ {MT5_STARTUP_WAIT}s để MT5 khởi động..."
                    ))
                    time.sleep(MT5_STARTUP_WAIT)
                else:
                    asyncio.run(send_alert(
                        f"🔴 MT5 restart FAILED (#{mt5_restarts})\n"
                        f"Kiểm tra VPS ngay: {MT5_EXE}"
                    ))

            # ── Check Bot process ───────────────────────
            # Watchdog itself is python.exe — cần >=2 python processes để bot đang chạy
            if count_process("python.exe") < 2:
                bot_restarts += 1
                logger.warning(f"Bot not running! Restarting... (#{bot_restarts})")
                # Đảm bảo MT5 đang chạy trước khi start bot
                if is_process_running("terminal64.exe"):
                    ok = start_bot()
                    if ok:
                        asyncio.run(send_alert(
                            f"⚠️ Bot crashed — restarted (#{bot_restarts})"
                        ))
                    else:
                        asyncio.run(send_alert(
                            f"🔴 Bot restart FAILED (#{bot_restarts})"
                        ))
                else:
                    logger.info("MT5 not ready yet, skip bot restart this cycle")

        except Exception as e:
            logger.error(f"Watchdog error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
