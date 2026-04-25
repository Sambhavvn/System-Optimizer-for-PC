from __future__ import annotations
from loguru import logger
from datetime import datetime
from .config import LOG_DIR

# Create log file with today's date
LOG_FILE = LOG_DIR / f"app_{datetime.now():%Y-%m-%d}.log"

# Remove default logger to apply our own formatting
logger.remove()

# Log to console (for real-time debugging)
logger.add(
    sink=lambda msg: print(msg, end=""),
    level="INFO",
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan> -> "
           "<level>{message}</level>"
)

# Log to file for saving logs
logger.add(
    LOG_FILE,
    level="INFO",
    rotation="1 week",      # New log file every week
    retention="4 weeks",    # Keep logs for 4 weeks
    encoding="utf-8"
)

# Export logger whenever this file is imported
__all__ = ["logger"]
