from typing import Any, Dict, List

from cachetools import TTLCache

chat_history_cache = TTLCache(maxsize=1000, ttl=1800) 

def store_message(session_id: str, message: List[Dict[str, Any]]) -> None:
    if session_id not in chat_history_cache:
        chat_history_cache[session_id] = []
    for msg in message:
          chat_history_cache[session_id].append(msg)
    print("[store_message] Current cache state:", len(chat_history_cache[session_id]))

def get_history(session_id: str) -> List[Dict[str, Any]]:
    return chat_history_cache.get(session_id, [])

def has_history(session_id: str) -> bool:
    return session_id in chat_history_cache



