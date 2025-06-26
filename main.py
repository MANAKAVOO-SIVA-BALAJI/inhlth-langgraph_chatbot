from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from fastapi.middleware.cors import CORSMiddleware

from enum import Enum
from datetime import datetime
import json
from chat import generate_chat_response
from fastapi import FastAPI, Request
from logging_config import setup_logger


class UserRole(str, Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    HOSPITAL = "HOSPITAL"
    BLOOD_BANK = "BLOOD_BANK"

def date_time():
    return datetime.utcnow().isoformat()

class ChatRequest(BaseModel):
    """
    Model for validating chat requests.
    """
    message: str = Field(..., min_length=1, max_length=1000)
    role: str = Field(default=UserRole.HOSPITAL)
    company_id: str = Field()
    user_id: str = Field()
    session_id: str = Field()
    timestamp: str = Field(default_factory=date_time)

    # message: str = Field(..., min_length=1, max_length=1000)
    # role: str = Field(default=None)
    # company_id: str = Field(default="CMP-RRPZYICLEG")
    # user_id: str = Field(default="USR-IHI6SJSYB0")
    # session_id: str = Field(default="CSI-A7PD1CV7YA")
    # timestamp: str = Field(default_factory=date_time)

    @field_validator("message")
    def validate_message_content(cls, v):
        """
        Validator to ensure message content is not empty.
        """
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v


logger = setup_logger()

app = FastAPI(title="LangGraph AI Chat Backend")

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
    """Process message for normal (non-streaming) response"""
    config = {"configurable": {"thread_id":req.session_id}} # req.session_id

    try:
        response = generate_chat_response(req, config)
        
        return {
            "session_id": req.session_id,
            # "response": "This is a test response. Data request received successfully, but no real call was made.",#response,
            "response":response,
            "timestamp": req.timestamp,
            "user_id": req.user_id,
            "company_id": req.company_id
        }
    except Exception as e:
        return {
            "session_id": req.session_id,
            "response": f"Error: {str(e)}",
            "timestamp": req.timestamp,
            "user_id": req.user_id,
            "company_id": req.company_id
        }


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Normal chat endpoint - returns complete response at once
    """
    result = await process_normal_message(req)
    return JSONResponse(content=result)


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


@app.get("/")
async def root():
    return {"message": "Chatbot API AI backend is live and operational!"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "normal_chat": "/chat"
        }
    }


if __name__ == "__main__":
    import uvicorn 
    
    print("Starting FastAPI server...")
    print("Available endpoints:")

    
    uvicorn.run(app, host="0.0.0.0", port=8000)

