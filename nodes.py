from typing import Annotated, Any, Dict, List, Optional, TypedDict, Union

from langchain_core.messages import (  # type: ignore
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI  # type: ignore
from langgraph.graph.message import add_messages  # type: ignore

from config import OPENAI_API_KEY
from logging_config import setup_logger
from prompt import (
    system_data_analysis_prompt_format,
    system_general_response_prompt,
    system_intent_prompt,
)
from utils import get_current_datetime, store_datetime

logger = setup_logger()
import json


class AgentState(TypedDict):
    messages: Annotated[Union[AIMessage, HumanMessage, ToolMessage,SystemMessage],add_messages]
    intent_planner_response: Optional[list[Dict[str,any]]]
    tool_calls_history: Optional[List[Dict[str, any]]]
    query_generate_response: Optional[Dict[str, any]]
    history: List[Any]
    nodes: List[str]
    time: List[str]
    debug_info: Optional[Dict[str, Any]]

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0,api_key=OPENAI_API_KEY)

# def intent_planner(state: AgentState):
#     logger.info("intent_planner is executing..")
#     try:
#         response = llm.invoke([SystemMessage(content=system_intent_prompt)] + state["messages"])
#         parsed_response = json.loads(response.content)
        
#         new_nodes = state["nodes"] + ["intent_planner"]
#         new_time = state["time"] + [store_datetime()]
        
#         return {
#             "messages": state["messages"] + [AIMessage(content=response.content, additional_kwargs={"tag": "intent_planner"})],
#             "intent_planner_response": [parsed_response],
#             "nodes": new_nodes,
#             "time": new_time
#         }
#     except json.JSONDecodeError as e:
#         logger.error(f"JSON parsing failed in intent_planner: {e}")
#         return {
#             "messages": state["messages"] + [AIMessage(content="Error processing request", additional_kwargs={"tag": "error"})],
#             "nodes": state["nodes"] + ["intent_planner_error"],
#             "time": state["time"] + [store_datetime()]
#         }

# def intent_planner_decision(state: AgentState):
#     print("intent_planner_decision is executing..")
#     last_message = state["messages"][-1].content
#     if isinstance(last_message,str):
#         try:
#             output = json.loads(last_message)
#         except Exception as e:
#             return "general"
    
#     if output["ask_for"].strip() != "":
#         return "clarification"
#     if output["intent"] == "data_query":
#         return "data_query"
#     else:
#         return "general"

def intent_planner_decision(state: AgentState):
    try:
        last_message = state["messages"][-1].content
        if not isinstance(last_message, str):
            logger.warning("Non-string message content, routing to general")
            return "general"
            
        output = json.loads(last_message)
        
        # Validate required fields
        if "ask_for" not in output or "intent" not in output:
            logger.error("Missing required fields in intent response")
            return "general"
            
        if output["ask_for"].strip():
            return "clarification"
        elif output["intent"] == "data_query":
            return "data_query"
        else:
            return "general"
            
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed in decision: {e}")
        return "general"
    except Exception as e:
        logger.error(f"Unexpected error in intent_planner_decision: {e}")
        return "general"

# def general_response(state: AgentState):
#     print("general_response is executing..")
#     try:
#         last_message = json.loads(state["messages"][-1].content)
#         # input_message = [f"User question:{last_message["rephrased_question"]},\n Chain of Thought: {last_message["chain_of_thought"]} + Curent Date & Time:{get_current_datetime()}"]
#         input_message = [HumanMessage(content=f"User question: {last_message['rephrased_question']}\nChain of Thought: {last_message['chain_of_thought']}\nCurrent Time: {get_current_datetime()}")]    
#         output = llm.invoke([SystemMessage(content=system_general_response_prompt)]+input_message)
#     except Exception as e:
#         print("general_response error: ",e)
#         last_message = state["messages"][0]
#         output = llm.invoke([SystemMessage(content=system_general_response_prompt)]+last_message)
#     state["nodes"].append("general_response")
#     state["time"].append(store_datetime())
#     return {"messages": state["messages"] + [AIMessage(content=output.content,additional_kwargs={"tag": "general_response"})],"nodes":state["nodes"],"time":state["time"]}

def general_response(state: AgentState):
    try:
        last_message = json.loads(state["messages"][-1].content)
        input_message = [HumanMessage(content=f"User question: {last_message['rephrased_question']}\nChain of Thought: {last_message['chain_of_thought']}\nCurrent Time: {get_current_datetime()}")]
        output = llm.invoke([SystemMessage(content=system_general_response_prompt)] + input_message)
    except json.JSONDecodeError:
        # Fallback to original user message
        user_message = next((msg for msg in state["messages"] if isinstance(msg, HumanMessage)), None)
        if user_message:
            input_message = [HumanMessage(content=f"User question: {user_message.content}\nCurrent Time: {get_current_datetime()}")]
            output = llm.invoke([SystemMessage(content=system_general_response_prompt)] + input_message)
        else:
            logger.error("No valid user message found in state")
            output = AIMessage(content="I'm sorry, I couldn't process your request. Please try again.")
    except Exception as e:
        logger.error(f"Error in general_response: {e}")
        output = AIMessage(content="An error occurred while processing your request.")
    
    return {
        "messages": state["messages"] + [AIMessage(content=output.content, additional_kwargs={"tag": "general_response"})],
        "nodes": state["nodes"] + ["general_response"],
        "time": state["time"] + [store_datetime()]
    }

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tool_call"
    return "data"

def data_analyser(state: AgentState):
    print("data_analyser is executing..")
    try:
        # response = llm.invoke([system_data_analysis_prompt_format]+[state["messages"][0],state["messages"][-1]])
        print(state["intent_planner_response"])
        rephrased_question = json.loads(state["intent_planner_response"][0]).get("rephrased_question","")
        print(rephrased_question)
        user_message= rephrased_question if rephrased_question else state["messages"][0]
        response = llm.invoke([system_data_analysis_prompt_format]+["User question : ",user_message,"Data : "+str(state["messages"][-1].content)+"Response: "])

    except Exception as e:
        print("data_analyser error: ",e)
        response = llm.invoke([system_data_analysis_prompt_format]+state["messages"])

    print("data_analyser: ",response.content)
    state["nodes"].append("data_analyser")
    state["time"].append(store_datetime())
    return {"messages": state["messages"] + [AIMessage(content=response.content)],"nodes":state["nodes"],"time":state["time"]}

def clarify(state: AgentState):
    last_message = state["messages"][-1].content
    if isinstance(last_message,str):
        try:
            output = json.loads(last_message)
        except Exception as e:
            print("clarify error: ",e)
            return {"messages": state["messages"] + [AIMessage(content="we don't understand your question, can you rephrase it?",additional_kwargs={"tag": "clarify"})]}
    state["nodes"].append("clarify")
    state["time"].append(store_datetime())
    return {"messages": state["messages"] + [AIMessage(content=output["ask_for"],additional_kwargs={"tag": "clarify"})],"nodes":state["nodes"],"time":state["time"]}

def intent_classify(state: AgentState):
    print("intent_classify is executing..")
    try:
        response = llm.invoke([system_intent_prompt]+state["history"]+state["messages"])
    except Exception as e:
        print("intent_classify error: ",e)
        response = llm.invoke([system_intent_prompt]+state["messages"])

    print("intent_classify: ",response.content)
    state["nodes"].append("intent_classify")
    state["time"].append(store_datetime())

    return {"messages": [AIMessage(content=response.content)],"nodes":state["nodes"],"time":state["time"]}

def intent_decision(state: AgentState):
    print("intent_decision is executing..")
    if state["messages"][-1].content.lower() == "dataquery":
        return "data_need"
    else:
        return "direct_answer"

