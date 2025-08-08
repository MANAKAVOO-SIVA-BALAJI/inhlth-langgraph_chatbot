import json

from langchain.tools import Tool, tool
from langchain_community.tools.graphql.tool import GraphQLAPIWrapper  # type: ignore

# from langchain_core.tools import Tool # type: ignore
from langchain_core.messages import (  # type: ignore
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, StateGraph  # type: ignore

from config import HASURA_ADMIN_SECRET, HASURA_GRAPHQL_URL, HASURA_ROLE
from graphql_memory import HasuraMemory
from logging_config import setup_logger
from blood_nodes import (
    AgentState,
    clarify,
    data_analyser,
    general_response,
    intent_planner_decision,
    llm,
    should_continue,
)
from blood_prompt import blood_system_intent_prompt, blood_System_query_prompt_format , blood_system_intent_prompt2
from utils import store_datetime ,get_current_datetime

logger = setup_logger()

class SafeGraphQLWrapper:
    def __init__(self, endpoint: str, headers: dict = None):
        self.client = GraphQLAPIWrapper(graphql_endpoint=endpoint, custom_headers=headers, fetch_schema_from_transport=False)

    def run(self, query: str) -> str:
        try:
            return self.client.run(query)
        except Exception as e:
            return f"[GraphQL Error] {str(e)} When running this query: {query}. The query might be malformed or the field might not exist."

def blood_build_graph(company_id,user_id):
    graphql_client = HasuraMemory(
        hasura_url=HASURA_GRAPHQL_URL,
        hasura_secret=HASURA_ADMIN_SECRET,
        hasura_role=HASURA_ROLE,
        user_id=user_id,
        company_id=company_id
    )
    headers= {
                "Content-Type": "application/json",
                "x-hasura-admin-secret": HASURA_ADMIN_SECRET,
                "x-hasura-role": HASURA_ROLE,
                "X-Hasura-Company-Id": company_id,
                "x-hasura-user-id": user_id
            }
    safe_graphql_tool = Tool(
    name="GraphQLTool",
    func=SafeGraphQLWrapper(endpoint=HASURA_GRAPHQL_URL,headers=headers).run,
    description="Executes GraphQL queries to retrive data. Returns error messages if the query is invalid."
    )
    

    def get_possible_values():

        query=""" query GetFilterOptions {
            bank_names: blood_bank_order_view(distinct_on: hospital_name) {
                hospital_name
            }
            blood_groups: blood_bank_order_view(distinct_on: blood_group) {
                blood_group
            }
            reasons: blood_bank_order_view(distinct_on: reason) {
                reason
            }
            statuses: blood_bank_order_view(distinct_on: status) {
                status
            }
            } """
        
        result = graphql_client.run_query(query)
        # print("blood bank get_possible_values: ",result)
        return result
    

    tools_list = [safe_graphql_tool]

    llm_bind_tool=llm.bind_tools(tools_list)
    

    tool_map = {tool.name: tool for tool in tools_list}

    def intent_planner(state: AgentState):
        logger.info("intent_planner is executing..")
        new_nodes = state["nodes"] + ["intent_planner"]
        new_time = state["time"] + [store_datetime()]

        try:
            # Fetch allowed values for schema-restricted fields
            possible_values = get_possible_values() or {}
            data = possible_values

            # Extract and flatten the field values
            bank_names = [item["hospital_name"] for item in data.get("bank_names", [])]
            blood_groups = [item["blood_group"] for item in data.get("blood_groups", [])]
            reasons = [item["reason"] for item in data.get("reasons", [])]
            statuses = [item["status"] for item in data.get("statuses", [])]

            # Build a formatted string to guide the LLM
            field_context = f"""
            VALID FIELDS AND VALUES
            You must validate these restricted fields using exact or normalized values. If the user provides a value outside of these, ask for clarification.
            Valid values for field validation:
                - `hospital_name` (requested Hospital): {bank_names}
                - `blood_group`: {blood_groups}
                - `reason` (Cause of request): {reasons}
                - `status` (upcoming status): {statuses}
                - `order_line_items` (Blood Components):  
                  [Single Donor Platelet, Platelet Concentrate, Packed Red Cells, Whole Human Blood, Platelet Rich Plasma, Fresh Frozen Plasma, Cryo Precipitate] 
                - current time for Time based fields: {get_current_datetime()}
                        """.strip()
            
            # Compose the final prompt input to LLM
            full_prompt = [
                SystemMessage(content=blood_system_intent_prompt + field_context + blood_system_intent_prompt2),
                *state["messages"]
            ]

            # Single-step LLM invocation (no tool call needed)
            response = llm.invoke(full_prompt)

            logger.info("intent_planner LLM response received.")
            return {
                "messages": state["messages"] + [
                    AIMessage(content=response.content, additional_kwargs={"tag": "intent_planner"})
                ],
                "intent_planner_response": [response.content],
                "nodes": new_nodes,
                "time": new_time
            }

        except Exception as e:
            logger.error(f"Error in intent_planner: {e}")
            fallback_response = f"""{{
                "intent": "general",
                "rephrased_question": {json.dumps(state["messages"][0].content)},
                "chain_of_thought": "No chain of thoughts available",
                "ask_for": "",
                "fields_needed": ""
            }}"""
            return {
                "messages": state["messages"] + [AIMessage(content=fallback_response, additional_kwargs={"tag": "intent_planner"})],
                "intent_planner_response": [fallback_response],
                "nodes": new_nodes,
                "time": new_time
            }

    def query_generate(state: AgentState):
        logger.info("query_generate is executing...")
  
        last_message = state["messages"][-1]
        if last_message.content.strip().startswith("[GraphQL Error]"):
            # print("GraphQl Error: ",last_message.content)
            input_message = HumanMessage(
                content=f"""
                User question: {state['messages'][0].content}
                Response from graphql tool: {last_message.content}
                Please fix the query.
                """
            )
            response = llm_bind_tool.invoke([blood_System_query_prompt_format] + [input_message]) 
        
        elif isinstance(last_message,ToolMessage):
            # print("query_generate: Tool response:", last_message.content)
            input_message = HumanMessage(
            content=f"Response from tool: {last_message.content}"
            )
            # print("input_message: ",input_message)

            response = llm_bind_tool.invoke([blood_System_query_prompt_format] + state["messages"] + [input_message]
)
            # response = llm_bind_tool.invoke([blood_System_query_prompt_format] +["User question :"+ state["messages"] +"\n"+ last_message.content])
            # print("state[messages]:", state["messages"])
        else:
            json_data = {}
            try:
                content = state["intent_planner_response"][0].strip()
                # print("query_generate: Intent planner output:", content)
                try:
                    json_data = json.loads(content)
                except json.JSONDecodeError:
                    try:
                        import re
                        corrected_content = re.sub(r"(\w+):", r'"\1":', content) 
                        json_data = json.loads(corrected_content)
                    except Exception:
                        logger.error("query_generate: Failed to parse intent planner output.")
                        json_data = {
                            "rephrased_question": state["messages"][0].content,
                            "chain_of_thought": "No reasoning available.",
                            "fields_needed": ""
                        }

                required_keys = ["rephrased_question", "chain_of_thought"]
                if not all(key in json_data for key in required_keys):
                    logger.info(f"query_generate: Missing required {required_keys}keys in intent response.")

                    json_data.setdefault("rephrased_question", state["messages"][0].content)
                    json_data.setdefault("chain_of_thought", "")
                    json_data.setdefault("fields_needed", "")

                input_message = HumanMessage(
                    content=(
                        f"User question: {json_data['rephrased_question']}\n"
                        f"Chain of Thought: {json_data['chain_of_thought']}\n"
                        f"Suggested fields: {json_data['fields_needed']}"
                    )
                )

            except Exception as e:
                logger.error(f"query_generate error: {e}")
                # fallback: use original user message
                input_message = state["messages"][0]
                # input_message = [first_message.content if hasattr(first_message, "content") else str(first_message)]

            
            response = llm_bind_tool.invoke([blood_System_query_prompt_format, input_message])
            

        # handle tool_call message if no content
        if not response.content and response.additional_kwargs.get("tool_calls"):
            tool_name = response.additional_kwargs["tool_calls"][0]["function"]["name"]
            response.content = f"Calling `{tool_name}` tool to process your request..."
            response.additional_kwargs["tag"] = "tool_call"
            state["query_generate_response"]= response

        # print("Call_llm:", response.content)
        # update state
        state["nodes"].append("query_generate")
        state["time"].append(store_datetime())

        return {
            "messages": state["messages"] + [response],
            "nodes": state["nodes"],
            "time": state["time"]
        }

    def call_tool(state: AgentState):
        last_ai_message = state["messages"][-1]
        
        if not hasattr(last_ai_message, "tool_calls") or not last_ai_message.tool_calls:
            logger.warning("No tool_calls found in last AI message")
            error_msg = ToolMessage(
                tool_call_id="error",
                content="No tool calls found. Please specify what data you need."
            )
            return {
                "messages": state["messages"] + [error_msg],
                "tool_calls_history": state.get("tool_calls_history", [])
            }
        
        tool_outputs = []
        for call in last_ai_message.tool_calls:
            try:
                tool_name = call.get("name")
                if tool_name not in tool_map:
                    logger.error(f"Unknown tool: {tool_name}")
                    tool_result = f"[Tool Error] Unknown tool: {tool_name}"
                else:
                    args = call.get("args", {})
                    tool_input = args.get("query", args)
                    tool_result = tool_map[tool_name].run(tool_input)
                    
            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                tool_result = f"[Tool Error] {str(e)}"
                
            tool_outputs.append(
                ToolMessage(tool_call_id=call.get("id", "unknown"), content=tool_result)
            )
        
        return {
            "messages": state["messages"] + tool_outputs,
            "tool_calls_history": (state.get("tool_calls_history", []) + [tool_outputs])
        }
   
    sample_builder= StateGraph(AgentState)
    sample_builder.add_node("intent_planner", intent_planner)
    sample_builder.add_node("query_generate", query_generate)
    sample_builder.add_node("general_response", general_response)
    sample_builder.add_node("data_analyser", data_analyser)
    sample_builder.add_node("graphql_tool", call_tool)
    sample_builder.add_node("clarify", clarify)

    sample_builder.add_conditional_edges("intent_planner", intent_planner_decision,
                                         {
            "data_query": "query_generate",
            "general": "general_response",
            "clarification": "clarify"
        }
    )
   
    sample_builder.add_conditional_edges("query_generate", should_continue, {
        "tool_call": "graphql_tool",
        "data": "data_analyser"
    })
    # sample_builder.add_edge("query_generate", END)
    sample_builder.add_edge("graphql_tool", "query_generate")
    sample_builder.add_edge("data_analyser",END)
    sample_builder.add_edge("general_response",END)
    sample_builder.add_edge("clarify",END)

    sample_builder.set_entry_point("intent_planner")

    graph=sample_builder.compile() 
    
    graph.get_graph(xray=True).draw_mermaid_png(output_file_path="blood_graph.png")
    return graph

