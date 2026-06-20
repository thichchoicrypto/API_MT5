"""
Centralized logging using loguru.
"""
import sys
from pathlib import Path
from loguru import logger

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def setup_logger(name: str = "scalper") -> None:
    logger.remove()

    # Console — colored
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan> - {message}",
        level="INFO",
    )

    # File — INFO+ (DEBUG quá verbose, gây file 200MB+/ngày)
    logger.add(
        LOG_DIR / f"{name}.log",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
        level="INFO",
    )

    # Error-only file
    logger.add(
        LOG_DIR / f"{name}_errors.log",
        rotation="1 week",
        retention="12 weeks",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
        level="ERROR",
    )


setup_logger()

__all__ = ["logger"]
