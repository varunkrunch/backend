# FastAPI Backend Pydantic Models

from pydantic import BaseModel, Field, ConfigDict, validator
from typing import Optional, List, Dict, Any, Literal, Union
from datetime import datetime

# --- Common Models ---

class StatusResponse(BaseModel):
    status: str
    message: str

class TaskStatus(BaseModel):
    status: str
    message: Optional[str] = None

# --- Notebook Models ---

class NotebookBase(BaseModel):
    name: str = Field(..., example="My Research Project")
    description: Optional[str] = Field(None, example="Notes and sources related to quantum entanglement.")

class NotebookCreate(NotebookBase):
    pass

class NotebookUpdate(BaseModel):
    name: Optional[str] = Field(None, example="Updated Project Name")
    description: Optional[str] = Field(None, example="Updated description with more details.")

# Summary model for lists
class NotebookSummary(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created: datetime
    updated: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)
    archived: bool = False

# Full notebook model with relationships
class Notebook(NotebookSummary):
    sources: List["SourceSummary"] = Field(default_factory=list)  # Related sources
    notes: List["NoteSummary"] = Field(default_factory=list)      # Related notes
    chat_sessions: List["ChatSessionSummary"] = Field(default_factory=list)  # Related chat sessions

# --- Note Models ---

class NoteBase(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    note_type: Optional[Literal["human", "ai"]] = None

class NoteCreate(NoteBase):
    pass

class NoteUpdate(NoteBase):
    pass

class Note(NoteBase):
    id: str
    created: datetime
    updated: datetime
    embedding: Optional[List[float]] = None

class NoteSummary(BaseModel):
    id: str
    title: Optional[str] = None
    note_type: Optional[Literal["human", "ai"]] = None
    created: datetime
    updated: datetime

# Response model for notes
class NoteResponse(BaseModel):
    id: str
    title: str
    content: str
    created: datetime
    updated: datetime
    note_type: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    notebook_id: Optional[str] = None

# --- Source Models ---

class SourceInsightResponse(BaseModel):
    id: str
    title: str
    content: str
    created: datetime
    updated: datetime
    metadata: Dict[str, Any] = {}

class Source(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    id: str
    title: str = ""
    type: str
    status: str = "completed"
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    full_text: str = ""
    notebook_id: Optional[str] = None
    insights: List[Dict[str, Any]] = Field(default_factory=list)
    embedded_chunks: int = 0

class SourceResponse(Source):
    pass

class SourceSummary(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    id: str
    title: str
    type: str
    status: str = "pending"
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    insights: List[Dict[str, Any]] = Field(default_factory=list)

class SourceWithInsightsResponse(BaseModel):
    id: str
    title: str
    insights: List[SourceInsightResponse] = []

class NoteFullResponse(BaseModel):
    id: str
    title: str
    content: str
    created: datetime
    updated: datetime
    note_type: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    notebook_id: Optional[str] = None
    source: Optional[SourceWithInsightsResponse] = None

# --- Chat Session Models ---

class ChatSessionSummary(BaseModel):
    id: str
    title: str
    created: datetime
    updated: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ChatSession(ChatSessionSummary):
    messages: List[Dict[str, Any]] = Field(default_factory=list)

# --- AI Interaction Models ---

class SourceInsight(BaseModel):
    id: str
    title: str
    content: str
    transformation_id: str
    source_id: str
    created: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Citation(BaseModel):
    source_id: str
    text: str  # The cited text snippet
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ChatContext(BaseModel):
    source_ids: Optional[List[str]] = None
    note_ids: Optional[List[str]] = None
    mode: Literal["summary", "full", "auto", "list_of_ids"] = "auto"
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TransformationBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    name: str = Field(..., description="Name of the transformation")
    title: str = Field(..., description="Title that will be shown on cards created by this transformation")
    description: str = Field(..., description="Description of what this transformation does")
    prompt: str = Field(..., description="The prompt template for this transformation")
    apply_default: bool = Field(False, description="Whether to apply this transformation by default on new sources")

class TransformationCreate(TransformationBase):
    pass

class TransformationUpdate(TransformationBase):
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    apply_default: Optional[bool] = None

class TransformationResponse(TransformationBase):
    id: str
    created: datetime
    updated: datetime

class TransformationRunRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    input_text: str = Field(..., description="Text to transform")
    llm_id: Optional[str] = Field(None, description="ID of the language model to use. If not provided, uses default transformation model.")
    transformation_id: str = Field(..., description="ID of the transformation to apply")
    source_id: Optional[str] = Field(None, description="Optional source ID to add the transformation result as an insight")

class TransformationRunResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    output: str = Field(..., description="The transformed text output")
    llm_used: str = Field(..., description="ID of the language model used")
    transformation_name: str = Field(..., description="Name of the transformation that was applied")

class ApplyTransformationRequest(BaseModel):
    transformation_id: str
    model_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(protected_namespaces=())

class DefaultPrompts(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    transformation_instructions: Optional[str] = Field(
        None, description="Instructions for executing a transformation"
    )

class ChatRequest(BaseModel):
    query: str
    context: Optional[ChatContext] = None
    model_provider: Optional[str] = Field(None, description="The provider of the language model (e.g., 'openai', 'anthropic', 'groq')")
    model_name: Optional[str] = Field(None, description="The name of the language model to use (e.g., 'gpt-3.5-turbo', 'claude-3-opus')")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(protected_namespaces=())

class AskRequest(BaseModel):
    question: str
    model_provider: Optional[str] = Field(None, description="The provider of the language model (e.g., 'openai', 'anthropic', 'groq')")
    model_name: Optional[str] = Field(None, description="The name of the language model to use (e.g., 'gpt-3.5-turbo', 'claude-3-opus')")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(protected_namespaces=())

class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AskResponse(BaseModel):
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

# --- Model Models (Matching Domain Model Exactly) ---

class ModelBase(BaseModel):
    """Base model matching the domain Model class structure exactly"""
    name: str = Field(..., description="Model name (e.g., gpt-4o-mini, claude-3-sonnet)")
    provider: str = Field(..., description="Provider name (e.g., openai, anthropic, groq)")
    type: Literal["language", "embedding", "text_to_speech", "speech_to_text"] = Field(..., description="Model type")
    
    @validator('provider')
    def validate_provider(cls, v):
        """Validate that the provider is supported"""
        supported_providers = [
            "openai", "anthropic", "groq", "xai", "vertexai", "vertexai-anthropic",
            "gemini", "openrouter", "elevenlabs", "ollama", "azure", "mistral",
            "voyage", "deepseek", "litellm"
        ]
        if v not in supported_providers:
            raise ValueError(f"Unsupported provider: {v}. Supported providers: {supported_providers}")
        return v
    
    @validator('name')
    def validate_model_name(cls, v, values):
        """Validate model name based on provider"""
        provider = values.get('provider')
        if not provider:
            return v
            
        # Basic validation
        if not v or len(v.strip()) == 0:
            raise ValueError("Model name cannot be empty")
        
        # Provider-specific validations
        if provider == "openai" and not any(prefix in v.lower() for prefix in ["gpt", "text-embedding", "tts", "whisper"]):
            print(f"Warning: Model name '{v}' may not be a valid OpenAI model")
        elif provider == "anthropic" and not any(prefix in v.lower() for prefix in ["claude"]):
            print(f"Warning: Model name '{v}' may not be a valid Anthropic model")
        elif provider == "groq" and not any(prefix in v.lower() for prefix in ["llama", "mixtral", "gemma"]):
            print(f"Warning: Model name '{v}' may not be a valid Groq model")
            
        return v.strip()
    
    model_config = ConfigDict(from_attributes=True)

class ModelCreate(ModelBase):
    pass

class ModelUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    type: Optional[Literal["language", "embedding", "text_to_speech", "speech_to_text"]] = None
    
    @validator('provider')
    def validate_provider(cls, v):
        if v is None:
            return v
        supported_providers = [
            "openai", "anthropic", "groq", "xai", "vertexai", "vertexai-anthropic",
            "gemini", "openrouter", "elevenlabs", "ollama", "azure", "mistral",
            "voyage", "deepseek", "litellm"
        ]
        if v not in supported_providers:
            raise ValueError(f"Unsupported provider: {v}. Supported providers: {supported_providers}")
        return v
    
    model_config = ConfigDict(from_attributes=True)

class Model(ModelBase):
    id: str
    created: datetime
    updated: datetime
    model_config = ConfigDict(from_attributes=True)

class DefaultModels(BaseModel):
    """API model for default model configurations.
    This matches the domain model structure exactly.
    """
    # Model configuration fields (matching domain model exactly)
    default_chat_model: Optional[str] = None
    default_transformation_model: Optional[str] = None
    large_context_model: Optional[str] = None
    default_text_to_speech_model: Optional[str] = None
    default_speech_to_text_model: Optional[str] = None
    default_embedding_model: Optional[str] = None
    default_tools_model: Optional[str] = None
    
    # Database metadata fields
    id: Optional[str] = None
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra='ignore',
        str_strip_whitespace=True,
        validate_assignment=True
    )

class NotesWithLogsResponse(BaseModel):
    notes: List[NoteSummary]
    logs: List[str]

class NotebookResponse(NotebookSummary):
    pass

class NotebookWithNotesResponse(NotebookSummary):
    notes: List[NoteResponse] = Field(default_factory=list)
    sources: List[SourceSummary] = Field(default_factory=list)
    chat_sessions: List[ChatSessionSummary] = Field(default_factory=list)

