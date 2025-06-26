# app/logging_config.py
import logging
from logging.handlers import RotatingFileHandler
import os

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger():
    logger = logging.getLogger("fastapi")
    logger.setLevel(logging.INFO)

    # File handler (rotates at 1MB, keeps 3 backups)
    file_handler = RotatingFileHandler(f"{LOG_DIR}/app.log", maxBytes=1_000_000, backupCount=3)
    file_handler.setLevel(logging.INFO)

    # Console handler (optional)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Attach handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
