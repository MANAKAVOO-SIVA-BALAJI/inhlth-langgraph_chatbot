from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict


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


def format_blood_orders_for_llm(data: Dict) -> str:
    def fmt_dt(dt_str):
        if not dt_str or dt_str in ["null", None]:
            return "Not Delivered"
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")
            return dt.strftime("%b %d, %Y at %I:%M %p")
        except ValueError:
            print(f"Invalid Date Format: {dt_str}")
            return "No Delivery Date"

    formatted = []
    for i, order in enumerate(data["blood_bank_order_view"], 1):
        items = ", ".join(
            f"{item['unit']} unit of {item['product_name']} "
            for item in order.get("order_line_items", [])
        )
        created = fmt_dt(order.get("creation_date_and_time"))
        delivered = fmt_dt(order.get("delivery_date_and_time"))

        order_summary = (
            f"{i}. Order ID: {order.get('request_id')} | Status: {order.get('status')}\n"
            f"   Patient details: {order.get('first_name')} {order.get('last_name')} (Age {order.get('age')}, Blood Group: {order.get('blood_group')})\n"
            f"   Reason for blood order: {order.get('reason')}\n"
            f"   resquested hospital name: {order.get('hospital_name') or 'N/A'}\n"
            f"   Blood components: {items or 'No Items'}\n"
            f"   Created at: {created} | Delivered on: {delivered}\n"
        )
        formatted.append(order_summary)

    return "\n".join(formatted)

def format_hospital_orders_for_llm(data: Dict) -> str:
    def fmt_dt(dt_str):
        if not dt_str or dt_str in ["null", None]:
            return "Not Delivered"
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")
            return dt.strftime("%b %d, %Y at %I:%M %p")
        except ValueError:
            print(f"Invalid Date Format: {dt_str}")
            return "No Delivery Date"

    formatted = []
    for i, order in enumerate(data["blood_order_view"], 1):
        items = ", ".join(
            f"{item['unit']} unit of {item['product_name']} (cost: ₹{item['price']})"
            for item in order.get("order_line_items", [])
        )
        created = fmt_dt(order.get("creation_date_and_time"))
        delivered = fmt_dt(order.get("delivery_date_and_time"))

        order_summary = (
            f"{i}. Order ID: {order.get('request_id')} | Status: {order.get('status')}\n"
            f"   Patien details: {order.get('first_name')} {order.get('last_name')} (Age {order.get('age')}, Blood Group: {order.get('blood_group')})\n"
            f"   Reason for blood order: {order.get('reason')}\n"
            f"   Order Accepted Blood Bank: {order.get('blood_bank_name') or 'N/A'}\n"
            f"   Blood components: {items or 'No Items'}\n"
            f"   Created at: {created} | Delivered by: {delivered}\n"
        )
        formatted.append(order_summary)

    return "\n".join(formatted)

