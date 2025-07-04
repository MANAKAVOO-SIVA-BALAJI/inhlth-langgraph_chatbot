from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from fastapi.middleware.cors import CORSMiddleware

from enum import Enum
from datetime import datetime
from typing import Optional
from chat import generate_chat_response
from fastapi import FastAPI, Request
from logging_config import setup_logger
from config import HASURA_ADMIN_SECRET,HASURA_GRAPHQL_URL,HASURA_ROLE ,LANGCHAIN_TRACING_V2, LANGCHAIN_ENDPOINT, LANGCHAIN_API_KEY ,APP_DEBUG
import os
from graphql_memory import HasuraMemory
from utils import get_session_id
if APP_DEBUG:
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING_V2
    os.environ["LANGCHAIN_ENDPOINT"] = LANGCHAIN_ENDPOINT

logger = setup_logger()


class UserRole(str, Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    HOSPITAL = "HOSPITAL"
    BLOOD_BANK = "BLOOD_BANK"

def date_time():
    return datetime.utcnow().isoformat()

class UserInfo(BaseModel):
    user_id: str = Field()
    company_id: str = Field()

class ChatRequest(UserInfo):
    """
    Model for validating chat requests.
    """
    message: str = Field(..., min_length=1, max_length=1000)
    session_id: str = Field(default=get_session_id())
    timestamp: str = Field(default_factory=date_time)

    @field_validator("message")
    def validate_message_content(cls, v):
        """
        Validator to ensure message content is not empty.
        """
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v

class ChatResponse(BaseModel):
    """
    Model for chat responses.
    """
    session_id: str = Field()
    response: str = Field(..., description="The chatbot's response to the user's message")
    timestamp: str = Field(default_factory=date_time)

class HistoryRequest(BaseModel):
    """
    Model for chat history requests.
    """
    session_id: str = Field(default=get_session_id(), description="Session ID to retrieve messages from")
    user_id: str = Field(..., description="User ID")

class HistoryResponse(BaseModel):
    """
    Model for chat history.
    """
    messages: list = Field(..., description="List of chat messages in the session")

app = FastAPI(title="Inhlth AI Chatbot API",
             description="API for interacting with the Inhlth AI Chatbot",
             version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"New request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Completed with status code: {response.status_code}")
    return response

async def process_normal_message(req: ChatRequest):
    """Process message for normal response"""
    config = {"configurable": {"thread_id":req.session_id}}

    try:
        response = generate_chat_response(req, config)
        return ChatResponse(
            session_id=req.session_id,
            response=response,
            timestamp=date_time()
        )
    except Exception as e:
        print("Error:", str(e))
        return ChatResponse(
            session_id=req.session_id,
            response="Sorry, I couldn't reply with a response at this Moment. Please try again later.",
            timestamp=req.timestamp,
        )


@app.get("/")
async def root():
    return {"message": "Chatbot API AI backend is live and operational!"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "normal_chat": "/chat"
        }
    }

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Normal chat endpoint - returns complete response at once
    """
    result = await process_normal_message(req)
    return result

@app.post("/get_session_messages")
async def get_session_messages(req: HistoryRequest): 

    print("get_session_messages request details: ", req.session_id)
    hasura_obj = HasuraMemory(hasura_url=HASURA_GRAPHQL_URL, hasura_secret=HASURA_ADMIN_SECRET, hasura_role=HASURA_ROLE, user_id=req.user_id)

    try:
        history = hasura_obj.get_history({"configurable": {"thread_id": req.session_id}})
        if not history:
            return HistoryResponse(messages=[])
    except Exception as e:
        print(f"Error retrieving messages: {e}")
        return JSONResponse(status_code=500, content={"message": "Internal server error while retrieving messages."})
    
    return HistoryResponse(messages=history)

# # Example response format:
# {
#     "messages": [
#         {
#             "role": "user",
#             "content": "hello, inhlth",
#             "created_at": "2025-07-01T13:07:48.905346",
#             "conversation_id": "2025_07_01_13_07_51_957074"
#         },
#         {
#             "role": "ai",
#             "content": "Hello! How can I assist you today?",
#             "created_at": "2025-07-01T13:07:51.954991",
#             "conversation_id": "2025_07_01_13_07_51_957074"
#         }
#     ]
# }


# @app.post("/chat/stream")
# async def chat_stream_endpoint(req: ChatRequest):
#     """
#     Streaming chat endpoint - returns response in real-time chunks
#     Uses Server-Sent Events (SSE) format
#     """
#     return StreamingResponse(
#         create_streaming_generator(req),
#         media_type="text/plain",
#         headers={
#             "Cache-Control": "no-cache",
#             "Connection": "keep-alive",
#             "Content-Type": "text/event-stream"
#         }
#     )


# @app.post("/chat/stream-simple")
# async def chat_stream_simple_endpoint(req: ChatRequest):
#     """
#     Simple streaming endpoint - returns just the content chunks
#     For basic streaming without SSE format
#     """
#     def simple_generator():
#         try:
#             for chunk in generate_streaming_response(req.message):
#                 yield chunk
#         except Exception as e:
#             yield f"Error: {str(e)}"
    
#     return StreamingResponse(
#         simple_generator(),
#         media_type="text/plain"
#     )


# if __name__ == "__main__":
#     import uvicorn 
    
#     print("Starting FastAPI server...")
#     print("Available endpoints:")

#     uvicorn.run(app, host="0.0.0.0", port=8000)

