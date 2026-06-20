"""
Phase 9.7 + 9.12 — Risk Kill Switch + Safe/Degraded Mode.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, List
from utils.logger import logger
from utils.telegram import telegram
from config.settings import MAX_DAILY_LOSS, MAX_DRAWDOWN, SYMBOLS


class KillSwitch:
    """
    Phase 9.7: Monitors for critical conditions and halts the bot.
    Phase 9.12: Safe mode — only close positions, no new entries.
    """

    def __init__(self, order_manager):
        self.order_manager = order_manager
        self.active = True          # False = fully stopped
        self.safe_mode = False      # True = only closes, no new entries
        self._triggers: List[str] = []

    async def check(self, daily_pnl_pct: float, drawdown: float,
                    ws_connected: bool, data_delayed: bool,
                    api_errors: int,
                    binance_banned: bool = False) -> bool:
        """
        Returns True if trading is allowed, False if kill switch triggered.
        Edge cases handled:
        - Binance IP ban → immediate kill
        - API error accumulation → safe mode first, then kill
        - Data delay → safe mode (no new entries)
        """
        if not self.active:
            return False

        reasons = []

        if daily_pnl_pct <= -MAX_DAILY_LOSS:
            reasons.append(f"Daily loss {daily_pnl_pct:.1%} exceeded {MAX_DAILY_LOSS:.1%}")

        if drawdown >= MAX_DRAWDOWN:
            reasons.append(f"Drawdown {drawdown:.1%} exceeded {MAX_DRAWDOWN:.1%}")

        if binance_banned:
            reasons.append("Binance IP banned — cannot execute orders")

        if api_errors >= 10:
            reasons.append(f"Too many API errors: {api_errors}")
        elif api_errors >= 5 and not self.safe_mode:
            await self.enter_safe_mode(f"API errors: {api_errors}")

        if data_delayed and not self.safe_mode:
            await self.enter_safe_mode("Market data delayed")

        if reasons:
            await self._trigger(reasons)
            return False

        return self.trading_allowed

    async def _trigger(self, reasons: List[str]):
        reason_str = " | ".join(reasons)
        self._triggers.extend(reasons)

        msg = f"🚨 KILL SWITCH TRIGGERED\nReason: {reason_str}"
        logger.critical(msg)
        await telegram.send(msg)

        # Phase 9.7: close all and disable
        try:
            await self.order_manager.close_all_positions(SYMBOLS)
            logger.info("All positions closed via kill switch")
        except Exception as e:
            logger.error(f"Kill switch close_all error: {e}")

        self.active = False

    async def enter_safe_mode(self, reason: str):
        """Phase 9.12: Safe/degraded mode — no new entries."""
        self.safe_mode = True
        msg = f"⚠️ SAFE MODE: {reason} — no new entries, closing only"
        logger.warning(msg)
        await telegram.send(msg)

    def reset(self):
        """Manual reset after human review."""
        self.active = True
        self.safe_mode = False
        self._triggers.clear()
        logger.info("Kill switch reset")

    @property
    def trading_allowed(self) -> bool:
        return self.active and not self.safe_mode
