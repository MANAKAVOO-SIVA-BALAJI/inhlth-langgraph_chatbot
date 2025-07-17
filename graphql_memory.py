#graphql_memory.py
import json
import uuid
from typing import Any, Dict, List, Optional

import requests
from langchain_core.messages import (  #type: ignore
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
import requests
from requests.exceptions import Timeout, RequestException

from cache import memory_cache
from logging_config import setup_logger

logger = setup_logger()

class HasuraMemory():
    def __init__(
        self, 
        hasura_url: str, 
        hasura_secret: str,
        hasura_role: str = "dataops", 
        user_id: str = None,
        company_id: Optional[str] = None,
        
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
        from langchain.schema import BaseMessage  # type: ignore
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
        print("[SAVE_MESSAGES] Called with arguments:")
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
            if node == "data_analyser" or node == "general_response" or node == "clarify":
                sender_type = "final_response"
            
            meta_data = {"step": step, "node": node,"sender_type": sender_type}
            objects.append({
                "session_id": thread_id,
                "user_id": self.user_id,
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
            print(f"[SAVE_MESSAGES] - Response: {response.json()}")

            data = response.json()
            if "errors" in data:
                    print(f"[SAVE_MESSAGES] Error : {data['errors']}")
                    return []
            print("[PUT] Success:", response.json())

            memory_cache.store_message(self.user_id, cache_messages)
        except Exception as e:
            print(f"[PUT] Error inserting checkpoint into Hasura: {e}")

    def get_messages(self,config: Dict[str, Any]) -> List:
            """Retrieve messages for a thread"""
            print("[GET_MESSAGES] Called with arguments:")
            print(f"  config: {config}")
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            records_cache = memory_cache.get_history(self.user_id)
            if records_cache:
                print(f"[GET_MESSAGES] Found {len(records_cache)} messages in cache for thread_id: {thread_id}")
                return records_cache

            graphql_query = """query MyQuery($thread_id: String) {
                chat_messages(where: {session_id: {_eq: $thread_id}, sender_type: {_in: ["user","final_response"]}}, limit: 6) {
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
            try:
                response = requests.post(self.hasura_url, json=payload, headers=self.headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                records = data.get("data", {}).get("chat_messages", [])
                if not records:
                    print(f"[GET] No data found for thread_id: {thread_id}")
                    return None
                print("records:",len(records), records[0] if records else "No records found")

            except Timeout:
                print("[get_messages] Timeout occurred while calling Hasura.")
                return []
            except RequestException as e:
                print(f"[get_messages] Request error: {e}")
                return []
            except Exception as e:
                print(f"[get_messages] Unexpected error: {e}")
                return []
            
            serialized_history = self.deserialize_history(records)
            memory_cache.store_message(self.user_id, serialized_history)

            return serialized_history

    def get_history(self, config: Dict[str, Any]) -> List:
        """Retrieve chat history for a session"""
        print("[GET_HISTORY] Called with arguments:")
        print(f"  config: {config}")
        
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")

        graphql_query = """query MyQuery($session_id: String, $user_id: String = "") {
                chat_messages(where: {session_id: {_eq: $session_id}, sender_type: {_in: ["user", "final_response"]}, user_id: {_eq: $user_id}}, order_by: {created_at: asc}) {
                    role: messages(path: "type")
                    node
                    content: messages(path: "content")
                    created_at
                    conversation_id
                    feedback
                }
                }
            """
        
        variables= {
            "session_id": thread_id,
            "user_id": self.user_id
        }

        payload = {
            "query": graphql_query,
            "variables": variables
        }
        
        try:
            response = requests.post(self.hasura_url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                print(f"[GET_HISTORY] Error: {data['errors']}")
                return []
            records = data.get("data", {}).get("chat_messages", [])
            if not records:
                print(f"[GET_HISTORY] No data found for thread_id: {thread_id}")
                return []
                      
        except Timeout:
            print("[get_messages] Timeout occurred while calling Hasura.")
            return []
        except RequestException as e:
            print(f"[get_messages] Request error: {e}")
            return []
        except Exception as e:
            print(f"[get_messages] Unexpected error: {e}")
            return []
        logger.info(f"[GET_HISTORY] Extracted - thread_id: {thread_id}")
        return records if isinstance(records, list) else [records]

    def get_session_list(self) -> List:
        print("[GET_SESSION_LIST] Called")
        graphql_query = """query MyQuery {
            chat_messages(distinct_on: session_id, order_by: {session_id: desc}) {
                session_id
            }
            }
            """
        try:
            response = requests.post(self.hasura_url, json={"query": graphql_query}, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            print(f"[GET_SESSION_LIST] Response: {data}")
            if "errors" in data:
                print(f"[GET_SESSION_LIST] Error: {data['errors']}")
                return []
            records = data.get("data", {}).get("chat_messages", [])
            if not records:
                print("[GET_SESSION_LIST] No data found")
                return []
        except Exception as e:
            print(f"[GET_SESSION_LIST] Error retrieving checkpoint from Hasura: {e}")
            return []
        result=[msg["session_id"] for msg in records]
        return result

    def run_query(self, query, variables=None):
        try:
            payload = {
                "query": query,
                "variables": variables
            }
            response = requests.post(self.hasura_url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                print(f"Graphql Error: {data['errors']}")
                return {"error": "No data"}
            return data.get("data", {})
        except Timeout:
            print("[run_query] Timeout occurred while calling Hasura.")
            return {"errors": "Timeout"}
        except RequestException as e:
            print(f"[run_query] Request error: {str(e)}")
            return {"errors": "RequestException"}
        except Exception as e:
            print(f"[run_query] Unexpected error: {str(e)}")
            return None

    def session_init(self, variables):
        print("Session initiated")

        try:            
            query = """ mutation MyMutation($user_id: String!, $session_id: String!, $created_at: timestamp!, $title: String = "") {
                insert_chat_sessions(objects: {user_id: $user_id, session_id: $session_id, created_at: $created_at, title: $title}, on_conflict: {constraint: chat_sessions_pkey, update_columns: []}) {
                    returning {
                    session_id
                    created_at
                    }
                }
                }
                """
            variables= variables
            data = self.run_mutation(query, variables)
            print("session_init_data", data)
            if "errors" in data:
                print(f"Graphql Error: {data['errors']}")
                return {"data":"No data"}
            
            return data
        except Exception as e:
            print(f"GraphQL query error: {str(e)}")
            return None

    def run_mutation(self, query, variables=None):
        try:
            # gql_query = gql(query) #parse the graphQl query string to a gql object
            payload = {
                "query": query,
                "variables": variables
            }
            response = requests.post(self.hasura_url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                print(f"Graphql Error: {data['errors']}")
                return {"data": "No data"}
            return data.get("data", {})
        except Timeout:
            print("[run_query] Timeout occurred while calling Hasura.")
            return {"data": "Timeout"}
        except RequestException as e:
            print(f"[run_query] Request error: {str(e)}")
            return {"data": "RequestException"}
        except Exception as e:
            print(f"[run_query] Unexpected error: {str(e)}")
            return None

    def validate_user_id(self, user_id):

        try:
            # gql_query = gql(query) #parse the graphQl query string to a gql object
            query= """
                query MyQuery($user_id: String) {
                    chat_sessions(where: {user_id: {_eq: $user_id}}) {
                        user_id
                    }
                    }
                    """
            variables= {
                "user_id": user_id
            }
            payload = {
                "query": query,
                "variables": variables
            }
            response = requests.post(self.hasura_url, json=payload, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                print(f"Graphql Error: {data['errors']}")
                return False
            result = data.get("data", {})
            return True
        except Exception as e:
            print(f"GraphQL query error: {str(e)}")
            return False

    def check_session_exists(self, session_id: str) -> bool:
        query = """
        query MyQuery($session_id: String = "", $user_id: String = "") {
        chat_sessions(where: {_and: {session_id: {_eq: $session_id}}, user_id: {_eq: $user_id}}) {
            user_id
            session_id
        }
        }

        """
        variables = {"session_id": session_id,"user_id": self.user_id}
        result = self.run_query(query, variables)
        print("result", result)
        exists = result.get("chat_sessions", [])
        print("exists", exists)
        return bool(exists)

    def add_feedback(self,conversation_id:str,session_id:str,feedback:str):

        if int(feedback) == 1:
            query = """
                        mutation MyMutation($conversation_id: String = "", $user_id: String = "", $session_id: String = "") {
                update_chat_messages(where: {conversation_id: {_eq: $conversation_id}, user_id: {_eq: $user_id}, session_id: {_eq: $session_id}}, _set: {feedback: true}) {
                    affected_rows
                }
                }
            """
        else:
            query = """
                        mutation MyMutation($conversation_id: String = "", $user_id: String = "", $session_id: String = "") {
                update_chat_messages(where: {conversation_id: {_eq: $conversation_id}, user_id: {_eq: $user_id}, session_id: {_eq: $session_id}}, _set: {feedback: false}) {
                    affected_rows
                }
                }
            """

        variables = {"conversation_id": conversation_id,"session_id":session_id,"user_id": self.user_id}
        result = self.run_mutation(query, variables)
        print("result", result)
        return result
    
    def get_all_data(self,role: str ):
        if role == "bloodbank":
            query = """
                query MyQuery {
            blood_bank_order_view(order_by: {creation_date_and_time: desc, delivery_date_and_time: asc_nulls_first}, limit: 30) {
                age
                blood_group
                creation_date_and_time
                delivery_date_and_time
                first_name
                hospital_name
                last_name
                order_line_items
                patient_id
                reason
                status
                request_id
            }
            }
            """
        
        elif role == "hospital":
            query = """
                query MyQuery {
            blood_order_view(order_by: {creation_date_and_time: desc, delivery_date_and_time: asc_nulls_first}, limit: 30) {
                age
                blood_group
                creation_date_and_time
                delivery_date_and_time
                first_name
                blood_bank_name
                last_name
                order_line_items
                patient_id
                reason
                status
                request_id
            }
            }
            """
        
        result = self.run_query(query, variables=None)
        
        return result

 