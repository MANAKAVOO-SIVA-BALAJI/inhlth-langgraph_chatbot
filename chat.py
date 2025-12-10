
from typing import Any, Dict

from langchain_core.messages import HumanMessage , AIMessage  # type: ignore
from langsmith.run_helpers import traceable  # type: ignore

from config.config import HASURA_ADMIN_SECRET, HASURA_GRAPHQL_URL, HASURA_ROLE
from hospital.graph_builder import build_graph
from blood_bank.blood_graph_builder import blood_build_graph
from hasura.graphql_memory import HasuraMemory
from config.logging_config import setup_logger
from utils import get_message_unique_id, store_datetime

logger = setup_logger()

from config.logging_config import setup_logger

logger = setup_logger()

@traceable(name="generate_chat_response", tags=["chatbot", "langgraph"])
def generate_chat_response(chat_request, config: Dict[str, Any], conversation_id: str = get_message_unique_id()) -> str:
    """Generate a chat response using the graph."""
      # Use as trace_id

    user_id = chat_request.user_id
    company_type = chat_request.company_type

    try:
        from langsmith import utils  # type: ignore
        if utils.tracing_is_enabled():
            logger.info(f" LangSmith tracing is enabled. user_id={user_id}")
        else:
            logger.info(f" LangSmith tracing is not enabled. user_id={user_id}")

        # Initialize Hasura memory
        try:
            hasura_memory = HasuraMemory(
                hasura_url=HASURA_GRAPHQL_URL,
                hasura_secret=HASURA_ADMIN_SECRET,
                hasura_role=HASURA_ROLE,
                company_id=chat_request.company_id,
                user_id=chat_request.user_id
            )
        except Exception as e:
            logger.error(f"[trace_id={conversation_id}] Failed to initialize HasuraMemory for user_id={user_id}: {e}")
            return "Something went wrong. Please try again later."

        #build graph
        try:
            if company_type == "BLOODBANK":
                logger.info("BLOODBANK")
                graph = blood_build_graph(chat_request.company_id, chat_request.user_id)

            else:
                logger.info("HOSPITAL")
                graph = build_graph(chat_request.company_id, chat_request.user_id)
                
        except Exception as e:
            logger.error(f"[trace_id={conversation_id}] Failed to build graph for user_id={user_id}: {e}")
            return "Something went wrong. Please try again later."

        # validate user input
        if not chat_request.message:
            logger.warning(f"[trace_id={conversation_id}] Empty message received from user_id={user_id}")
            return "Error processing the request. Please provide a valid input."

        # fetch history
        try:
            history = hasura_memory.get_messages(config)
        except Exception as e:
            logger.error(f"[trace_id={conversation_id}] Failed to fetch message history for user_id={user_id}: {e}")
            history = []
        # print("history messages :", history)

        history_length = len(history) if history else 0
        logger.info(f" Retrieved history for user_id={user_id}, length={history_length}")
        # return "test response"
        # invoke the graph
        if history_length > 0:
            history_context = "\n".join(
                    f"I am asked {msg.content}" if isinstance(msg, HumanMessage)
                    else f"then I got {msg.content}"
                    for msg in history
                )
        else:
            history_context = ""

        message = [HumanMessage(content=chat_request.message, additional_kwargs={"tag": "user_input"})]
        # print("history_context :", history_context)
        history_context = history_context + "so consider this context. Now, I am asked "
        
        try:
            output = graph.invoke({
                "messages": message,
                "history": history,
                "history_context": history_context,
                "nodes": ["input"],
                "time": [store_datetime()],
            })
        except Exception as e:
            logger.error(f"[trace_id={conversation_id}] Graph invocation failed for user_id={user_id}: {e}")
            return "Sorry, I could not generate a response at this time. Please try again later."

        logger.info(f"Graph invocation successful. user_id={user_id}")
        logger.debug(f"[trace_id={conversation_id}] Output nodes: {output.get('nodes')}, time: {output.get('time')}")

        # Save messages
        try:
            store_messages = output.get("messages", [])
            hasura_memory.save_messages(
                config,
                store_messages,
                nodes=output.get("nodes"),
                time=output.get("time"),
                conversation_id=conversation_id
            )
        except Exception as e:
            logger.error(f"[trace_id={conversation_id}] Failed to store messages for user_id={user_id}: {e}")

        # Return response
        return (
            store_messages[-1].content.replace("*", "")
            if store_messages else
            "I'm having trouble generating a response right now. Please try again later, and I'll do my best to help you."
        )

    except Exception as e:
        logger.error(f"[trace_id={conversation_id}] Unexpected error for user_id={user_id}: {e}")
        return "We're experiencing technical difficulties. Our team is working to resolve this as soon as possible. Please try again later."



