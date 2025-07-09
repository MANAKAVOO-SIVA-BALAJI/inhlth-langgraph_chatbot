from datetime import datetime
from zoneinfo import ZoneInfo

def get_current_datetime() -> str:
    """Returns the current date and time in IST (Asia/Kolkata) timezone."""
    tz = ZoneInfo("Asia/Kolkata")
    return datetime.now(tz).strftime("%d-%m-%Y %I:%M %p") # e.g. 01-07-2025 01:07 PM

def get_message_unique_id() -> str:
    """Generates a unique message ID based on the current date and time."""
    return datetime.now().strftime("%Y_%m_%d_%H_%M_%S_%f") # e.g. 2025_07_01_13_07_51_957074

def store_datetime() -> str:
    """Returns the current date and time in IST (Asia/Kolkata) timezone with seconds and microseconds."""
    tz = ZoneInfo("Asia/Kolkata")
    current_time = datetime.now(tz)
    return current_time.strftime("%d-%m-%Y %I:%M:%S.%f %p") # e.g. 01-07-2025 01:07:51.957074 PM

def get_session_id() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%m-%Y") # e.g. 01-07-2025


