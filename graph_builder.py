from nodes import AgentState, should_continue, data_analyser, intent_classify, intent_decision , llm
from langgraph.graph import StateGraph, START,END
from langchain_core.tools import Tool
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage,SystemMessage
from langchain_community.tools.graphql.tool import GraphQLAPIWrapper
from config import OPENAI_API_KEY,HASURA_GRAPHQL_URL,HASURA_ADMIN_SECRET,HASURA_ROLE
from prompt import system_query_prompt_format


def build_graph(company_id,user_id):
    graphql_tool = GraphQLAPIWrapper(
    graphql_endpoint=HASURA_GRAPHQL_URL,
    custom_headers= {
                "Content-Type": "application/json",
                "x-hasura-admin-secret": HASURA_ADMIN_SECRET,
                "x-hasura-role": HASURA_ROLE,
                "X-Hasura-Company-Id": company_id,
                "x-hasura-user-id": user_id
            },
    fetch_schema_from_transport=False) 

    tool = Tool.from_function(
        func=graphql_tool.run,
        name="graphql",
        description="Execute GraphQL queries to retrieve data"
    ) 
    llm_bind_tool=llm.bind_tools([tool])
    tool_map = {tool.name: tool}
    def call_llm(state: AgentState):
        print("call_llm is executing..")
        response = llm_bind_tool.invoke([system_query_prompt_format]+state["history"]+state["messages"])
        if not response.content and response.additional_kwargs.get("tool_calls"):
            tool_name = response.additional_kwargs["tool_calls"][0]["function"]["name"]
            response.content = f"Calling `{tool_name}` tool to process your request..."
        print("Call_llm: ",response.content)
        state["nodes"].append("call_llm")
        return {"messages": state["messages"] + [response],"nodes":state["nodes"]}

    def call_tool(state: AgentState):
        last_ai_message = state["messages"][-1]
        if not hasattr(last_ai_message, "tool_calls"):
            raise ValueError("No tool_calls in last AI message")
        print("call_tool")
        tool_outputs = []
        for call in last_ai_message.tool_calls:
            tool_name = call["name"]
            tool_input = call["args"]["query"] if "query" in call["args"] else call["args"]
            tool_result = tool_map[tool_name].run(tool_input)
            # print(f"Tool {tool_name} executed with input: {tool_input}")
            # print(f"Tool {tool_name} returned: {tool_result}")
            tool_outputs.append(
                ToolMessage(tool_call_id=call["id"], content=tool_result)
            )
        return {"messages": state["messages"] + tool_outputs}

    builder = StateGraph(AgentState)
    builder.add_node("intent_classify", intent_classify)
    builder.add_node("query_llm", call_llm)
    builder.add_node("graphql_tool", call_tool)
    builder.add_node("data_analyser", data_analyser)

    builder.add_edge(START,"intent_classify")

    builder.add_conditional_edges("intent_classify", intent_decision, {"data_need":"query_llm","direct_answer":"data_analyser"})

    builder.add_conditional_edges("query_llm", should_continue, {
        "query": "graphql_tool",
        "data": "data_analyser"
    })

    builder.add_edge("graphql_tool", "query_llm")

    builder.add_edge("data_analyser",END)

    graph = builder.compile()
    
    graph.get_graph(xray=True).draw_mermaid_png(output_file_path="graph.png")
    return graph


