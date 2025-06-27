from typing import TypedDict, List, Union, Optional,Annotated ,Any
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage,SystemMessage
from langchain_core.runnables import Runnable
from langgraph.graph import StateGraph, START,END
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langchain_community.tools.graphql.tool import GraphQLAPIWrapper
from langgraph.graph.message import add_messages
from prompt import system_query_prompt_format, system_data_analysis_prompt_format ,system_intent_prompt
from config import OPENAI_API_KEY,HASURA_GRAPHQL_URL,HASURA_ADMIN_SECRET,HASURA_ROLE
from logging_config import setup_logger
logger = setup_logger()

class AgentState(TypedDict):
    messages: Annotated[Union[AIMessage, HumanMessage, ToolMessage,SystemMessage]
,add_messages]
    history: List[Any]
    nodes: List[str]


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0,api_key=OPENAI_API_KEY)

# graphql_tool = GraphQLAPIWrapper(
#     graphql_endpoint=HASURA_GRAPHQL_URL,
#     custom_headers= {
#                 "Content-Type": "application/json",
#                 "x-hasura-admin-secret": HASURA_ADMIN_SECRET,
#                 "x-hasura-role": HASURA_ROLE,
#                 "X-Hasura-Company-Id": "CMP-RRPZYICLEG",
#                 "x-hasura-user-id": "USR-IHI6SJSYB0"
#             },
#     fetch_schema_from_transport=False
# )

# tool = Tool.from_function(
#     func=graphql_tool.run,
#     name="graphql",
#     description="Execute GraphQL queries to retrieve data"
# )
# llm_bind_tool=llm.bind_tools([tool])
# tool_map = {tool.name: tool}

# def call_llm(state: AgentState):
#     print("call_llm is executing..")
#     response = llm_bind_tool.invoke([system_query_prompt_format]+state["messages"])
#     if not response.content and response.additional_kwargs.get("tool_calls"):
#         tool_name = response.additional_kwargs["tool_calls"][0]["function"]["name"]
#         response.content = f"Calling `{tool_name}` tool to process your request..."
#     print("Call_llm: ",response.content)
#     state["nodes"].append("call_llm")
#     return {"messages": state["messages"] + [response],"nodes":state["nodes"]}

# def call_tool(state: AgentState):
#     last_ai_message = state["messages"][-1]
#     if not hasattr(last_ai_message, "tool_calls"):
#         raise ValueError("No tool_calls in last AI message")
#     print("call_tool")
#     tool_outputs = []
#     for call in last_ai_message.tool_calls:
#         tool_name = call["name"]
#         tool_input = call["args"]["query"] if "query" in call["args"] else call["args"]
#         tool_result = tool_map[tool_name].run(tool_input)
#         # print(f"Tool {tool_name} executed with input: {tool_input}")
#         # print(f"Tool {tool_name} returned: {tool_result}")
#         tool_outputs.append(
#             ToolMessage(tool_call_id=call["id"], content=tool_result)
#         )
#     return {"messages": state["messages"] + tool_outputs}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "query"
    return "data"

def data_analyser(state: AgentState):
    print("data_analyser is executing..")
    # final_prompt = system_data_analysis_prompt_format.format(human_message=state["messages"][0].content)
    try:
        response = llm.invoke([system_data_analysis_prompt_format]+[state["messages"][0],state["messages"][-1]])
    except Exception as e:
        response = llm.invoke([system_data_analysis_prompt_format]+state["messages"])
    # print("data_analyser prompt: ",final_prompt)
    # print("data_analyser input: ",[state["messages"][-1]])
    # print("data_analyser human input: ",[state["messages"][0]])

    print("data_analyser: ",response.content)
    state["nodes"].append("data_analyser")
    return {"messages": state["messages"] + [AIMessage(content=response.content)],"nodes":state["nodes"]}

def intent_classify(state: AgentState):
    print("intent_classify is executing..")
    try:
        response = llm.invoke([system_intent_prompt]+state["history"]+state["messages"])
    except Exception as e:
        print("intent_classify error: ",e)
        response = llm.invoke([system_intent_prompt]+state["messages"])

    print("intent_classify: ",response.content)
    state["nodes"].append("intent_classify")
    return {"messages": AIMessage(content=response.content),"nodes":state["nodes"]}

def intent_decision(state: AgentState):
    print("intent_decision is executing..")
    if state["messages"][-1].content.lower() == "dataquery":
        return "data_need"
    else:
        return "direct_answer"