import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, ClassVar, Union, AsyncGenerator, Literal
from fastapi import APIRouter, HTTPException, Depends, Body, Query, status, Request, Response
from src.database import get_db_connection
from surrealdb import AsyncSurreal
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
                try:
                    self.active_connections[session_id].remove(queue)
                    logger.info(f"Disconnected SSE client for session {session_id}. Remaining connections: {len(self.active_connections[session_id])}")
                except ValueError:
                    pass  # Queue was already removed
    
    async def broadcast(self, session_id: str, message: dict):
        """Broadcast a message to all connected clients for a session."""
        async with self.lock:
            if session_id in self.active_connections:
                for queue in self.active_connections[session_id][:]:  # Copy list to avoid modification during iteration
                    try:
                        queue.put_nowait(message)
                    except asyncio.QueueFull:
                        logger.warning(f"Queue full for session {session_id}, removing connection")
                        self.active_connections[session_id].remove(queue)
                    except Exception as e:
                        logger.error(f"Error broadcasting to session {session_id}: {e}")
                        try:
                            self.active_connections[session_id].remove(queue)
                        except ValueError:
                            pass
    
    async def get_connection_count(self, session_id: str) -> int:
        """Get the number of active connections for a session."""
        async with self.lock:
            return len(self.active_connections.get(session_id, []))

# Global connection manager
connection_manager = ConnectionManager()

# Load environment variables
load_dotenv()

# Create router for chat endpoints
router = APIRouter(
    prefix="/api/v1/chat",
    tags=["Chat"],
)

# Pydantic models
class ChatMessageRequest(BaseModel):
    message: str = Field(..., description="The message content")
    session_name: Optional[str] = Field(None, description="Name for a new chat session")
    message_id: Optional[str] = Field(None, description="Client-generated message ID")
    context: Optional[str] = Field(None, description="Additional context for the chat")
    context_config: Optional[Dict[str, str]] = Field(None, description="Context configuration for sources and notes")

class ChatMessageResponse(BaseModel):
    id: str
    content: str
    role: str
    timestamp: str
    session_id: str
    notebook_id: str
    metadata: Dict[str, Any] = {}

class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created: str
    updated: str
    message_count: int
    notebook_id: str

class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]
    notebook_id: str

async def build_context_for_notebook(notebook_id: str, db: AsyncSurreal, context_config: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Build context for a notebook exactly like Streamlit's build_context function.
    This replicates the Streamlit context building logic with full source insights and note content.
    """
    try:
        # Get the notebook ID if we were given a name
        actual_notebook_id = notebook_id
        if not notebook_id.startswith('notebook:'):
            notebook_query = "SELECT * FROM notebook WHERE name = $name"
            notebook_result = await db.query(notebook_query, {"name": notebook_id})
            if notebook_result and len(notebook_result) > 0:
                notebook_data = dict(notebook_result[0])
                actual_notebook_id = str(notebook_data.get('id', ''))
            else:
                return {"note": [], "source": []}
        
        # Build context like Streamlit does - initialize with empty lists
        context = {"note": [], "source": []}
        
        # Default context config if not provided (include all sources and notes)
        if context_config is None:
            context_config = {}
        
        # Get sources for the notebook
        try:
            # Query sources for this notebook using the reference relation
            all_refs_query = "SELECT * FROM reference"
            all_refs = await db.query(all_refs_query)
            
            # Filter references for this specific notebook
            source_ids = []
            notebook_record_id = actual_notebook_id.split(':')[-1] if ':' in actual_notebook_id else actual_notebook_id
            
            for ref in all_refs:
                if 'out' in ref and 'in' in ref:
                    out_id = ref['out']
                    out_id_str = str(out_id)
                    if ':' in out_id_str:
                        out_record_id = out_id_str.split(':')[-1]
                        if out_record_id == notebook_record_id:
                            source_id = ref['in']
                            if hasattr(source_id, 'table_name') and hasattr(source_id, 'record_id'):
                                source_id_str = f"{source_id.table_name}:{source_id.record_id}"
                            else:
                                source_id_str = str(source_id)
                            source_ids.append(source_id_str)
            
            # Fetch sources and build context with insights
            if source_ids:
                all_sources_query = "SELECT * FROM source"
                all_sources_result = await db.query(all_sources_query)
                source_id_set = set(source_ids)
                
                for source_data in all_sources_result:
                    source_dict = dict(source_data)
                    source_id_str = str(source_dict.get('id', ''))
                    
                    if source_id_str in source_id_set:
                        # Check context config for this source
                        source_status = context_config.get(source_id_str, "🟢 full content")
                        
                        # Skip if not in context
                        if "not in" in source_status:
                            continue
                        
                        # Get source insights
                        insights_query = "SELECT * FROM source_insight WHERE source = $source_id"
                        insights_result = await db.query(insights_query, {"source_id": source_id_str})
                        insights = [dict(insight) for insight in insights_result] if insights_result else []
                        
                        # Build context like Streamlit's get_context method
                        if "insights" in source_status:
                            # Short context - insights only
                            source_context = {
                                "id": source_id_str,
                                "title": source_dict.get('title', 'Untitled'),
                                "insights": insights
                            }
                        elif "full content" in source_status:
                            # Long context - insights + full text
                            source_context = {
                                "id": source_id_str,
                                "title": source_dict.get('title', 'Untitled'),
                                "insights": insights,
                                "full_text": source_dict.get('full_text', '')
                            }
                        else:
                            # Default to full content
                            source_context = {
                                "id": source_id_str,
                                "title": source_dict.get('title', 'Untitled'),
                                "insights": insights,
                                "full_text": source_dict.get('full_text', '')
                            }
                        
                        context["source"].append(source_context)
        
        except Exception as e:
            logger.error(f"Error fetching sources for context: {str(e)}")
        
        # Get notes for the notebook
        try:
            notes_query = """
                SELECT note.* FROM note 
                INNER JOIN artifact ON note.id = artifact.in 
                WHERE artifact.out = $notebook_id
            """
            notes_result = await db.query(notes_query, {"notebook_id": actual_notebook_id})
            
            for note_data in notes_result:
                note_dict = dict(note_data)
                note_id_str = str(note_dict.get('id', ''))
                
                # Check context config for this note
                note_status = context_config.get(note_id_str, "🟢 full content")
                
                # Skip if not in context
                if "not in" in note_status:
                    continue
                    
                # Build context like Streamlit's get_context method
                if "full content" in note_status:
                    # Long context - full content
                    note_context = {
                        "id": note_id_str,
                        "title": note_dict.get('title', 'Untitled'),
                        "content": note_dict.get('content', '')
                    }
                else:
                    # Short context - truncated content
                    content = note_dict.get('content', '')
                    note_context = {
                        "id": note_id_str,
                        "title": note_dict.get('title', 'Untitled'),
                        "content": content[:100] if content else None
                    }
                
                context["note"].append(note_context)
        
        except Exception as e:
            logger.error(f"Error fetching notes for context: {str(e)}")
        
        return context
    except Exception as e:
        logger.error(f"Error building context: {str(e)}")
        return {"note": [], "source": []}

def get_or_create_chat_session(notebook_id: str, session_identifier: Optional[str] = None, session_name: Optional[str] = None) -> Optional[DomainChatSession]:
    """
    Get an existing chat session or create a new one, exactly like Streamlit does.
    """
    try:
        if session_identifier:
            # Try to get existing session
            try:
                session = DomainChatSession.get(session_identifier)
                if session:
                    return session
            except Exception as e:
                logger.warning(f"Could not retrieve session {session_identifier}: {e}")
        
        # Create new session
        session = DomainChatSession(
            title=session_name or f"Chat Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            messages=[],
            metadata={}
        )
        session.save()
        
        # Relate to notebook
        session.relate_to_notebook(notebook_id)
        
        return session
        
    except Exception as e:
        logger.error(f"Error creating chat session: {str(e)}")
        return None

@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    request: ChatMessageRequest,
    notebook_id: str = Query(..., description="Name or ID of the notebook this chat belongs to"),
    session_id: Optional[str] = Query(None, description="Optional session ID to continue a conversation"),
    db: AsyncSurreal = Depends(get_db_connection),
):
    """
    Send a message to the chat and get a response.
    
    This endpoint works exactly like the Streamlit chat functionality:
    1. Uses the same context building logic
    2. Uses the same chat graph processing
    3. Uses the same message format and state management
    4. Maintains session state exactly like Streamlit
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
        
        # Create user message with the same format as Streamlit
        current_time = datetime.now(timezone.utc).isoformat()
        user_message = {
            "type": "human", 
            "content": request.message.strip(),
            "timestamp": current_time
        }
        
        # Add user message to session (same as Streamlit)
        if not hasattr(chat_session, 'messages') or not isinstance(chat_session.messages, list):
            chat_session.messages = []
        
        chat_session.messages.append(user_message)
        chat_session.updated = datetime.now(timezone.utc)
        
        # Save user message to database
        try:
            session_id_str = str(chat_session.id)
            # Update session in database
            update_session_query = """
                UPDATE chat_session SET 
                messages = $messages,
                    updated = time::now()
                WHERE id = $session_id
                """
            await db.query(update_session_query, {
                    "session_id": session_id_str,
                "messages": chat_session.messages
            })
            
        except Exception as e:
            logger.error(f"Error saving chat session to database: {str(e)}")
        
        # Broadcast the user message to all connected clients
        await connection_manager.broadcast(
            session_id=str(chat_session.id),
            message={
                "id": f"user_{uuid.uuid4().hex}",
                "role": "user",
                "content": user_message["content"],
                "timestamp": user_message["timestamp"]
            }
        )
        
        # Generate AI response using the same approach as Streamlit
        # Build context the same way as Streamlit with context config
        context_config = request.context_config or {}
        context = await build_context_for_notebook(notebook_id, db, context_config)
        
        # Convert context to string format like Streamlit expects
        context_str = ""
        if context.get("source"):
            context_str += "Available sources:\n"
            for source in context["source"]:
                context_str += f"- {source['title']} (ID: {source['id']})\n"
                if source.get('insights'):
                    context_str += f"  Insights: {len(source['insights'])} insights\n"
                if source.get('full_text'):
                    context_str += f"  Content: {len(source['full_text'])} characters\n"
        
        if context.get("note"):
            context_str += "\nAvailable notes:\n"
            for note in context["note"]:
                context_str += f"- {note['title']} (ID: {note['id']})\n"
                if note.get('content'):
                    context_str += f"  Content: {len(note['content'])} characters\n"
        
        # Prepare the chat input in the same format as Streamlit
        chat_input = {
            "messages": chat_session.messages,
            "context": context_str.strip(),
            "notebook": {"id": notebook_id, "name": notebook_id},
            "context_config": context_config
        }
        
        # Use the same chat graph as Streamlit with proper config
        config = RunnableConfig(configurable={"thread_id": str(chat_session.id)})
        
        logger.info(f"Invoking chat graph with input: {chat_input}")
        
        # Get the AI response using the same method as Streamlit
        result = chat_graph.invoke(chat_input, config=config)
        
        # Process the result the same way as Streamlit
        if "messages" in result and len(result["messages"]) > len(chat_session.messages):
            ai_message = result["messages"][-1]  # Get the latest message (AI response)
            
            # Extract content from the AI message
            if hasattr(ai_message, 'content'):
                full_response = ai_message.content
            elif isinstance(ai_message, dict):
                full_response = ai_message.get('content', '')
            else:
                full_response = str(ai_message)
            
            logger.info(f"Generated response: {full_response[:100]}...")
            
            # Add AI message to session (same as Streamlit)
            chat_session.messages.append(ai_message)
            chat_session.updated = datetime.now(timezone.utc)
            
            # Save the updated session with messages (same as Streamlit)
            try:
                # Update session in database
                update_session_query = """
                    UPDATE chat_session SET 
                    messages = $messages,
                    updated = time::now()
                    WHERE id = $session_id
                """
                await db.query(update_session_query, {
                "session_id": session_id_str,
                    "messages": chat_session.messages
            })
            
            except Exception as e:
                logger.error(f"Error saving chat session: {str(e)}")
        
            # Broadcast the AI response to all connected clients
            await connection_manager.broadcast(
                session_id=str(chat_session.id),
                message={
                        "id": getattr(ai_message, 'id', f"ai_{uuid.uuid4().hex}"),
                        "role": "assistant",
                        "content": full_response,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            
            # Return the response in the expected format
            return ChatMessageResponse(
                id=getattr(ai_message, 'id', f"ai_{uuid.uuid4().hex}"),
                content=full_response,
                role="assistant",
                timestamp=datetime.now(timezone.utc).isoformat(),
                session_id=str(chat_session.id),
                notebook_id=notebook_id,
                metadata={}
                )
        else:
            logger.warning("No new messages returned from chat graph")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No response generated from AI"
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
        
        return ChatMessageResponse(
            id=error_id,
            content=f"I'm sorry, I encountered an error: {str(e)}",
            role="assistant",
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=str(chat_session.id),
            notebook_id=notebook_id,
            metadata={"error": True}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/events/{session_id}")
async def stream_events(session_id: str):
    """Stream Server-Sent Events for real-time chat updates."""
    async def event_generator():
        # Create a connection queue for this session
        queue = await connection_manager.connect(session_id)
        
        try:
            # Send initial connection message
            yield f"data: {json.dumps({'event': 'connected', 'session_id': session_id})}\n\n"
            
            # Keep connection alive and send messages
            while True:
                try:
                    # Wait for messages with timeout
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(message)}\n\n"
                    
                    # Send heartbeat every 30 seconds
                    await asyncio.sleep(0.1)
                    
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"data: {json.dumps({'event': 'heartbeat', 'timestamp': datetime.now().isoformat()})}\n\n"
                    
                except asyncio.CancelledError:
                    logger.info(f"SSE connection cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Error in SSE stream for session {session_id}: {e}")
            yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"
        finally:
            # Clean up connection
                await connection_manager.disconnect(session_id, queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

@router.get("/context", response_model=Dict[str, Any])
async def get_notebook_context(
    notebook_id: str = Query(..., description="Name or ID of the notebook"),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Get the full context (sources and notes) for a notebook."""
    try:
        context = await build_context_for_notebook(notebook_id, db)
        return context
    except Exception as e:
        logger.error(f"Error getting notebook context: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting notebook context: {str(e)}"
        )

@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    notebook_id: str = Query(..., description="Name or ID of the notebook"),
    session_id: Optional[str] = Query(None, description="Optional session ID"),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Get chat history for a notebook or specific session."""
    try:
        if session_id:
            # Get specific session
            session_query = "SELECT * FROM chat_session WHERE id = $session_id"
            session_result = await db.query(session_query, {"session_id": session_id})
        
            if not session_result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat session not found"
                )
            
            session_data = dict(session_result[0])
            return ChatHistoryResponse(
                session_id=session_id,
                messages=session_data.get('messages', []),
                notebook_id=notebook_id
            )
        else:
            # Get all sessions for notebook
            sessions_query = """
                SELECT chat_session.* FROM chat_session 
                INNER JOIN refers_to ON chat_session.id = refers_to.in 
                WHERE refers_to.out = $notebook_id
                ORDER BY chat_session.updated DESC
            """
            sessions_result = await db.query(sessions_query, {"notebook_id": notebook_id})
            
            if not sessions_result:
                return ChatHistoryResponse(
                    session_id="",
                    messages=[],
                    notebook_id=notebook_id
                )
            
            # Get the most recent session
            latest_session = dict(sessions_result[0])
            return ChatHistoryResponse(
                session_id=str(latest_session.get('id', '')),
                messages=latest_session.get('messages', []),
                notebook_id=notebook_id
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting chat history: {str(e)}"
        )

@router.post("/sessions", response_model=ChatSessionResponse)
async def create_chat_session(
    notebook_id: str = Query(..., description="Name or ID of the notebook"),
    session_name: Optional[str] = Query(None, description="Optional session name"),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Create a new chat session for a notebook."""
    try:
        chat_session = get_or_create_chat_session(
            notebook_id=notebook_id,
            session_name=session_name
        )
        
        if not chat_session:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create chat session"
            )
        
        return ChatSessionResponse(
            id=str(chat_session.id),
            title=chat_session.title or "Chat Session",
            created=chat_session.created.isoformat() if chat_session.created else datetime.now(timezone.utc).isoformat(),
            updated=chat_session.updated.isoformat() if chat_session.updated else datetime.now(timezone.utc).isoformat(),
            message_count=len(chat_session.messages) if chat_session.messages else 0,
            notebook_id=notebook_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating chat session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating chat session: {str(e)}"
        )
