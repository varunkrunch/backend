import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, ClassVar, Union, AsyncGenerator, Literal
from fastapi import APIRouter, HTTPException, Depends, Body, Query, status, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, validator, HttpUrl
from humanize import naturaltime
import asyncio
import logging
import uuid
import json
import time
import humanize
import re
from loguru import logger
from dotenv import load_dotenv
from collections import defaultdict
from enum import Enum

# Import domain models and services
from open_notebook.domain.notebook import Notebook, ChatSession as DomainChatSession
from open_notebook.graphs.chat import graph as chat_graph
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Set up logging
logger = logging.getLogger(__name__)

# Connection manager for SSE
class ConnectionManager:
    def __init__(self):
        self.active_connections = defaultdict(list)
        self.lock = asyncio.Lock()
        self.heartbeat_interval = 30  # seconds
    
    async def connect(self, session_id: str) -> asyncio.Queue:
        """Create a new connection queue for a session."""
        queue = asyncio.Queue(maxsize=100)  # Limit queue size to prevent memory issues
        async with self.lock:
            self.active_connections[session_id].append(queue)
        logger.info(f"New SSE connection for session {session_id}. Total connections: {len(self.active_connections[session_id])}")
        return queue
    
    async def disconnect(self, session_id: str, queue: asyncio.Queue):
        """Remove a connection queue for a session."""
        async with self.lock:
            if session_id in self.active_connections:
                if queue in self.active_connections[session_id]:
                    self.active_connections[session_id].remove(queue)
                    logger.info(f"SSE connection removed for session {session_id}. Remaining: {len(self.active_connections[session_id])}")
                if not self.active_connections[session_id]:
                    del self.active_connections[session_id]
                    logger.info(f"No more connections for session {session_id}. Session removed.")
    
    async def broadcast(self, session_id: str, message: dict):
        """Broadcast a message to all connections for a session."""
        async with self.lock:
            if session_id in self.active_connections:
                dead_queues = []
                for queue in self.active_connections[session_id]:
                    try:
                        # Non-blocking put with timeout
                        queue.put_nowait(message)
                    except asyncio.QueueFull:
                        logger.warning(f"Queue full for session {session_id}. Message dropped.")
                    except Exception as e:
                        logger.error(f"Error sending message to session {session_id}: {str(e)}")
                        dead_queues.append(queue)
                
                # Clean up dead queues
                for queue in dead_queues:
                    if queue in self.active_connections[session_id]:
                        self.active_connections[session_id].remove(queue)
    
    async def get_connection_count(self, session_id: str) -> int:
        """Get the number of active connections for a session."""
        async with self.lock:
            return len(self.active_connections.get(session_id, []))

# Global connection manager
connection_manager = ConnectionManager()

# Load environment variables
load_dotenv()

# Initialize LLM with API key from .env
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.warning("OPENAI_API_KEY not found in .env file")

# Configure LLM
llm = ChatOpenAI(
    api_key=openai_api_key,
    model_name=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
    temperature=float(os.getenv("OPENAI_TEMPERATURE", 0.7)),
)

# Cache for notebook name to ID mapping
notebook_name_cache = {}

# Configure chat graph with the LLM
# The chat_graph is already compiled, so we'll pass the LLM directly when invoking it

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    responses={404: {"description": "Not found"}},
)

# We'll use the database for chat sessions instead of in-memory storage
# ChatSession class from domain.notebook will handle the persistence

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex}")
    role: MessageRole = MessageRole.USER
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def dict(self, **kwargs):
        # Convert datetime to ISO format string for serialization
        result = super().model_dump(**kwargs)
        if isinstance(result.get('timestamp'), datetime):
            result['timestamp'] = result['timestamp'].isoformat()
        return result

class ChatMessageRequest(BaseModel):
    message: str = Field(..., description="The message content from the user")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context for the chat")
    session_name: Optional[str] = Field(None, description="Optional name for a new chat session")
    message_id: Optional[str] = Field(None, description="Optional client-generated message ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Hello, how are you?",
                "context": {
                    "note": [],
                    "source": []
                }
            }
        }

class ChatMessageResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex}")
    role: str = Field(..., description="The role of the message sender (user/assistant)")
    content: str = Field(..., description="The message content")
    session_id: str = Field(..., description="The session ID for this conversation")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat(),
                         description="ISO formatted timestamp of the response")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    type: str = Field(default="text", description="Type of the message (text/markdown)")
    
    def model_dump(self, **kwargs):
        # Convert to dict with proper serialization
        result = super().model_dump(**kwargs)
        # Ensure timestamp is always a string
        if isinstance(result.get('timestamp'), datetime):
            result['timestamp'] = result['timestamp'].isoformat()
        # Add type field if not present
        if 'type' not in result:
            result['type'] = "text"
        return result

class ChatEventType(str, Enum):
    MESSAGE = "message"
    SESSION_UPDATE = "session_update"
    ERROR = "error"

class ChatEvent(BaseModel):
    event: ChatEventType
    data: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Hello! How can I help you today?",
                "session_id": "chat_session:12345",
                "timestamp": "2023-01-01T12:00:00Z"
            }
        }

class ChatSessionResponse(BaseModel):
    id: str = Field(..., description="Unique identifier for the chat session")
    title: str = Field(..., description="Title of the chat session")
    created_at: str = Field(..., description="ISO formatted creation timestamp")
    updated_at: str = Field(..., description="ISO formatted last update timestamp")
    messages: List[Dict[str, Any]] = Field(..., description="List of messages in the session")
    notebook_id: Optional[str] = Field(None, description="ID of the notebook this session belongs to")

    @validator('created_at', 'updated_at', pre=True)
    def format_timestamp(cls, v):
        if isinstance(v, str):
            return v
        return v.isoformat() if v else None

    @classmethod
    def from_domain(cls, session: DomainChatSession) -> 'ChatSessionResponse':
        return cls(
            id=str(session.id),
            title=session.title,
            created_at=session.created,
            updated_at=session.updated,
            messages=getattr(session, 'messages', []),
            notebook_id=getattr(session, 'notebook_id', None)
        )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

def get_notebook_by_name_or_id(identifier: str) -> Notebook:
    """Helper function to get notebook by name or ID"""
    try:
        # Check cache first
        if identifier in notebook_name_cache:
            return notebook_name_cache[identifier]
            
        # Try to get by ID first (format: "notebook:123")
        if ":" in identifier:
            notebook = Notebook.get(identifier)
            if notebook:
                notebook_name_cache[identifier] = notebook
                return notebook
        
        # Try to get by name
        notebooks = Notebook.get_all()
        for nb in notebooks:
            if hasattr(nb, 'name') and nb.name == identifier:
                notebook_name_cache[identifier] = nb
                return nb
                
        raise HTTPException(status_code=404, detail=f"Notebook '{identifier}' not found")
    except Exception as e:
        logger.error(f"Error getting notebook {identifier}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error finding notebook")

def _save_session_messages(session_id: str, messages: list) -> bool:
    """
    Helper function to save messages for a session.
    
    Args:
        session_id: The ID of the session to save messages for
        messages: List of message dictionaries to save
        
    Returns:
        bool: True if messages were saved successfully, False otherwise
    """
    if not messages:
        logger.warning(f"No messages provided to save for session {session_id}")
        return False
        
    try:
        # Validate input
        if not isinstance(messages, list):
            logger.error(f"Messages must be a list, got {type(messages).__name__}")
            return False
            
        # Get the session with retry logic
        max_retries = 3
        retry_delay = 0.5  # seconds
        
        for attempt in range(max_retries):
            try:
                session = DomainChatSession.get(session_id)
                if not session:
                    logger.error(f"Session {session_id} not found when saving messages")
                    return False
                
                # Initialize messages list if it doesn't exist
                if not hasattr(session, 'messages') or not isinstance(session.messages, list):
                    session.messages = []
                
                # Process and validate each message
                valid_messages = []
                for i, msg in enumerate(messages):
                    if not isinstance(msg, dict):
                        logger.warning(f"Skipping invalid message at index {i}: not a dictionary")
                        continue
                        
                    # Extract message data with validation
                    role = msg.get('role', 'user' if msg.get('type') == 'human' else 'ai')
                    content = msg.get('content', '')
                    
                    # Validate content
                    if not content or not isinstance(content, str):
                        logger.warning(f"Skipping message at index {i}: invalid content")
                        continue
                    
                    # Prepare message metadata
                    metadata = msg.get('metadata', {})
                    if not isinstance(metadata, dict):
                        metadata = {}
                    
                    # Add timestamp if not present
                    if 'timestamp' not in metadata:
                        metadata['timestamp'] = datetime.utcnow().isoformat()
                    
                    valid_messages.append({
                        'role': role,
                        'content': content,
                        'metadata': metadata
                    })
                
                if not valid_messages:
                    logger.warning("No valid messages to save")
                    return False
                
                # Clear existing messages and add new ones
                # This ensures we maintain a single source of truth
                session.messages = []
                for msg in valid_messages:
                    session.add_message(
                        role=msg['role'],
                        content=msg['content'],
                        **msg['metadata']
                    )
                
                # Enforce message limit (prevent excessive memory usage)
                max_messages = int(os.getenv('MAX_CHAT_MESSAGES', '100'))
                if len(session.messages) > max_messages:
                    logger.info(f"Truncating message history from {len(session.messages)} to {max_messages} messages")
                    session.messages = session.messages[-max_messages:]
                
                # Update timestamp and save
                session.updated = datetime.utcnow()
                session.save()
                
                logger.debug(f"Successfully saved {len(valid_messages)} messages to session {session_id}")
                return True
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Error saving messages (attempt {attempt + 1}/{max_retries}): {str(e)}")
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                raise
                
    except Exception as e:
        logger.error(f"Critical error saving session messages: {str(e)}", exc_info=True)
        return False

def get_or_create_chat_session(
    notebook_id: str, 
    session_identifier: str = None, 
    session_name: str = None
) -> DomainChatSession:
    """Helper function to get or create a chat session with messages support
    
    Args:
        notebook_id: ID of the notebook this session belongs to
        session_identifier: Either the session ID (format: 'table:id'), session name, or None to create a new session
        session_name: Optional name for a new session (only used when creating a new session)
        
    Returns:
        DomainChatSession: The found or created chat session
    """
    try:
        # Try to find the session by ID or name if session_identifier is provided
        if session_identifier:
            # Try to get by ID first if it looks like an ID (contains a colon)
            if ":" in session_identifier:
                try:
                    domain_session = DomainChatSession.get(session_identifier)
                    if domain_session:
                        # Ensure messages is a list
                        if not hasattr(domain_session, 'messages') or not isinstance(domain_session.messages, list):
                            domain_session.messages = []
                        return domain_session
                except Exception as e:
                    logger.warning(f"Error getting session by ID {session_identifier}: {str(e)}")
            
            # If not found by ID or not an ID format, try to find by name
            try:
                sessions = DomainChatSession.find(title=session_identifier)
                if sessions:
                    # Return the most recently updated session with this title
                    domain_session = max(sessions, key=lambda s: s.updated if hasattr(s, 'updated') else datetime.min)
                    if not hasattr(domain_session, 'messages') or not isinstance(domain_session.messages, list):
                        domain_session.messages = []
                    return domain_session
            except Exception as e:
                logger.warning(f"Error finding session by name '{session_identifier}': {str(e)}")
        
        # If we get here, we need to create a new session
        # Use the provided session_name or create a default one
        title = ""
        if session_name and session_name.strip():
            title = session_name.strip()
        
        if not title:
            # Create a default title with timestamp
            now = datetime.now()
            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            title = f"Chat Session - {timestamp}"
        
        logger.info(f"Creating new chat session with title: {title}")
        
        # Ensure notebook exists
        notebook = get_notebook_by_name_or_id(notebook_id)
        if not notebook:
            logger.error(f"Notebook {notebook_id} not found")
            raise HTTPException(status_code=404, detail=f"Notebook {notebook_id} not found")
            
        # Create the session with the title in the metadata
        domain_session = DomainChatSession(
            title=title,
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
            messages=[],
            metadata={
                "notebook_id": notebook_id, 
                "created_at": datetime.utcnow().isoformat(),
                "title": title  # Also store title in metadata for easier retrieval
            }
        )
        domain_session.save()
        
        # Relate it to the notebook
        try:
            domain_session.relate_to_notebook(notebook.id)
            logger.info(f"Successfully related chat session to notebook {notebook_id}")
        except Exception as e:
            logger.warning(f"Failed to relate session to notebook {notebook_id}: {str(e)}")
            logger.exception(e)
            # Continue even if relation fails, as the session is still created
        
        return domain_session
        
    except Exception as e:
        logger.error(f"Error getting/creating chat session: {str(e)}")
        logger.exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create chat session: {str(e)}"
        )

@router.post(
    "/message",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Chat response generated successfully"},
        400: {"description": "Invalid request parameters"},
        404: {"description": "Notebook or session not found"},
        500: {"description": "Internal server error"},
    },
    summary="Send a chat message and get a response",
    description="""
    Send a message to the chat and get a response. This endpoint works similarly to the Streamlit interface,
    maintaining session state and returning the full response in a single call when used with Swagger.
    """
)
async def send_message(
    request: ChatMessageRequest,
    notebook_id: str = Query(..., description="Name or ID of the notebook this chat belongs to"),
    session_id: Optional[str] = Query(None, description="Optional session ID to continue a conversation"),
):
    """
    Send a message to the chat and get a response.
    
    This endpoint handles both new conversations and continuing existing ones.
    If no session is provided, a new chat session will be created.
    
    Request body can include:
    - message: The message content (required)
    - context: Additional context for the chat (optional)
    - session_name: Name for a new chat session (optional, only used when creating a new session)
    - message_id: Optional client-generated message ID
    """
    try:
        # Validate the message
        if not request.message or not request.message.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message cannot be empty"
            )

        # Get or create the chat session
        is_new_session = session_id is None
        
        # Generate a session name if not provided for new sessions
        session_name = None
        if is_new_session and request.session_name and request.session_name.strip():
            session_name = request.session_name.strip()
        
        chat_session = get_or_create_chat_session(
            notebook_id=notebook_id,
            session_identifier=session_id,
            session_name=session_name if is_new_session else None
        )
        
        if not chat_session:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create or retrieve chat session"
            )
        
        # Create user message with consistent format
        current_time = datetime.utcnow().isoformat()
        user_message = {
            "id": request.message_id or f"msg_{uuid.uuid4().hex}",
            "type": "text",
            "role": "user",
            "content": request.message.strip(),
            "timestamp": current_time,
            "metadata": {}
        }
        
        # Add user message to session
        if not hasattr(chat_session, 'messages') or not isinstance(chat_session.messages, list):
            chat_session.messages = []
        
        chat_session.messages.append(user_message)
        chat_session.updated = datetime.utcnow()
        
        # Save the updated session
        try:
            chat_session.save()
        except Exception as e:
            logger.error(f"Error saving chat session: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save chat session"
            )
        
        # Broadcast the user message to all connected clients in the format expected by Streamlit
        await connection_manager.broadcast(
            session_id=str(chat_session.id),
            message={
                "id": user_message["id"],
                "role": "user",
                "content": user_message["content"],
                "timestamp": user_message["timestamp"]
            }
        )
        
        # Generate AI response
        try:
            # Prepare the input for the chat graph
            chat_input = {
                "messages": chat_session.messages,
                "context": request.context or {}
            }
            
            # Generate a unique message ID for the AI response
            ai_message_id = f"msg_{uuid.uuid4().hex}"
            
            # Create AI message with consistent format
            current_time = datetime.utcnow().isoformat()
            ai_message = {
                "id": ai_message_id,
                "type": "text",
                "role": "assistant",
                "content": "",
                "timestamp": current_time,
                "metadata": {}
            }
            
            # Add initial AI message to session
            chat_session.messages.append(ai_message)
            
            # Configure the runnable with async support
            config = RunnableConfig(
                configurable={
                    "thread_id": str(chat_session.id),
                    "notebook_id": notebook_id,
                    "session_id": str(chat_session.id)
                }
            )
            
            # First, save the user message to the session
            chat_session.save()
            
            # For Swagger/API clients, we'll collect the full response first
            full_response = ""
            
            try:
                # Log the chat input for debugging
                logger.info(f"Sending chat input to model: {chat_input}")
                
                # Get the full response first for API clients
                result = chat_graph.invoke(chat_input, config=config)
                
                if "messages" in result and result["messages"]:
                    last_message = result["messages"][-1]
                    
                    # Handle different message content formats
                    if hasattr(last_message, 'content'):
                        chunk_content = last_message.content
                        
                        if isinstance(chunk_content, str):
                            full_response = chunk_content
                        elif isinstance(chunk_content, list) and chunk_content:
                            # Handle case where content is a list of content blocks
                            full_response = " ".join(
                                block.text if hasattr(block, 'text') else str(block)
                                for block in chunk_content
                                if hasattr(block, 'text') or block
                            )
                        else:
                            full_response = str(chunk_content)
                    
                    # Update the AI message with the full response
                    if full_response.strip():
                        ai_message["content"] = full_response
                        
                        # Broadcast the AI response chunk to all connected clients in the format expected by Streamlit
                        await connection_manager.broadcast(
                            session_id=str(chat_session.id),
                            message={
                                "id": ai_message_id,
                                "role": "assistant",
                                "content": chunk_content,
                                "timestamp": current_time
                            }
                        )
                        
                        # Update the response content for the API response
                        response_content = full_response
            
            except Exception as e:
                logger.error(f"Error generating response: {str(e)}", exc_info=True)
                error_msg = f"I'm sorry, I encountered an error: {str(e)}"
                ai_message["content"] = error_msg
                ai_message["metadata"]["error"] = str(e)
                response_content = error_msg
                
                await connection_manager.broadcast(
                    session_id=str(chat_session.id),
                    message={
                        "event": "error",
                        "message": ai_message
                    }
                )
            
            # Update the AI message with the final content
            ai_message["content"] = response_content
            ai_message["timestamp"] = datetime.utcnow().isoformat()
            
            # Update the session with the final AI message
            if chat_session.messages and chat_session.messages[-1]["id"] == ai_message_id:
                chat_session.messages[-1] = ai_message
            else:
                chat_session.messages.append(ai_message)
            
            # Final save of the session with updated timestamp
            chat_session.updated = datetime.utcnow()
            chat_session.save()
            
            # Broadcast the final message to any streaming clients
            await connection_manager.broadcast(
                session_id=str(chat_session.id),
                message={
                    "event": "message_complete",
                    "message": ai_message
                }
            )
            
            # Format the response to match frontend expectations
            response_data = {
                "id": ai_message_id,
                "role": "assistant",
                "content": response_content,
                "session_id": str(chat_session.id),
                "timestamp": ai_message["timestamp"],
                "type": "text",
                "metadata": ai_message.get("metadata", {})
            }
            
            return JSONResponse(
                content=response_data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error generating AI response: {str(e)}", exc_info=True)
            
            # Create an error message
            error_id = f"err_{uuid.uuid4().hex}"
            error_message = {
                "id": error_id,
                "type": "ai",
                "role": "assistant",
                "content": f"I'm sorry, I encountered an error: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {"error": True}
            }
            
            # Add error to session
            chat_session.messages.append(error_message)
            chat_session.updated = datetime.now(timezone.utc)
            chat_session.save()
            
            # Broadcast the error
            await connection_manager.broadcast(
                session_id=str(chat_session.id),
                message={
                    "event": "error",
                    "message": error_message,
                    "error": str(e)
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error generating response: {str(e)}"
            )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in send_message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your request"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_message: {str(e)}")
        logger.exception(e)
        raise HTTPException(
            status_code=500, 
            detail="An unexpected error occurred while processing your request."
        )

@router.get("/sessions/{notebook_id}", response_model=List[ChatSessionResponse])
async def list_sessions(notebook_id: str):
    """
    List all chat sessions for a notebook.
    
    Returns a list of chat sessions ordered by most recently updated.
    """
    try:
        # Get the notebook to access its chat sessions
        try:
            notebook = Notebook.get(notebook_id)
            if not notebook:
                raise HTTPException(status_code=404, detail="Notebook not found")
                
            # Get chat sessions for this notebook
            sessions = notebook.chat_sessions
            
            # Convert to response model
            session_list = []
            for session in sessions:
                # Try to get the title from the session's metadata if it exists
                title = None
                if hasattr(session, 'metadata') and isinstance(session.metadata, dict) and 'title' in session.metadata:
                    title = session.metadata['title']
                
                # Fall back to the session title or a default
                if not title and hasattr(session, 'title') and session.title:
                    title = session.title
                
                # If we still don't have a title, use the first message if available
                if not title and hasattr(session, 'messages') and session.messages and len(session.messages) > 0:
                    first_message = session.messages[0]
                    if isinstance(first_message, dict) and 'content' in first_message:
                        truncated = (first_message['content'][:50] + '...') if len(first_message['content']) > 50 else first_message['content']
                        title = f"Chat: {truncated}"
                
                # Final fallback
                if not title:
                    title = f"Chat Session {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
                
                session_list.append({
                    "id": str(session.id),
                    "title": title,
                    "created_at": session.created.isoformat() if hasattr(session, 'created') else datetime.utcnow().isoformat(),
                    "updated_at": session.updated.isoformat() if hasattr(session, 'updated') else datetime.utcnow().isoformat(),
                    "messages": session.messages[-10:] if hasattr(session, 'messages') and session.messages else []
                })
            
            # Sort by updated_at in descending order
            session_list.sort(key=lambda x: x["updated_at"], reverse=True)
            return session_list
            
        except Exception as e:
            logger.error(f"Error fetching chat sessions for notebook {notebook_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Error fetching chat sessions")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in list_sessions: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

@router.get("/sessions/{session_identifier}", response_model=ChatSessionResponse)
async def get_session(session_identifier: str):
    """
    Get details of a specific chat session by ID or name.
    
    Args:
        session_identifier: Either the session ID (format: 'table:id') or session name
        
    Returns:
        ChatSessionResponse: The chat session details including messages
        
    Raises:
        HTTPException: 404 if session not found, 500 for server errors
    """
    try:
        session = None
        
        # Try to get by ID first if it looks like an ID (contains a colon)
        if ":" in session_identifier:
            try:
                session = DomainChatSession.get(session_identifier)
            except Exception as e:
                logger.warning(f"Error getting session by ID {session_identifier}: {str(e)}")
        
        # If not found by ID, try to find by name
        if not session:
            try:
                sessions = DomainChatSession.find(title=session_identifier)
                if sessions:
                    # Return the most recently updated session with this title
                    session = max(sessions, key=lambda s: s.updated if hasattr(s, 'updated') else datetime.min)
            except Exception as e:
                logger.warning(f"Error finding session by name '{session_identifier}': {str(e)}")
        
        if not session:
            raise HTTPException(status_code=404, detail=f"Chat session '{session_identifier}' not found")
        
        # Ensure messages is a list
        if not hasattr(session, 'messages') or not isinstance(session.messages, list):
            session.messages = []
            
        return {
            "id": str(session.id),
            "title": session.title or "Untitled Chat",
            "created_at": session.created.isoformat() if hasattr(session, 'created') else datetime.utcnow().isoformat(),
            "updated_at": session.updated.isoformat() if hasattr(session, 'updated') else datetime.utcnow().isoformat(),
            "messages": session.messages
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching chat session {session_identifier}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching chat session")

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a chat session.
    
    This will permanently remove the chat session and all its messages.
    """
    try:
        session = await DomainChatSession.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        await session.delete()
        
        # Notify all connected clients that this session was deleted
        await connection_manager.broadcast(
            session_id=session_id,
            message={
                "event": "session_deleted",
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
        return {"status": "success", "message": "Session deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")


@router.get("/events/{session_id}")
async def chat_events(session_id: str, request: Request):
    """
    Server-Sent Events (SSE) endpoint for real-time chat updates.
    
    This endpoint maintains a persistent connection with the client and sends
    real-time updates about chat messages and session changes.
    
    The Streamlit frontend expects events in the format:
    ```
    event: message
    data: {"event": "new_message", "message": {...}}
    ```
    """
    # Check if client supports SSE
    accept_header = request.headers.get("Accept", "")
    if "text/event-stream" not in accept_header:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="Client does not support Server-Sent Events. 'Accept: text/event-stream' header is required.",
        )
    
    logger.info(f"New SSE connection for session {session_id} from {request.client.host if request.client else 'unknown'}")
    
    # Validate session exists
    try:
        session = DomainChatSession.get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            async def error_generator():
                yield "event: error\ndata: {\"error\": \"Session not found\"}\n\n"
            return StreamingResponse(
                error_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/event-stream",
                    "X-Accel-Buffering": "no",
                },
            )
    except Exception as e:
        logger.error(f"Error validating session {session_id}: {str(e)}")
        async def validation_error_generator():
            yield "event: error\ndata: {\"error\": \"Error validating session\"}\n\n"
        return StreamingResponse(
            validation_error_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
                "X-Accel-Buffering": "no",
            },
        )
    
    # Create a new queue for this connection
    queue = await connection_manager.connect(session_id)
    
    async def event_generator():
        """Generator function that yields SSE events."""
        last_activity = time.time()
        
        try:
            while True:
                # Check if client has disconnected
                if await request.is_disconnected():
                    logger.info(f"Client disconnected from session {session_id}")
                    break
                
                # Calculate time since last activity
                idle_time = time.time() - last_activity
                
                # If we've been idle too long, send a heartbeat
                if idle_time >= 25:  # Slightly less than the client's reconnection time
                    try:
                        yield ":heartbeat\n\n"
                        last_activity = time.time()
                        continue
                    except Exception as e:
                        logger.error(f"Error sending heartbeat: {str(e)}")
                        break
                
                # Wait for a new message with a timeout
                try:
                    # Use a short timeout to allow for periodic heartbeats
                    timeout = min(30.0, 25 - idle_time)
                    message = await asyncio.wait_for(queue.get(), timeout=timeout)
                    
                    # Format the message as expected by the Streamlit frontend
                    # The frontend expects a simple JSON object with id, role, content, and timestamp
                    message_data = {
                        "id": message.get("id", f"msg_{uuid.uuid4().hex}"),
                        "role": message.get("role", "assistant"),
                        "content": message.get("content", ""),
                        "timestamp": message.get("timestamp", datetime.utcnow().isoformat())
                    }
                    
                    # Send the message as an SSE event
                    yield f"event: message\ndata: {json.dumps(message_data)}\n\n"
                    last_activity = time.time()
                    
                except asyncio.TimeoutError:
                    # This will trigger the idle check and send a heartbeat
                    continue
                    
                except asyncio.CancelledError:
                    logger.info(f"SSE connection cancelled for session {session_id}")
                    break
                    
        except Exception as e:
            logger.error(f"Error in SSE stream for session {session_id}: {str(e)}", exc_info=True)
            
        finally:
            # Clean up the connection
            try:
                await connection_manager.disconnect(session_id, queue)
            except Exception as e:
                logger.error(f"Error during SSE connection cleanup: {str(e)}")
    
    # Set up SSE response with appropriate headers
    response_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream",
        "X-Accel-Buffering": "no",  # Disable buffering in nginx
        "Access-Control-Allow-Origin": "*",
    }
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=response_headers,
    )
