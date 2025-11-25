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
from nodes import (
    AgentState,
    clarify,
    data_analyser,
    general_response,
    intent_planner_decision,
    llm,
    should_continue,
)
from prompt import system_intent_prompt, system_query_prompt_format , system_intent_prompt2 ,System_query_validation_prompt
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

def build_graph(company_id,user_id):
    print("[BUILD_GRAPH] Called")
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
            bank_names: blood_order_view(distinct_on: blood_bank_name) {
                blood_bank_name
            }
            blood_groups: blood_order_view(distinct_on: blood_group) {
                blood_group
            }
            reasons: blood_order_view(distinct_on: reason) {
                reason
            }
            statuses: blood_order_view(distinct_on: status) {
                status
            }
            } """
        
        result = graphql_client.run_query(query)
        # logger.info(f"get_possible_values: {result}")
        return result
    
    tools_list = [safe_graphql_tool]
    llm_bind_tool=llm.bind_tools(tools_list)

    tool_map = {tool.name: tool for tool in tools_list}
    def intent_planner(state: AgentState):
        logger.info("intent_planner is executing..")
        new_nodes = state["nodes"] + ["intent_planner"]
        new_time = state["time"] + [store_datetime()]

        try:
            possible_values = get_possible_values() or {}
            data = possible_values

            bank_names = [item["blood_bank_name"] for item in data.get("bank_names", [])]
            blood_groups = [item["blood_group"] for item in data.get("blood_groups", [])]
            reasons = [item["reason"] for item in data.get("reasons", [])]
            statuses = [item["status"] for item in data.get("statuses", [])]

            field_context = f"""
            FIELD VALUE VALIDATION RULES
            You must strictly validate the following fields using the allowed values list.
            If no exact or fuzzy match is found (case-insensitive, spelling corrections, or common synonyms), you must ask for clarification in ask_for

            You must validate these restricted fields using exact or normalized values.
            If a user provides a value for any field that cannot be matched to the possible values (even after normalization), you must ask for clarification.
            For example, if user says B+ but it's not in the allowed list, ask:
            “I couldn’t find any data for ‘B+’. I have options like O+, AB+, or A-. Could you let me know which one fits best?”

            Valid values for field validation:
                - `blood_bank_name` (accepted blood banks): {bank_names}
                - `blood_group`: {blood_groups}
                - `reason` (Cause of request): {reasons}
                - `status` (upcoming status): {statuses}
                - `order_line_items` (Blood Components):  
                  [Single Donor Platelet, Platelet Concentrate, Packed Red Cells, Whole Human Blood, Platelet Rich Plasma, Fresh Frozen Plasma, Cryo Precipitate] 
                - current time for Time based fields: {get_current_datetime()}
                       
Clarify with a friendly, helpful message listing a few valid options. Do not assume or auto-correct silently.
 """.strip()
            
            
            full_prompt = [
                SystemMessage(content=system_intent_prompt + field_context + system_intent_prompt2),
                state["history_context"] + " ".join(msg.content for msg in state["messages"])
            ]
            # print("full_prompt :", full_prompt)

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

    def static_query_generate(fields_needed: list):
            all_order_supported_fields = ["age", "blood_bank_name", "blood_group", "creation_date_and_time", "delivery_date_and_time",\
                        "first_name", "last_name", "order_id", "patient_id", "reason", "status", "user_id", "order_line_items"]
            
            all_cost_supported_fields = ["company_name", "month_year", "blood_component", "total_patient","overall_blood_unit", "total_cost"]
                
            order_supported_fields =[]
            cost_supported_fields =[]

            for field in fields_needed:
                if field in all_order_supported_fields:
                    order_supported_fields.append(field)
                elif field in all_cost_supported_fields:
                    cost_supported_fields.append(field)

            if not order_supported_fields and not cost_supported_fields:
                order_supported_fields = ["request_id", "status", "blood_bank_name","creation_date_and_time", "order_line_items"]

            cost_query_template=""
            order_query_template=""

            if order_supported_fields:
                order_query_template = f"""
                blood_order_view(
                    order_by: {{ creation_date_and_time: desc }},
                    limit: 100
                ) {{
                    {', '.join(order_supported_fields)}
                }}
            """
            if cost_supported_fields:
                cost_query_template = f"""
                cost_and_billing_view(
                    order_by: {{ month_year: desc }},
                    limit: 100
                ) {{
                    {', '.join(cost_supported_fields)}
                }}
                
                """
            return f"""
            query {{
                {order_query_template}
                {cost_query_template if cost_query_template else ""}
            }}
                
            """

    def query_generate(state: AgentState):
        logger.info("query_generate is executing...")
        from graphql import parse, GraphQLError
   
        last_message = state["messages"][-1]
        if last_message.content.strip().startswith("[GraphQL Error]"):
            print("GraphQl Error query: ",last_message.content)
            input_message = HumanMessage(
                content=f"""
                User question: {state['messages'][0].content}
                Response from graphql tool: {last_message.content}
                Please fix the query.
                """
            )
            response = llm.invoke([system_query_prompt_format] + [input_message]) 
        
        else:
            json_data = {}
            try:
                content = state["intent_planner_response"][0].strip()
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

                required_keys = ["rephrased_question", "chain_of_thought","fields_needed"]
                if not all(key in json_data for key in required_keys):
                    logger.info(f"query_generate: Missing required {required_keys} keys in intent response.")

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
                suggested_fields = json_data['fields_needed']
                # print("suggested_fields :", suggested_fields)
            except Exception as e:
                logger.error(f"query_generate error: {e}")
                input_message = state["messages"][0]
            system_message = SystemMessage(
                content=system_query_prompt_format
            )
            # print("input_message :", input_message.content)
            response = llm.invoke([system_message, input_message])
            print("query_generated : ",response.content)
            try:
                parsed = parse(response.content)
            except GraphQLError as e:
                logger.error(f"GraphQLError in query_generate: {e}")
                error_message =  f"[GraphQL Error] {str(e)} When running this query: {response.content}."
                query_validation_input_message = HumanMessage(content=f"""
                        User Request: {input_message}
                        Error Message:
                        {error_message}
                        """)
                try:
                    response = llm.invoke([SystemMessage(content=System_query_validation_prompt), query_validation_input_message])
                    parsed = parse(response.content)
                except Exception as e:
                    logger.error(f"Failed to parse GraphQL response: {e}")
                    response.content=static_query_generate(suggested_fields)
                    logger.error(f"Used static query generation due to validation failure")
               
            logger.info("Query_generated finished successfully.")

        state["nodes"].append("query_generate")
        state["time"].append(store_datetime())

        return {
            "messages": state["messages"] + [AIMessage(content=response.content, additional_kwargs={"tag": "query_generate"})],
            "nodes": state["nodes"],
            "time": state["time"],
            "loop_count": state.get("loop_count", 0) + 1
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
    
    def run_graphql_query(state: AgentState):
        query = state["messages"][-1].content
        logger.info(f"Running GraphQL query: {query}")
        data=graphql_client.run_query(query)
        state["nodes"].append("run_graphql_query")
        state["time"].append(store_datetime())

        return {
            "messages": state["messages"] + [AIMessage(content=json.dumps(data), additional_kwargs={"tag": "run_graphql_query"})],
            "nodes": state["nodes"],
            "time": state["time"]
        }

    sample_builder= StateGraph(AgentState)
    sample_builder.add_node("intent_planner", intent_planner)
    sample_builder.add_node("query_generate", query_generate)
    sample_builder.add_node("general_response", general_response)
    sample_builder.add_node("run_graphql_query", run_graphql_query)
    sample_builder.add_node("data_analyser", data_analyser)
    # sample_builder.add_node("graphql_tool", call_tool)
    sample_builder.add_node("clarify", clarify)

    sample_builder.add_conditional_edges("intent_planner", intent_planner_decision,
                                         {
            "data_query": "query_generate",
            "general": "general_response",
            "clarification": "clarify"
        }
    )
   
    sample_builder.add_conditional_edges("query_generate", should_continue, {
        "query": "run_graphql_query",
        "end": "general_response" 
    })
    sample_builder.add_edge("run_graphql_query","data_analyser")
    # sample_builder.add_edge("graphql_tool", END)
    # sample_builder.add_edge("graphql_tool", "query_generate")
    sample_builder.add_edge("data_analyser",END)
    sample_builder.add_edge("general_response",END)
    sample_builder.add_edge("clarify",END)

    sample_builder.set_entry_point("intent_planner")
    # sample_builder.add_edge("intent_planner", END)
    graph=sample_builder.compile() 
    # graph_code = graph.get_graph(xray=True).draw_mermaid()
    # print(graph_code)

    # graph.get_graph(xray=True).draw_mermaid_png(output_file_path="graph.png")
    return graph

# user_id = "USR-3K2HD8DHYH"
# company_id = "CMP-RRPZYICLEG"
# graph=build_graph(company_id,user_id)
