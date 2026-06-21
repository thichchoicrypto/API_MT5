"""
Telegram alert service.
"""
import asyncio
import ssl
import aiohttp
from utils.logger import logger
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


class TelegramAlert:
    def __init__(self, token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self._enabled = bool(token and chat_id)

    async def send(self, message: str) -> bool:
        if not self._enabled:
            logger.debug(f"[Telegram disabled] {message}")
            return False
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        return True
                    logger.warning(f"Telegram send failed: {resp.status}")
                    return False
        except Exception as e:
            logger.warning(f"Telegram error: {e}")
            return False

    def send_sync(self, message: str) -> bool:
        """Synchronous wrapper."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.send(message))
                return True
            return loop.run_until_complete(self.send(message))
        except Exception:
            return False


# Singleton
telegram = TelegramAlert()
