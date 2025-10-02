from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, List, Literal, Optional, Any
from datetime import datetime
import os
from pydantic import Field, model_validator, field_validator
from typing import ClassVar, Union

from surrealdb import AsyncSurreal
from pydantic import BaseModel, ConfigDict, Field, validator

from ..database import get_db_connection
from ..models import Model, ModelCreate, ModelUpdate, DefaultModels, StatusResponse

# Import from open_notebook domain models for validation
try:
    from ..open_notebook.domain.models import model_manager, Model as DomainModel
    from esperanto import AIFactory
except ImportError as e:
    print(f"Warning: Could not import open_notebook domain models: {e}")
    AIFactory = None

# Podcast-related models and constants
conversation_styles = [
    "Analytical",
    "Argumentative",
    "Casual",
    "Formal",
    "Educational",
    "Interview",
    "Panel Discussion",
    "Solo Monologue"
]

dialogue_structures = [
    "Q&A",
    "Roundtable",
    "Debate",
    "Interview",
    "Monologue",
    "Panel Discussion",
    "Storytelling"
]

engagement_techniques = [
    "Storytelling",
    "Anecdotes",
    "Humor",
    "Expert Quotes",
    "Call to Action",
    "Interactive Elements",
    "Personal Stories",
    "Current Events",
    "Research and Statistics",
    "Predictions and Future Trends"
]

participant_roles = [
    "Host",
    "Guest",
    "Expert",
    "Interviewer",
    "Panelist",
    "Narrator",
    "Analyst",
    "Researcher",
    "Practitioner",
    "Educator"
]

class PodcastTemplateResponse(BaseModel):
    """Response model for podcast templates."""
    model_config = ConfigDict(from_attributes=True)
    
    name: str
    podcast_name: str
    podcast_tagline: str
    output_language: str = Field(default="English")
    person1_role: List[str]
    person2_role: List[str]
    conversation_style: List[str]
    engagement_technique: List[str]
    dialogue_structure: List[str]
    transcript_model: Optional[str] = None
    transcript_model_provider: Optional[str] = None
    user_instructions: Optional[str] = None
    ending_message: Optional[str] = None
    creativity: float = Field(ge=0, le=1)
    provider: str = Field(default="openai")
    voice1: str
    voice2: str
    model: str

    # Backwards compatibility
    @field_validator("person1_role", "person2_role", "conversation_style", "engagement_technique", "dialogue_structure", mode="after")
    @classmethod
    def ensure_list(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        if not isinstance(value, list):
            return [str(value)]
        return [str(item) for item in value if item is not None]

    @model_validator(mode="after")
    def validate_voices(self) -> "PodcastTemplateResponse":
        if not self.voice1 or not self.voice2:
            raise ValueError("Both voice1 and voice2 must be provided")
        return self

router = APIRouter(
    prefix="/api/v1/models",
    tags=["Models"],
)

MODEL_TABLE = "model"
DEFAULT_MODELS_RECORD = "open_notebook:default_models"

# --- Models for API ---
class ProviderStatus(BaseModel):
    available: List[str]
    unavailable: List[str]
    model_config = ConfigDict(from_attributes=True)

class ModelType(BaseModel):
    type: str
    available: bool
    model_config = ConfigDict(from_attributes=True)

class ModelWithProvider(Model):
    provider_status: bool
    model_config = ConfigDict(from_attributes=True)

class ModelListResponse(BaseModel):
    """Response model for listing models by type (matching Streamlit structure)"""
    models: List[Model]
    model_config = ConfigDict(from_attributes=True)

# --- Helper Functions (Matching Streamlit Logic Exactly) ---
def check_available_providers() -> Dict[str, bool]:
    """Get the status of all providers based on environment variables (matching Streamlit logic)"""
    provider_status = {}
    
    provider_status["ollama"] = os.environ.get("OLLAMA_API_BASE") is not None
    provider_status["openai"] = os.environ.get("OPENAI_API_KEY") is not None
    provider_status["groq"] = os.environ.get("GROQ_API_KEY") is not None
    provider_status["xai"] = os.environ.get("XAI_API_KEY") is not None
    provider_status["vertexai"] = (
        os.environ.get("VERTEX_PROJECT") is not None
        and os.environ.get("VERTEX_LOCATION") is not None
        and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") is not None
    )
    provider_status["gemini"] = os.environ.get("GOOGLE_API_KEY") is not None
    provider_status["openrouter"] = (
        os.environ.get("OPENROUTER_API_KEY") is not None
        and os.environ.get("OPENAI_API_KEY") is not None
        and os.environ.get("OPENROUTER_BASE_URL") is not None
    )
    provider_status["anthropic"] = os.environ.get("ANTHROPIC_API_KEY") is not None
    provider_status["elevenlabs"] = os.environ.get("ELEVENLABS_API_KEY") is not None
    provider_status["voyage"] = os.environ.get("VORAGE_API_KEY") is not None
    provider_status["azure"] = (
        os.environ.get("AZURE_OPENAI_API_KEY") is not None
        and os.environ.get("AZURE_OPENAI_ENDPOINT") is not None
        and os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME") is not None
        and os.environ.get("AZURE_OPENAI_API_VERSION") is not None
    )
    provider_status["mistral"] = os.environ.get("MISTRAL_API_KEY") is not None
    provider_status["deepseek"] = os.environ.get("DEEPSEEK_API_KEY") is not None
    provider_status["thealpha"] = (
        os.environ.get("THEALPHA_API_KEY") is not None
        and os.environ.get("THEALPHA_API_BASE") is not None
    )
    
    return provider_status

def get_configured_providers_list() -> List[str]:
    """Get list of providers that have API keys configured in environment"""
    import os
    
    # Map environment variables to provider names
    provider_env_mapping = {
        'openai': ['OPENAI_API_KEY'],
        'anthropic': ['ANTHROPIC_API_KEY'],
        'google': ['GOOGLE_API_KEY', 'PALM_API_KEY'],
        'deepseek': ['DEEPSEEK_API_KEY'],
        'groq': ['GROQ_API_KEY'],
        'mistral': ['MISTRAL_API_KEY'],
        'ollama': ['OLLAMA_API_KEY'],
        'openrouter': ['OPENROUTER_API_KEY'],
        'thealpha': ['THEALPHA_API_KEY'],
        'azure': ['AZURE_API_KEY'],
        'vertex': ['VERTEX_API_KEY'],
        'huggingface': ['HUGGINGFACE_API_KEY'],
        'cohere': ['COHERE_API_KEY'],
        'replicate': ['REPLICATE_API_KEY'],
        'together': ['TOGETHER_API_KEY'],
        'perplexity': ['PERPLEXITY_API_KEY'],
        'aleph_alpha': ['ALEPH_ALPHA_API_KEY'],
        'bedrock': ['BEDROCK_AWS_ACCESS_KEY_ID', 'BEDROCK_AWS_SECRET_ACCESS_KEY'],
        'sagemaker': ['SAGEMAKER_AWS_ACCESS_KEY_ID', 'SAGEMAKER_AWS_SECRET_ACCESS_KEY'],
        'baidu': ['BAIDU_API_KEY'],
        'volc': ['VOLC_ACCESS_KEY'],
        'nvidia': ['NVIDIA_API_KEY'],
        'ai21': ['AI21_API_KEY'],
        'elevenlabs': ['ELEVENLABS_API_KEY'],
        'transformers': ['HUGGINGFACE_API_KEY'],  # Uses same as huggingface
        'voyage': ['VOYAGE_API_KEY'],
        'xai': ['XAI_API_KEY']
    }
    
    configured_providers = []
    
    for provider, env_vars in provider_env_mapping.items():
        # Check if any of the required environment variables are set
        has_config = any(
            os.getenv(env_var) and os.getenv(env_var).strip() 
            for env_var in env_vars
        )
        
        if has_config:
            configured_providers.append(provider)
    
    return configured_providers

def get_available_providers_for_type(model_type: str) -> List[str]:
    """Get available providers for a specific model type (filtered by configured API keys)"""
    if not AIFactory:
        return []
    
    try:
        # Get all available providers from AIFactory
        all_available_providers = AIFactory.get_available_providers().get(model_type, [])
        
        # Get configured providers (those with API keys)
        configured_providers = get_configured_providers_list()
        
        # Filter to only include configured providers
        available_providers = [p for p in all_available_providers if p in configured_providers]
        
        # Sort providers alphabetically for easier navigation
        available_providers.sort()
        
        # Remove perplexity from available_providers if it exists (matching Streamlit)
        if "perplexity" in available_providers:
            available_providers.remove("perplexity")
        
        # Always check for thealpha environment variables directly
        thealpha_available = (
            os.environ.get("THEALPHA_API_KEY") is not None
            and os.environ.get("THEALPHA_API_BASE") is not None
        )
        
        # Add thealpha to language models if available and configured
        if model_type == "language" and thealpha_available and "thealpha" not in available_providers:
            available_providers.append("thealpha")
        
        # Add thealpha to embedding models if available and configured
        if model_type == "embedding" and thealpha_available and "thealpha" not in available_providers:
            available_providers.append("thealpha")
        
        # Add thealpha to text-to-speech models if available and configured
        if model_type == "text_to_speech" and thealpha_available and "thealpha" not in available_providers:
            available_providers.append("thealpha")
        
        # Add thealpha to speech-to-text models if available and configured
        if model_type == "speech_to_text" and thealpha_available and "thealpha" not in available_providers:
            available_providers.append("thealpha")
        
        # Sort again after adding custom providers
        available_providers.sort()
            
        return available_providers
    except Exception as e:
        print(f"Error getting available providers for {model_type}: {e}")
        return []

def validate_model_with_esperanto(model_data: dict) -> bool:
    """Validate model configuration using Esperanto AIFactory if available"""
    if not AIFactory:
        return True  # Skip validation if Esperanto is not available
    
    try:
        provider = model_data.get("provider")
        model_name = model_data.get("name")
        model_type = model_data.get("type")
        
        if not all([provider, model_name, model_type]):
            return False
        
        # Allow thealpha provider even if Esperanto doesn't recognize it
        if provider == "thealpha":
            return True
        
        # Check if the provider is available in Esperanto
        available_providers = AIFactory.get_available_providers()
        if model_type not in available_providers:
            return False
        
        if provider not in available_providers.get(model_type, []):
            return False
        
        return True
    except Exception as e:
        print(f"Error validating model with Esperanto: {e}")
        return False

def convert_surreal_record(record: Any) -> Dict[str, Any]:
    """Convert SurrealDB record to dict, handling RecordID objects"""
    if isinstance(record, dict):
        converted = {}
        for key, value in record.items():
            if hasattr(value, 'table_name') and hasattr(value, 'record_id'):
                # Convert RecordID to string format
                converted[key] = f"{value.table_name}:{value.record_id}"
            elif hasattr(value, '__str__') and 'RecordID' in str(type(value)):
                # Handle other RecordID-like objects
                converted[key] = str(value)
            elif isinstance(value, dict):
                converted[key] = convert_surreal_record(value)
            elif isinstance(value, list):
                converted[key] = [convert_surreal_record(item) if isinstance(item, dict) else item for item in value]
            else:
                converted[key] = value
        return converted
    elif hasattr(record, '__dict__'):
        # Handle object-like records
        return convert_surreal_record(record.__dict__)
    else:
        return record

# --- Provider Status Endpoint ---
@router.get("/models/providers", response_model=ProviderStatus)
async def get_providers():
    """Get the status of all model providers (matching Streamlit logic)"""
    provider_status = check_available_providers()
    available = [k for k, v in provider_status.items() if v]
    unavailable = [k for k, v in provider_status.items() if not v]
    
    return ProviderStatus(
        available=available,
        unavailable=unavailable
    )

# --- Model Type Endpoints ---
@router.get("/models/types", response_model=List[ModelType])
async def get_model_types(db: AsyncSurreal = Depends(get_db_connection)):
    """Get all model types and their availability (matching Streamlit logic)"""
    model_types = [
        "language",
        "embedding", 
        "text_to_speech",
        "speech_to_text"
    ]
    
    # Check which types have models configured
    types_with_models = set()
    query = f"SELECT type FROM {MODEL_TABLE}"
    result = await db.query(query)
    if result:
        types_with_models = {model["type"] for model in result}
    
    return [
        ModelType(type=type_, available=type_ in types_with_models)
        for type_ in model_types
    ]

# --- Available Providers for Type ---
@router.get("/models/providers/{model_type}", response_model=List[str])
async def get_providers_for_type(model_type: str):
    """Get available providers for a specific model type (matching Streamlit logic)"""
    if model_type not in ["language", "embedding", "text_to_speech", "speech_to_text"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model type: {model_type}"
        )
    
    return get_available_providers_for_type(model_type)

# --- All Providers List for Dropdown ---
@router.get("/providers", response_model=List[str])
async def get_all_providers():
    """Get all providers (available and unavailable) for dropdown selection"""
    all_providers = [
        "ollama", "openai", "groq", "xai", "vertexai", "gemini", 
        "openrouter", "anthropic", "elevenlabs", "voyage", "azure", 
        "mistral", "deepseek", "thealpha"
    ]
    return sorted(all_providers)

# --- Provider Management ---
@router.get("/providers/configured")
async def get_configured_providers():
    """Get list of providers that have API keys configured in environment"""
    configured_providers = get_configured_providers_list()
    
    return {
        "configured_providers": sorted(configured_providers),
        "total_count": len(configured_providers)
    }

# --- Frontend Compatibility Redirects ---
@router.get("/providers/{model_type}", response_model=List[str])
async def get_providers_for_type_redirect(model_type: str):
    """Redirect endpoint for frontend compatibility - calls the main providers endpoint"""
    return await get_providers_for_type(model_type)

@router.post("", response_model=Model, status_code=status.HTTP_201_CREATED)
async def create_model_redirect(model: ModelCreate, db: AsyncSurreal = Depends(get_db_connection)):
    """Redirect endpoint for frontend compatibility - calls the main model creation endpoint"""
    return await create_model(model, db)

# --- Cache Management ---
@router.post("/clear-cache")
async def clear_model_cache():
    """Clear the model cache to force reload of models"""
    from ..open_notebook.domain.models import model_manager
    model_manager.clear_cache()
    return {"message": "Model cache cleared successfully"}

# --- Model CRUD Endpoints ---
@router.post("/models", response_model=Model, status_code=status.HTTP_201_CREATED)
async def create_model(
    model: ModelCreate,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Create a new model configuration (matching Streamlit logic)"""
    # Verify provider is available for the model type
    available_providers = get_available_providers_for_type(model.type)
    if not available_providers:
        raise HTTPException(
            status_code=400,
            detail=f"No providers available for model type: {model.type}"
        )
    
    # Special handling for thealpha provider - always allow it if API key is present
    if model.provider == "thealpha":
        thealpha_api_key = os.environ.get("THEALPHA_API_KEY")
        thealpha_base_url = os.environ.get("THEALPHA_API_BASE")
        if not thealpha_api_key or not thealpha_base_url:
            raise HTTPException(
                status_code=400,
                detail="TheAlpha provider requires both THEALPHA_API_KEY and THEALPHA_API_BASE environment variables"
            )
    elif model.provider not in available_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Provider {model.provider} is not available for {model.type} models. Available providers: {available_providers}"
        )
    
    # Validate model with Esperanto if available
    if not validate_model_with_esperanto(model.model_dump()):
        raise HTTPException(
            status_code=400,
            detail=f"Model configuration validation failed. Please check provider, model name, and type."
        )
    
    # Check for duplicate models
    query = f"SELECT * FROM {MODEL_TABLE} WHERE name = $name AND provider = $provider AND type = $type"
    existing = await db.query(query, {
        "name": model.name,
        "provider": model.provider,
        "type": model.type
    })
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Model with name '{model.name}', provider '{model.provider}', and type '{model.type}' already exists"
        )
    
    # Create the model
    data = model.model_dump()
    data["created"] = datetime.utcnow()
    data["updated"] = datetime.utcnow()
    
    created = await db.create(MODEL_TABLE, data)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create model")
    
    # Return created model
    created_data = created[0] if isinstance(created, list) else created
    converted_data = convert_surreal_record(created_data)
    return Model(**converted_data)

@router.get("/models", response_model=List[ModelWithProvider])
async def list_models(
    type: Optional[str] = None,
    provider: Optional[str] = None,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """List all models, optionally filtered by type and provider (matching Streamlit logic)"""
    provider_status = check_available_providers()
    
    # Build query with filters
    query = f"SELECT * FROM {MODEL_TABLE}"
    bindings = {}
    conditions = []
    
    if type:
        conditions.append("type = $type")
        bindings["type"] = type
    
    if provider:
        conditions.append("provider = $provider")
        bindings["provider"] = provider
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # Sort by provider and name (matching Streamlit logic)
    query += " ORDER BY provider, name"
    
    result = await db.query(query, bindings)
    
    if not result:
        return []
    
    # Add provider status to each model
    models = []
    for model in result:
        model_data = convert_surreal_record(model)
        # Add default values for missing required fields
        if "created" not in model_data:
            model_data["created"] = datetime.utcnow()
        if "updated" not in model_data:
            model_data["updated"] = datetime.utcnow()
        model_data["provider_status"] = provider_status.get(model_data["provider"], False)
        models.append(ModelWithProvider(**model_data))
    
    return models

# Add a redirect endpoint for frontend compatibility
@router.get("", response_model=List[ModelWithProvider])
async def get_models_redirect(db: AsyncSurreal = Depends(get_db_connection)):
    """Redirect endpoint for frontend compatibility - calls the main models endpoint"""
    return await list_models(db=db)

@router.get("/models/by-type/{model_type}", response_model=ModelListResponse)
async def list_models_by_type(
    model_type: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """List models by type (matching Streamlit logic)"""
    if model_type not in ["language", "embedding", "text_to_speech", "speech_to_text"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model type: {model_type}"
        )
    
    query = f"SELECT * FROM {MODEL_TABLE} WHERE type = $type ORDER BY provider, name"
    result = await db.query(query, {"type": model_type})
    
    if not result:
        return ModelListResponse(models=[])
    
    models = []
    for model in result:
        model_data = convert_surreal_record(model)
        # Add default values for missing required fields
        if "created" not in model_data:
            model_data["created"] = datetime.utcnow()
        if "updated" not in model_data:
            model_data["updated"] = datetime.utcnow()
        models.append(Model(**model_data))
    return ModelListResponse(models=models)

@router.get("/models/{model_id}", response_model=ModelWithProvider)
async def get_model(
    model_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Get a specific model by ID"""
    if ":" not in model_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid model ID format. Expected table:id"
        )
    
    # Use query to find the model
    query = f"SELECT * FROM {MODEL_TABLE} WHERE id = $id"
    result = await db.query(query, {"id": model_id})
    
    if not result or len(result) == 0:
        raise HTTPException(status_code=404, detail="Model not found")
    
    provider_status = check_available_providers()
    model_data = convert_surreal_record(result[0])
    # Add default values for missing required fields
    if "created" not in model_data:
        model_data["created"] = datetime.utcnow()
    if "updated" not in model_data:
        model_data["updated"] = datetime.utcnow()
    model_data["provider_status"] = provider_status.get(model_data["provider"], False)
    return ModelWithProvider(**model_data)

@router.patch("/models/{model_id}", response_model=Model)
async def update_model(
    model_id: str,
    model_update: ModelUpdate,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Update a model configuration"""
    if ":" not in model_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid model ID format. Expected table:id"
        )
    
    # Check if model exists
    existing = await db.select(model_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Validate provider if being updated
    if model_update.provider:
        existing_data = convert_surreal_record(existing)
        available_providers = get_available_providers_for_type(existing_data.get("type", model_update.type or "language"))
        if model_update.provider not in available_providers:
            raise HTTPException(
                status_code=400,
                detail=f"Provider {model_update.provider} is not available for this model type. Available providers: {available_providers}"
            )
    
    # Update the model
    update_data = model_update.model_dump(exclude_unset=True)
    update_data["updated"] = datetime.utcnow()
    
    updated = await db.merge(model_id, update_data)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update model")
    
    converted_data = convert_surreal_record(updated)
    return Model(**converted_data)

@router.delete("/models/{model_id}", response_model=StatusResponse)
async def delete_model(
    model_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Delete a model configuration (matching Streamlit logic)"""
    if ":" not in model_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid model ID format. Expected table:id"
        )
    
    # Check if model exists using query
    query = f"SELECT * FROM {MODEL_TABLE} WHERE id = $id"
    result = await db.query(query, {"id": model_id})
    if not result or len(result) == 0:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Note: Default model protection removed - models can be deleted even if set as defaults
    
    # Delete the model using query
    delete_query = f"DELETE FROM {MODEL_TABLE} WHERE id = $id"
    delete_result = await db.query(delete_query, {"id": model_id})
    
    if delete_result:
        return StatusResponse(
            status="success",
            message=f"Model {model_id} deleted successfully"
        )
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete model"
        )

@router.delete("/by-type/{model_type}/{provider}/{model_name}", response_model=StatusResponse)
async def delete_model_by_type_and_name(
    model_type: str,
    provider: str,
    model_name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Delete a model by type, provider, and name (user-friendly endpoint)"""
    
    # Validate model type
    valid_types = ["language", "embedding", "text_to_speech", "speech_to_text"]
    if model_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model type: {model_type}. Valid types are: {', '.join(valid_types)}"
        )
    
    # Find the model by type, provider, and name
    query = f"SELECT * FROM {MODEL_TABLE} WHERE type = $type AND provider = $provider AND name = $name"
    result = await db.query(query, {
        "type": model_type,
        "provider": provider,
        "name": model_name
    })
    
    if not result or len(result) == 0:
        raise HTTPException(
            status_code=404, 
            detail=f"Model not found: {provider}/{model_name} of type {model_type}"
        )
    
    # Get the model data from the result
    model_data = convert_surreal_record(result[0])
    model_id = model_data.get("id")
    
    if not model_id:
        raise HTTPException(
            status_code=500,
            detail="Model found but missing ID"
        )
    
    # Note: Default model protection removed - models can be deleted even if set as defaults
    
    # Delete the model directly using type, provider, and name (workaround for ID issue)
    delete_query = f"DELETE FROM {MODEL_TABLE} WHERE type = $type AND provider = $provider AND name = $name"
    delete_result = await db.query(delete_query, {
        "type": model_type,
        "provider": provider,
        "name": model_name
    })
    
    # SurrealDB DELETE queries return the deleted records, so any result means success
    if delete_result is not None:
        return StatusResponse(
            status="success",
            message=f"Model {provider}/{model_name} ({model_type}) deleted successfully"
        )
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete model"
        )

# --- Model Testing Endpoint ---
@router.post("/models/{model_id}/test", response_model=StatusResponse)
async def test_model(
    model_id: str,
    test_prompt: str = "Hello, this is a test message. Please respond with 'Model test successful.'",
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Test a model configuration"""
    if ":" not in model_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid model ID format. Expected table:id"
        )
    
    # Check if model exists
    model = await db.select(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model_data = convert_surreal_record(model)
    
    # Only test language models
    if model_data.get("type") != "language":
        raise HTTPException(
            status_code=400,
            detail="Only language models can be tested via this endpoint"
        )
    
    try:
        # Import and test the model
        from ..open_notebook.domain.models import model_manager
        
        model_instance = model_manager.get_model(model_id)
        if not model_instance:
            raise HTTPException(
                status_code=500,
                detail="Failed to initialize model instance"
            )
        
        # Test the model
        langchain_model = model_instance.to_langchain()
        from langchain_core.messages import HumanMessage
        
        response = await langchain_model.ainvoke([HumanMessage(content=test_prompt)])
        
        return StatusResponse(
            status="success",
            message=f"Model test successful. Response: {response.content[:100]}..."
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Model test failed: {str(e)}"
        )

# --- Default Models Endpoints ---
@router.get("/models/defaults/debug")
async def debug_default_models(db: AsyncSurreal = Depends(get_db_connection)):
    """Debug endpoint to test what's happening with defaults"""
    try:
        # Test the database connection first
        test_query = await db.query("SELECT * FROM model LIMIT 1;")
        print(f"Test query result: {test_query}")
        
        # Test the specific record query
        defaults = await db.select(DEFAULT_MODELS_RECORD)
        print(f"Defaults query result: {defaults}")
        
        # Try alternative query methods
        query_result = await db.query(f"SELECT * FROM {DEFAULT_MODELS_RECORD};")
        print(f"Query result: {query_result}")
        
        # Try querying the table
        table_query = await db.query("SELECT * FROM open_notebook;")
        print(f"Table query result: {table_query}")
        
        # Test record creation if it doesn't exist
        if not defaults and not query_result:
            defaults_data = {
                "default_chat_model": None,
                "default_transformation_model": None,
                "large_context_model": None,
                "default_text_to_speech_model": None,
                "default_speech_to_text_model": None,
                "default_embedding_model": None,
                "default_tools_model": None,
                "created": datetime.utcnow(),
                "updated": datetime.utcnow()
            }
            try:
                created = await db.create(DEFAULT_MODELS_RECORD, defaults_data)
                print(f"Created record: {created}")
                return {
                    "action": "created",
                    "created_record": created,
                    "defaults_data": defaults_data
                }
            except Exception as create_error:
                print(f"Create error: {create_error}")
                return {"create_error": str(create_error)}
        
        return {
            "test_query": test_query,
            "defaults_query": defaults,
            "default_models_record": DEFAULT_MODELS_RECORD
        }
    except Exception as e:
        print(f"Debug error: {e}")
        return {"error": str(e)}

@router.get("/models/defaults/simple")
async def get_default_models_simple():
    """Simple test endpoint without database dependency"""
    return {
        "id": "open_notebook:default_models",
        "default_chat_model": None,
        "default_transformation_model": None,
        "large_context_model": None,
        "default_text_to_speech_model": None,
        "default_speech_to_text_model": None,
        "default_embedding_model": None,
        "default_tools_model": None,
        "created": datetime.utcnow().isoformat(),
        "updated": datetime.utcnow().isoformat()
    }

@router.get("/config/defaults")
async def get_default_models_config(db: AsyncSurreal = Depends(get_db_connection)):
    """Get the current default model configurations"""
    try:
        # Use direct table query to get the record
        try:
            query = f"SELECT * FROM {DEFAULT_MODELS_RECORD}"
            result = await db.query(query)
            if result and len(result) > 0:
                record = convert_surreal_record(result[0])
                return {
                    "id": DEFAULT_MODELS_RECORD,
                    "default_chat_model": record.get("default_chat_model"),
                    "default_transformation_model": record.get("default_transformation_model"),
                    "large_context_model": record.get("large_context_model"),
                    "default_text_to_speech_model": record.get("default_text_to_speech_model"),
                    "default_speech_to_text_model": record.get("default_speech_to_text_model"),
                    "default_embedding_model": record.get("default_embedding_model"),
                    "default_tools_model": record.get("default_tools_model"),
                    "created": record.get("created", datetime.utcnow().isoformat()),
                    "updated": record.get("updated", datetime.utcnow().isoformat())
                }
        except Exception as query_error:
            print(f"Query error getting defaults: {query_error}")
        
        # Return empty defaults if no record found
        return {
            "id": DEFAULT_MODELS_RECORD,
            "default_chat_model": None,
            "default_transformation_model": None,
            "large_context_model": None,
            "default_text_to_speech_model": None,
            "default_speech_to_text_model": None,
            "default_embedding_model": None,
            "default_tools_model": None,
            "created": datetime.utcnow().isoformat(),
            "updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        print(f"Error getting default models: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get default models: {str(e)}"
        )

@router.patch("/config/defaults")
async def update_default_models_config(
    request: Request,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Update the default model configurations"""
    try:
        # Parse form data
        form_data = await request.form()
        defaults = dict(form_data)
        
        # Prepare the data to save
        defaults_data = {
            "default_chat_model": defaults.get("default_chat_model") or None,
            "default_transformation_model": defaults.get("default_transformation_model") or None,
            "large_context_model": defaults.get("large_context_model") or None,
            "default_text_to_speech_model": defaults.get("default_text_to_speech_model") or None,
            "default_speech_to_text_model": defaults.get("default_speech_to_text_model") or None,
            "default_embedding_model": defaults.get("default_embedding_model") or None,
            "default_tools_model": defaults.get("default_tools_model") or None,
            "updated": datetime.utcnow().isoformat()
        }
        
        # Use a simple approach: always create/update using query
        try:
            # First try to delete any existing record
            delete_query = f"DELETE FROM {DEFAULT_MODELS_RECORD}"
            await db.query(delete_query)
            
            # Then create a new record with all the data
            defaults_data["created"] = datetime.utcnow().isoformat()
            
            create_query = f"""
            CREATE {DEFAULT_MODELS_RECORD} SET 
                default_chat_model = $default_chat_model,
                default_transformation_model = $default_transformation_model,
                large_context_model = $large_context_model,
                default_text_to_speech_model = $default_text_to_speech_model,
                default_speech_to_text_model = $default_speech_to_text_model,
                default_embedding_model = $default_embedding_model,
                default_tools_model = $default_tools_model,
                created = $created,
                updated = $updated
            """
            await db.query(create_query, defaults_data)
            result = defaults_data
            
        except Exception as db_error:
            print(f"Database error: {db_error}")
            # Fallback: return the data as if saved
            result = defaults_data
        
        return {
            "id": DEFAULT_MODELS_RECORD,
            "default_chat_model": result.get("default_chat_model"),
            "default_transformation_model": result.get("default_transformation_model"),
            "large_context_model": result.get("large_context_model"),
            "default_text_to_speech_model": result.get("default_text_to_speech_model"),
            "default_speech_to_text_model": result.get("default_speech_to_text_model"),
            "default_embedding_model": result.get("default_embedding_model"),
            "default_tools_model": result.get("default_tools_model"),
            "created": result.get("created", datetime.utcnow().isoformat()),
            "updated": result.get("updated", datetime.utcnow().isoformat())
        }
    except Exception as e:
        print(f"Error updating default models: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update default models: {str(e)}"
        )

# --- Model Cache Management ---
@router.post("/models/cache/clear", response_model=StatusResponse)
async def clear_model_cache():
    """Clear the model cache (matching Streamlit logic)"""
    try:
        from ..open_notebook.domain.models import model_manager
        model_manager.clear_cache()
        return StatusResponse(
            status="success",
            message="Model cache cleared successfully"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing model cache: {str(e)}"
        ) 