
from graph_builder import build_graph
from langchain_core.messages import AIMessage, HumanMessage ,ToolMessage # type: ignore
from graphql_memory import HasuraMemory
from config import HASURA_ADMIN_SECRET,HASURA_GRAPHQL_URL,HASURA_ROLE
from typing import Dict, Any
from langsmith.run_helpers import traceable # type: ignore
from utils import store_datetime ,get_message_unique_id

@traceable(name="generate_chat_response", tags=["chatbot", "langgraph"])
def generate_chat_response(chat_request,config: Dict[str, Any]) -> str:
    """Generate a chat response using the graph."""
    from langsmith import utils # type: ignore
    if utils.tracing_is_enabled():
        print("LangSmith tracing is enabled.")
    else:
        print("LangSmith tracing is not enabled.")
    conversation_id = get_message_unique_id()
    hasura_memory = HasuraMemory(hasura_url=HASURA_GRAPHQL_URL,hasura_secret=HASURA_ADMIN_SECRET,hasura_role=HASURA_ROLE,company_id=chat_request.company_id,user_id=chat_request.user_id)
    graph = build_graph(chat_request.company_id,chat_request.user_id)
    message = [HumanMessage(content=chat_request.message)]
    meta_data = {"step": 0, "node": "human","sender_type": "input"}
    history =hasura_memory.get_messages(config)
    if not history:
        history = []
        history_length=0
    else:
        history_length = len(history)
    

    print("history:",type(history),history_length)

    # return "This is a test response. Data request received successfully, but no real call was made."
    if not message:
        return "Error processing the request. Please provide a valid input."    
    output = graph.invoke({
        "messages": message,
        "history": history,
        "nodes":["input"],
        "time":[store_datetime()],
    })
    # print("Type:",type(output["messages"][-1]))

    print("nodes:",output["nodes"])
    print("time:",output["time"])

    store_messages = output["messages"]
    hasura_memory.save_messages(config,store_messages,nodes=output["nodes"],time=output["time"], conversation_id=conversation_id)

    return output["messages"][-1].content.replace("*","") if output["messages"] else "Sorry, I could not generate a response at this time. Please try again later."


# user_input = "hello, track my last order?"
# print("User: ", user_input)
# config = {"configurable": {"thread_id":"CSI-A7PD1CV7YA"}} # req.session_id

# output = generate_chat_response(user_input,config)

# print("Chatbot: ", output)
