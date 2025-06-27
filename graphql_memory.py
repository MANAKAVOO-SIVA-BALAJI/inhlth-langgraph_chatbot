import requests
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage #type: ignore
# from langchain.schema import BaseMessage, ToolMessage

import json

class HasuraMemory():
    def __init__(
        self, 
        hasura_url: str, 
        hasura_secret: str,
        hasura_role: str = "user", #dataops,
        company_id: str = "CMP-RRPZYICLEG",
        user_id: str = "USR-IHI6SJSYB0"
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
        from langchain.schema import BaseMessage
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
                if msg.get("type") == "human":
                    deserialized.append(HumanMessage(content=msg["content"]))
                elif msg.get("type") == "ai":
                    deserialized.append(AIMessage(content=msg["content"]))
                elif msg.get("type") == "system":
                    deserialized.append(SystemMessage(content=msg["content"]))
                elif msg.get("type") == "tool":
                    deserialized.append(ToolMessage(content=msg["content"], tool_call_id=msg.get("tool_call_id", "")))
        print("deserialized return type: ",type(deserialized))
        return deserialized

    def save_messages(self, config: Dict[str, Any], messages: list,nodes: list, task_id: Optional[str] = None) -> None:
        """Store multiple messages in Hasura, excluding tool-related messages"""
        print(f"[SAVE_MESSAGES] Called with arguments:")
        print(f"  config: {config}")
        print(f"  messages: {len(messages)}")
        print(f"  task_id: {task_id}")

        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        step = 0

        print(f"[SAVE_MESSAGES] Extracted - thread_id: {thread_id}, step: {step}")

        graphql_query = """
        mutation InsertMultipleCheckpoints($objects: [chatmessages_insert_input!]!) {
            insert_chatmessages(objects: $objects) {
                affected_rows
            }
        }
        """
        nodes = [node for node in nodes if node != "tool"]
        nodes_i = 0
        node="None"
        objects = []
        for msg in messages[::-1]:
            if isinstance(msg, ToolMessage): 
                continue
            serialized_msg = self._safe_serialize(msg)
            if isinstance(msg, HumanMessage):
                sender_type = "human"
            elif isinstance(msg, AIMessage):
                sender_type = "ai"
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
                "metadata": meta_data or {}
            })
            step += 1
            nodes_i+=1
            

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
            response.raise_for_status()
            print("[PUT] Success:", response.json())
        except Exception as e:
            print(f"[PUT] Error inserting checkpoint into Hasura: {e}")

    def get_messages(self,config: Dict[str, Any],task_id: Optional[str] = None) -> list:
            """Retrieve messages for a thread"""
            print(f"[GET_MESSAGES] Called with arguments:")
            print(f"  config: {config}")
            print(f"  task_id: {task_id}")
            
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            graphql_query = """ query MyQuery($thread_id: String) {
                chatmessages(where: {session_id: {_eq: $thread_id}}, limit: 4) {
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

            print(f"[GET_TUPLE] Extracted - thread_id: {thread_id}")

            try:
                response = requests.post(self.hasura_url, json=payload, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                records = data.get("data", {}).get("chatmessages", [])#.get("messages", [])
                if not records:
                    print(f"[GET] No checkpoint found for thread_id: {thread_id}")
                    return None
            except Exception as e:
                print(f"[GET] Error retrieving checkpoint from Hasura: {e}")
                return None
            
            print(f"[GET] Extracted - thread_id: {thread_id}")

            print(f"[GET_MESSAGES] Extracted - thread_id: {thread_id}")

            return self.deserialize_history(records)


