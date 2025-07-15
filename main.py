# main.py
import json
import os
import random
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langsmith import utils
from pydantic import BaseModel, Field, field_validator

from chat import generate_chat_response
from config import (
    APP_DEBUG,
    HASURA_ADMIN_SECRET,
    HASURA_GRAPHQL_URL,
    HASURA_ROLE,
    LANGCHAIN_API_KEY,
    LANGCHAIN_ENDPOINT,
    LANGCHAIN_TRACING_V2,
)
from graphql_memory import HasuraMemory
from logging_config import setup_logger
from utils import get_current_datetime, get_message_unique_id, get_session_id, store_datetime

logger = setup_logger()

if APP_DEBUG:
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING_V2
    os.environ["LANGCHAIN_ENDPOINT"] = LANGCHAIN_ENDPOINT

trace = False

if utils.tracing_is_enabled():
    trace = True
    print("LangSmith tracing is enabled.")
else:
    print("LangSmith tracing is not enabled.")

class UserRole(str, Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    HOSPITAL = "HOSPITAL"
    BLOOD_BANK = "BLOOD_BANK"

def date_time():
    return datetime.now().isoformat()

class UserInfo(BaseModel):
    user_id: str = Field()
    company_id: str = Field()

class ChatRequest(UserInfo):
    """
    Model for validating chat requests.
    """
    message: str = Field(..., min_length=1, max_length=1000)
    session_id: str = Field(default=get_session_id())
    created_at: str = Field(default_factory=get_current_datetime)

    @field_validator("message")
    def validate_message_content(cls, v):
        """
        Validator to ensure message content is not empty.
        """
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v
    
    ##Handle the messages not from the current day
    @field_validator("session_id")
    def validate_session_id(cls, v):
        """
        Validator to ensure session ID is not empty.
        """
        if v !=get_session_id():
            logger.error("Invalid session id")
            raise ValueError("invalid session id")
        return v
    
        
class ChatResponse(BaseModel):
    """
    Model for chat responses.
    """
    session_id: str = Field(default=get_session_id())
    response: str = Field(..., description="The chatbot's response to the user's message")
    created_at: str = Field(default_factory=get_current_datetime)
    conversation_id: Optional[str] = Field(..., description="Conversation ID for each request")

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

class FeedbackEnum(str, Enum):
    zero = "0"
    one = "1"

class FeedbackRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    feedback: FeedbackEnum = Field(..., description="Feedback must be '0' or '1'")
    conversation_id: str
    session_id: str = Field(default_factory=get_session_id, description="Session ID")


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

def is_valid_user(user_id:str)-> bool:
    return True

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()  # Track start time

    # Read and preserve request body
    try:
        body_bytes = await request.body()
    except Exception as e:
        logger.error(f"Failed to read request body: {e}")
        return JSONResponse({"error": "Invalid request body"}, status_code=400)

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}
    request._receive = receive

    # Parse body and extract user_id
    try:
        body = json.loads(body_bytes)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON format: {e}")
        return JSONResponse({"error": "Invalid JSON format"}, status_code=400)

    user_id = body.get("user_id")
    if not user_id:
        logger.warning("Missing user_id in request")
        return JSONResponse({"error": "Missing user_id"}, status_code=401)

    if not is_valid_user(user_id):  # checking custom check
        logger.warning(f"Unauthorized access attempt with user_id: {user_id}")
        return JSONResponse({"error": "Unauthorized user"}, status_code=401)

    logger.info(f"Incoming request: {request.method} {request.url.path} (User: {user_id})")
    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception(f"Unhandled error while processing request: {e}")
        return JSONResponse({"error": "Internal server error"}, status_code=500)

    process_time = round((time.time() - start_time) * 1000, 2)  # in ms
    logger.info(f"Request completed: {request.method} {request.url.path} (User: {user_id}) - {process_time}ms")

    return response

async def session_init(user_id: str,session_id):
    """
    Init endpoint - returns complete response at once
    """
    logger.info(f"session_init request details:{user_id} ")

    user_id = user_id
    session_id = session_id 
    created_at = store_datetime()
    conversation_id = get_message_unique_id()   

    hasura_client = HasuraMemory(hasura_url=HASURA_GRAPHQL_URL, hasura_secret=HASURA_ADMIN_SECRET, hasura_role=HASURA_ROLE, user_id=user_id)

    initial_response = random.choice(WELCOME_MESSAGES)
    
    variables = {
        "session_id": session_id,
        "user_id": user_id,
        "created_at":created_at,
        "title": session_id 
    }
    result = hasura_client.session_init(variables=variables)
    if not result:
        logger.error("Session init failed, unable to create session")
        return JSONResponse(status_code=500, content={"response": "There was an technical issue. Please try again later."})
    
    logger.info(f"Session init Success: {result}")
    return {"session_id":session_id,"response":initial_response,"created_at":created_at}

async def process_normal_message(req: ChatRequest):
    """Process message for normal response"""
    config = {"configurable": {"thread_id":req.session_id}}
    hasura_client = HasuraMemory(
        hasura_url=HASURA_GRAPHQL_URL,
        hasura_secret=HASURA_ADMIN_SECRET,
        hasura_role=HASURA_ROLE,
        user_id=req.user_id,
    )
    session_exists = hasura_client.check_session_exists(req.session_id)
    print("session_exists", session_exists)
    if not session_exists:
        session_response = await session_init(req.user_id, req.session_id)
    
    conversation_id = get_message_unique_id()

    try:
        response = generate_chat_response(chat_request = req,config = config,conversation_id=conversation_id)
        return ChatResponse(
            session_id=req.session_id,
            response=response,
            created_at=get_current_datetime(),
            conversation_id=conversation_id
        )
    except Exception as e:
        print("Main Error:", str(e))
        return ChatResponse(
            session_id=req.session_id,
            response="Oops! Looks like we've got a technical issue in our system. Please try again later.",
            created_at=req.created_at,
            conversation_id=conversation_id
        )

WELCOME_MESSAGES = [
    """👋 Welcome to Inhlth Assistant!
I'm here to help you explore blood supply and cost data. Ask me anything like:
• "Track my pending orders"
• "Show rejected orders from last week"
• "Give me cost details for June 2025"
""",
    """🩸 Hi there! This is Inhlth Assistant.
You can ask me to analyze blood supply data, order statuses, or monthly billing insights. Try:
• "Pending orders by Blood Bank A"
• "Orders for plasma in June"
""",
    """Hello! I'm Inhlth Assistant.
Need data insights on blood orders, costs, or deliveries? Ask something like:
• "How many deliveries happened last month?"
• "Give me stats for AB+ blood group"
""",
    """ Welcome back to Inhlth Assistant!
I'm ready to help with data analysis and order tracking. You can start with:
• "Show cost summary for last month"
• "Track O negative orders"
""",
    """ Hello from Inhlth Assistant!
Ask me anything about blood orders or billing insights. For example:
• "Orders rejected this week"
• "Total cost for red blood cells"
"""
]

@app.get("/ai_assistant/")
async def root():
    return {"message": "Chatbot API AI backend is live and operational!"}

@app.get("/ai_assistant/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "normal_chat": "/ai_assistant/chat",
            "history": "/ai_assistant/get_session_messages",
            "health": "/ai_assistant/health",
            "test": "/ai_assistant"
        }
    }

@app.post("/ai_assistant/feedback")
async def feedback_endpoint(req: FeedbackRequest):
    """
    Feedback endpoint - returns complete response at once
    """
    logger.info(f"Feedback Request: {req}")
    user_id = req.user_id
    hasura_obj = HasuraMemory(hasura_url=HASURA_GRAPHQL_URL, hasura_secret=HASURA_ADMIN_SECRET, hasura_role=HASURA_ROLE, user_id=user_id)
    conversation_id = req.conversation_id
    
    session_id = req.session_id
    feedback = req.feedback

    result = hasura_obj.add_feedback(conversation_id=conversation_id,session_id=session_id,feedback=feedback)
    return {"response": "Feedback added successfully!"}

@app.post("/ai_assistant/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Normal chat endpoint - returns complete response at once
    """
    logger.info(f"Chat Request: {req}")
    
    result = await process_normal_message(req)
    return result

@app.post("/ai_assistant/get_session_messages")
async def get_session_messages(req: HistoryRequest): 

    print("get_session_messages request details: ", req.session_id)
    hasura_obj = HasuraMemory(hasura_url=HASURA_GRAPHQL_URL, hasura_secret=HASURA_ADMIN_SECRET, hasura_role=HASURA_ROLE, user_id=req.user_id)

    try:
        history = hasura_obj.get_history({"configurable": {"thread_id": req.session_id}})
        if not history:
            return HistoryResponse(messages=[])
    except Exception as e:
        print(f"Error retrieving messages: {e}")
        return JSONResponse(status_code=500, content={"message": []})
    
    return HistoryResponse(messages=history)

@app.post("/ai_assistant/get_session_list")
async def get_session_list(req: UserInfo):
    print("get_session_list request details: ", req.user_id)
    hasura_obj = HasuraMemory(hasura_url=HASURA_GRAPHQL_URL, hasura_secret=HASURA_ADMIN_SECRET, hasura_role=HASURA_ROLE, user_id=req.user_id)

    try:
        session_list = hasura_obj.get_session_list()
        if not session_list:
            return {"sessions_list": []}
    except Exception as e:
        print(f"Error retrieving messages: {e}")
        return JSONResponse(status_code=500, content={"sessions": []})
    
    return {"sessions_list": session_list}



