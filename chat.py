
from graph_builder import build_graph
from langchain_core.messages import AIMessage, HumanMessage ,ToolMessage
from graphql_memory import HasuraMemory
from config import HASURA_ADMIN_SECRET,HASURA_GRAPHQL_URL,HASURA_ROLE
from typing import Dict, Any

graph = build_graph()

def generate_chat_response(chat_request,config: Dict[str, Any]):
    """Generate a chat response using the graph."""
    hasura_memory = HasuraMemory(hasura_url=HASURA_GRAPHQL_URL,hasura_secret=HASURA_ADMIN_SECRET,hasura_role=HASURA_ROLE,company_id=chat_request.company_id,user_id=chat_request.user_id)
    message = [HumanMessage(content=chat_request.message)]
    meta_data = {"step": 0, "node": "human","sender_type": "input"}
    history =hasura_memory.get_messages(config, task_id="test_task_123")

    history_length = len(history)
    print("history:",type(history),history_length)

    # hasura_memory.save_messages(config,message[0], meta_data,task_id="test_task_123")

    if not message:
        return "Error processing the request. Please provide a valid input."    
    output = graph.invoke({
        "messages": history+ message
    })
    history_final = len(output["messages"])

    meta_data = {"step": 1, "node": "final_response","sender_type": "Agent"}
    print("Type:",type(output["messages"][-1]))

    # print(output["messages"])
    # hasura_memory.save_messages(config,output["messages"][-1],meta_data, task_id="test_task_123")

    store_messages = output["messages"][::-1][:history_final-history_length]
    hasura_memory.save_messages(config,store_messages,meta_data, task_id="test_task_123")

    for i in store_messages:
        if not isinstance(i, ToolMessage):
            i.pretty_print()

    return output["messages"][-1].content if output["messages"] else "Sorry, I could not generate a response at this time. Please try again later."


# user_input = "hello, track my last order?"
# print("User: ", user_input)
# config = {"configurable": {"thread_id":"CSI-A7PD1CV7YA"}} # req.session_id

# output = generate_chat_response(user_input,config)

# print("Chatbot: ", output)
