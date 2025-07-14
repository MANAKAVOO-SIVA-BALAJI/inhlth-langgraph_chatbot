from datetime import datetime
from zoneinfo import ZoneInfo


def get_current_datetime() -> str:
    """Returns current date and time in 12-hour format with AM/PM (YYYY-MM-DD HH:MM:SS AM/PM)."""
    tz = ZoneInfo("Asia/Kolkata")
    return datetime.now(tz).strftime("%Y-%m-%d %I:%M:%S %p")  # e.g. 2025-07-08 03:02:41 PM

def store_datetime() -> str:
    """Returns date and time in ISO-like format (YYYY-MM-DDTHH:MM:SS) in 24-hour format."""
    tz = ZoneInfo("Asia/Kolkata")
    return datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S")  # e.g. 2025-07-08T15:02:41 

def get_session_id() -> str:
    """Returns current date (YYYY-MM-DD)."""
    tz = ZoneInfo("Asia/Kolkata")
    return datetime.now(tz).strftime("%Y-%m-%d")  # e.g. 2025-07-08

def get_message_unique_id() -> str:
    """Generates a unique message ID based on the current date and time."""
    return datetime.now().strftime("%Y_%m_%d_%H_%M_%S_%f")  # e.g. 2025_07_01_13_07_51_957074

