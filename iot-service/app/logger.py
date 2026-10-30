"""
Structured Console & Rotating File Logger for the Raspberry Pi IoT Module.
Persists all device state transitions, MQTT connection events, and Watchdog recovery actions.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from app.config import settings

_LOGGING_INITIALIZED = False


def setup_iot_logging() -> None:
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED:
        return

    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    formatter = logging.Formatter(fmt)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    # 1. Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. Rotating File handler (5 MB x 3 backups)
    try:
        log_path = Path(settings.LOG_FILE_PATH)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as exc:
        root_logger.warning("Could not initialize file logger: %s", exc)

    _LOGGING_INITIALIZED = True


def get_iot_logger(name: str) -> logging.Logger:
    setup_iot_logging()
    return logging.getLogger(name)
