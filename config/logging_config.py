# app/logging_config.py
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger():
    logger = logging.getLogger("fastapi")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Prevent duplicate logs in root logger

    if not logger.handlers:
        file_handler = RotatingFileHandler(f"{LOG_DIR}/app.log", maxBytes=1_000_000, backupCount=3)
        file_handler.setLevel(logging.INFO)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
