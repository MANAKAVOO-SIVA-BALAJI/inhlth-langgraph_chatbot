import requests
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage #type: ignore
from utils import store_datetime
import json
from cache import memory_cache
class HasuraMemory():
    def __init__(
        self, 
        hasura_url: str, 
        hasura_secret: str,
        hasura_role: str = "dataops", #"user"
        company_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        self.hasura_url = hasura_url
        self.hasura_secret = hasura_secret
        self.hasura_role = hasura_role
        self.company_id = company_id
        self.user_id = user_id
        self.headers = {
            "Content-Type": "application/json",
            "x-hasura-admin-secret": self.hasura_secret,
            "x-hasura-role": self.hasura_role,
            "X-Hasura-Company-Id": self.company_id,
            "x-hasura-user-id": self.user_id
        }
    def _safe_serialize(self, obj):
        """Recursively convert complex LangChain objects into JSON-serializable format"""
        from langchain.schema import BaseMessage# type: ignore
        if isinstance(obj, BaseMessage):
            return obj.model_dump()
        elif isinstance(obj, dict):
            return {k: self._safe_serialize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._safe_serialize(i) for i in obj]
        return obj
 
    def deserialize_history(self,history):
        deserialized = []
        for record in history:
            raw = record.get("messages")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    continue 
            msgs = raw if isinstance(raw, list) else [raw]

            for msg in msgs:
                if msg.get("type") == "user":
                    deserialized.append(HumanMessage(content=msg["content"]))
                elif msg.get("type") == "ai":
                    deserialized.append(AIMessage(content=msg["content"]))
                elif msg.get("type") == "system":
                    deserialized.append(SystemMessage(content=msg["content"]))
                elif msg.get("type") == "tool":
                    deserialized.append(ToolMessage(content=msg["content"], tool_call_id=msg.get("tool_call_id", "")))
        # print("deserialized return type: ",type(deserialized))
        return deserialized

    def save_messages(self, config: Dict[str, Any], messages: list,nodes: list,time: list, conversation_id: str) -> None:
        """Store multiple messages in Hasura, excluding tool-related messages"""
        print(f"[SAVE_MESSAGES] Called with arguments:")
        print(f"  config: {config}")
        print(f"  messages Length: {len(messages)}")
        print(f"conversation_id: {conversation_id}")

        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        step = 0

        graphql_query = """
        mutation InsertMultipleCheckpoints($objects: [chat_messages_insert_input!]!) {
            insert_chat_messages(objects: $objects) {
                affected_rows
            }
        }
        """
        nodes = [node for node in nodes if node != "tool"]
        nodes_i = 0
        node = None
        objects = []
        time = time if time else []
        time_i = 0
        cache_messages = []
        for msg in messages:
            if isinstance(msg, ToolMessage): 
                continue
            serialized_msg = self._safe_serialize(msg)
            if isinstance(msg, HumanMessage):
                sender_type = "user"
            elif isinstance(msg, AIMessage):
                sender_type = "agent"
            if nodes_i < len(nodes):
                node = nodes[nodes_i]
            if node == "data_analyser":
                sender_type = "final_response"
            
            meta_data = {"step": step, "node": node,"sender_type": sender_type}
            objects.append({
                "session_id": thread_id,
                "step": step,
                "node": node,
                "sender_type":sender_type,
                "messages": serialized_msg,
                "metadata": meta_data or {},
                'created_at': time[time_i],
                'conversation_id': conversation_id or str(uuid.uuid4())
            })
            if sender_type in ["user","final_response"] :
                cache_messages.append(HumanMessage(content=serialized_msg["content"]) if sender_type == "user" else AIMessage(content=serialized_msg["content"]))
            step += 1
            nodes_i += 1
            time_i += 1
        print(f"[SAVE_MESSAGES] - objects: {len(objects)}")

        if not objects:
            print("[SAVE_MESSAGES] All messages were tool/tool_call; skipping insert.")
            return

        variables = {
            "objects": objects
        }

        try:
            response = requests.post(
                self.hasura_url,
                json={"query": graphql_query, "variables": variables},
                headers=self.headers
            )
            data = response.json()
            if "errors" in data:
                    print(f"[GET_HISTORY] Error : {data['errors']}")
                    return []
            print("[PUT] Success:", response.json())

            memory_cache.store_message(thread_id, cache_messages)
        except Exception as e:
            print(f"[PUT] Error inserting checkpoint into Hasura: {e}")

    def get_messages(self,config: Dict[str, Any]) -> List:
            """Retrieve messages for a thread"""
            print(f"[GET_MESSAGES] Called with arguments:")
            print(f"  config: {config}")
            
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            records_1 = memory_cache.get_history(thread_id)
            if records_1:
                print(f"[GET_MESSAGES] Found {len(records_1)} messages in cache for thread_id: {thread_id}")
                return records_1

            graphql_query = """query MyQuery($thread_id: String) {
                chat_messages(where: {session_id: {_eq: $thread_id}, sender_type: {_in: ["user","final_response"]}}, limit: 10) {
                    messages
                }
                }
                """
            
            variables= {
                "thread_id": thread_id
            }
    
            payload = {
                "query": graphql_query,
                "variables": variables
            }

            # print(f"[GET_TUPLE] Extracted - thread_id: {thread_id}")

            try:
                response = requests.post(self.hasura_url, json=payload, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                if "errors" in data:
                    print(f"[GET_HISTORY] Error : {data['errors']}")
                    return []
                records = data.get("data", {}).get("chat_messages", [])
                if not records:
                    print(f"[GET] No data found for thread_id: {thread_id}")
                    return None
                print("records:",len(records), records[0] if records else "No records found")

            except Exception as e:
                print(f"[GET] Error retrieving checkpoint from Hasura: {e}")
                return []
            
            print(f"[GET_MESSAGES] Extracted - thread_id: {thread_id}")
  
            serialized_history = self.deserialize_history(records)
            # print("Deserialized history:", serialized_history[0] if serialized_history else "No history found")

            memory_cache.store_message(thread_id, serialized_history)

            return serialized_history

    def get_history(self, config: Dict[str, Any]) -> List:
        """Retrieve chat history for a session"""
        print(f"[GET_HISTORY] Called with arguments:")
        print(f"  config: {config}")
        
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")

        graphql_query = """query MyQuery($thread_id: String) {
            chat_messages(where: {session_id: {_eq: $thread_id}, sender_type: {_in: ["user", "final_response"]}}) {
                role: messages(path: "type")
                content: messages(path: "content")
                created_at
                conversation_id
            }
            }
            """
        
        variables= {
            "thread_id": thread_id
        }

        payload = {
            "query": graphql_query,
            "variables": variables
        }

        try:
            response = requests.post(self.hasura_url, json=payload, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                print(f"[GET_HISTORY] Error: {data['errors']}")
                return []
            records = data.get("data", {}).get("chat_messages", [])
            if not records:
                print(f"[GET_HISTORY] No data found for thread_id: {thread_id}")
                return []

        except Exception as e:
            print(f"[GET_HISTORY] Error retrieving checkpoint from Hasura: {e}")
            return []
        
        print(f"[GET_HISTORY] Extracted - thread_id: {thread_id}")

        return records if isinstance(records, list) else [records]

