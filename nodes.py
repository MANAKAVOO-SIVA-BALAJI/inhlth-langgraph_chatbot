from typing import TypedDict, List, Union, Optional,Annotated ,Any
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage,SystemMessage# type: ignore
from langchain_core.runnables import Runnable# type: ignore
from langgraph.graph import StateGraph, START,END# type: ignore
from langchain_openai import ChatOpenAI# type: ignore
from langchain_core.tools import Tool# type: ignore
from langchain_community.tools.graphql.tool import GraphQLAPIWrapper # type: ignore
from langgraph.graph.message import add_messages# type: ignore
from prompt import system_query_prompt_format, system_data_analysis_prompt_format ,system_intent_prompt
from config import OPENAI_API_KEY,HASURA_GRAPHQL_URL,HASURA_ADMIN_SECRET,HASURA_ROLE
from logging_config import setup_logger
from utils import store_datetime
logger = setup_logger()

class AgentState(TypedDict):
    messages: Annotated[Union[AIMessage, HumanMessage, ToolMessage,SystemMessage],add_messages]
    history: List[Any]
    nodes: List[str]
    time: List[str]

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0,api_key=OPENAI_API_KEY)

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "query"
    return "data"

def data_analyser(state: AgentState):
    print("data_analyser is executing..")
    try:
        response = llm.invoke([system_data_analysis_prompt_format]+[state["messages"][0],state["messages"][-1]])
    except Exception as e:
        response = llm.invoke([system_data_analysis_prompt_format]+state["messages"])

    print("data_analyser: ",response.content)
    state["nodes"].append("data_analyser")
    state["time"].append(store_datetime())
    return {"messages": state["messages"] + [AIMessage(content=response.content)],"nodes":state["nodes"],"time":state["time"]}

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