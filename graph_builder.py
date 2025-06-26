from nodes import AgentState, should_continue,call_llm, call_tool, data_analyser, intent_classify, intent_decision
from langgraph.graph import StateGraph, START,END


def build_graph():
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

    # graph = builder.compile()
    # builder = StateGraph(AgentState)

    # builder.add_node("query_llm", call_llm)

    # builder.add_node("graphql_tool", call_tool)

    # builder.add_node("data_analyser", data_analyser)

    # builder.add_conditional_edges("query_llm", should_continue, {
    #     "query": "graphql_tool",
    #     "end": "data_analyser"
    # })

    # builder.add_edge("graphql_tool", "query_llm")

    # builder.set_entry_point("query_llm")
    # builder.add_edge(START,"query_llm")

    # builder.add_edge("data_analyser",END)

    
    graph.get_graph(xray=True).draw_mermaid_png(output_file_path="graph.png")
    return graph


