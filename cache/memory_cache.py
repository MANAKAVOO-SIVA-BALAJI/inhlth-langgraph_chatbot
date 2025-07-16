from typing import Any, Dict, List

from cachetools import TTLCache

chat_history_cache = TTLCache(maxsize=1000, ttl=1800) 

def store_message(user_id: str , message: List[Dict[str, Any]]) -> None:
    if user_id not in chat_history_cache:
        chat_history_cache[user_id] = []
    for msg in message:
          chat_history_cache[user_id].append(msg)
    print("[store_message] Current cache state:", len(chat_history_cache[user_id]))

def get_history(user_id: str) -> List[Dict[str, Any]]:
    return chat_history_cache.get(user_id, [])

def has_history(user_id: str) -> bool:
    return user_id in chat_history_cache



