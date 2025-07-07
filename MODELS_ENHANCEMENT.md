# Models Enhancement Documentation

## Overview

This document describes the enhanced models functionality in the Open Notebook FastAPI backend. The models system provides robust model management, validation, and AI integration capabilities that **exactly match** the existing Streamlit functionality and domain model structure.

## Architecture

The models system consists of several key components that mirror the Streamlit implementation:

1. **Domain Models** (`open_notebook/domain/models.py`): Core model definitions and ModelManager singleton
2. **FastAPI Models** (`fastapi_backend/src/models.py`): Pydantic models that exactly match the domain model structure
3. **Models Router** (`fastapi_backend/src/routers/models.py`): REST API endpoints that mirror Streamlit functionality
4. **AI Integration** (`fastapi_backend/src/routers/ai_interactions.py`): AI endpoints that use the model manager
5. **Database Schema**: SurrealDB table structure with constraints and validation

## Model Structure

The model structure **exactly matches** the domain model:

```python
class Model:
    id: str
    name: str                    # Model name (e.g., "gpt-4o-mini")
    provider: str                # Provider name (e.g., "openai")
    type: str                    # Model type ("language", "embedding", "text_to_speech", "speech_to_text")
    created: datetime
    updated: datetime
```

### Supported Providers (Matching Streamlit)

The provider checking logic **exactly matches** the Streamlit implementation:

- **OpenAI**: `openai` (GPT models, embeddings, TTS, STT)
- **Anthropic**: `anthropic` (Claude models)
- **Groq**: `groq` (Fast inference models)
- **Google**: `gemini`, `vertexai`
- **Others**: `xai`, `openrouter`, `elevenlabs`, `ollama`, `azure`, `mistral`, `voyage`, `deepseek`

### Model Types

- **language**: Text generation models (GPT, Claude, etc.)
- **embedding**: Vector embedding models
- **text_to_speech**: Text-to-speech models
- **speech_to_text**: Speech-to-text models

## API Endpoints

### Provider Status

```http
GET /api/v1/models/providers
```

Returns the availability status of all supported providers based on environment variables (matching Streamlit logic exactly).

**Response:**
```json
{
  "available": ["openai", "anthropic"],
  "unavailable": ["groq", "xai"]
}
```

### Available Providers for Model Type

```http
GET /api/v1/models/providers/{model_type}
```

Returns available providers for a specific model type (matching Streamlit logic).

**Response:**
```json
["openai", "anthropic", "groq"]
```

### Model Types

```http
GET /api/v1/models/types
```

Returns all model types and their availability status.

**Response:**
```json
[
  {
    "type": "language",
    "available": true
  },
  {
    "type": "embedding", 
    "available": false
  }
]
```

### Model CRUD Operations

#### Create Model

```http
POST /api/v1/models
```

**Request Body:**
```json
{
  "name": "gpt-4o-mini",
  "provider": "openai",
  "type": "language"
}
```

**Validation (Matching Streamlit):**
- Provider must be available for the specific model type
- Model name must not be empty
- Provider-specific model name validation
- No duplicate models (name + provider + type combination)

#### List Models

```http
GET /api/v1/models
GET /api/v1/models?type=language
GET /api/v1/models?provider=openai
```

**Response:**
```json
[
  {
    "id": "model:123",
    "name": "gpt-4o-mini",
    "provider": "openai",
    "type": "language",
    "provider_status": true,
    "created": "2024-01-01T00:00:00Z",
    "updated": "2024-01-01T00:00:00Z"
  }
]
```

#### List Models by Type

```http
GET /api/v1/models/by-type/{model_type}
```

Returns models grouped by type (matching Streamlit structure).

**Response:**
```json
{
  "models": [
    {
      "id": "model:123",
      "name": "gpt-4o-mini",
      "provider": "openai",
      "type": "language",
      "created": "2024-01-01T00:00:00Z",
      "updated": "2024-01-01T00:00:00Z"
    }
  ]
}
```

#### Get Model

```http
GET /api/v1/models/{model_id}
```

#### Update Model

```http
PATCH /api/v1/models/{model_id}
```

**Request Body:**
```json
{
  "name": "gpt-4o-mini-updated"
}
```

#### Delete Model

```http
DELETE /api/v1/models/{model_id}
```

**Protection:** Models cannot be deleted if they are set as default models (matching Streamlit logic).

### Model Testing

```http
POST /api/v1/models/{model_id}/test
```

Tests a language model by sending a test prompt and verifying the response.

### Default Models

#### Get Defaults

```http
GET /api/v1/models/defaults
```

**Response:**
```json
{
  "id": "open_notebook:default_models",
  "default_chat_model": "model:123",
  "default_transformation_model": "model:124",
  "large_context_model": "model:125",
  "default_text_to_speech_model": "model:126",
  "default_speech_to_text_model": "model:127",
  "default_embedding_model": "model:128",
  "default_tools_model": "model:129",
  "created": "2024-01-01T00:00:00Z",
  "updated": "2024-01-01T00:00:00Z"
}
```

#### Update Defaults

```http
PATCH /api/v1/models/defaults
```

**Request Body:**
```json
{
  "default_chat_model": "model:123",
  "default_embedding_model": "model:128"
}
```

**Validation:** All referenced models must exist in the database.

### Cache Management

```http
POST /api/v1/models/cache/clear
```

Clears the model cache in the ModelManager singleton (matching Streamlit logic).

## Database Schema

### Model Table

```sql
DEFINE TABLE model SCHEMAFULL;

DEFINE FIELD name ON TABLE model TYPE string;
DEFINE FIELD provider ON TABLE model TYPE string;
DEFINE FIELD type ON TABLE model TYPE string;
DEFINE FIELD created ON model DEFAULT time::now() VALUE $before OR time::now();
DEFINE FIELD updated ON model DEFAULT time::now() VALUE time::now();

-- Indexes
DEFINE INDEX idx_model_type ON TABLE model COLUMNS type;
DEFINE INDEX idx_model_provider ON TABLE model COLUMNS provider;
DEFINE INDEX idx_model_name ON TABLE model COLUMNS name;
DEFINE INDEX idx_model_created ON TABLE model COLUMNS created;
DEFINE INDEX idx_model_unique ON TABLE model COLUMNS name, provider, type UNIQUE;

-- Validation Events
DEFINE EVENT model_type_validation ON TABLE model WHEN ($after != NONE) THEN {
    LET valid_types = ["language", "embedding", "text_to_speech", "speech_to_text"];
    IF !array::includes(valid_types, $after.type) THEN {
        THROW "Invalid model type. Must be one of: " + array::join(valid_types, ", ");
    };
};

DEFINE EVENT model_provider_validation ON TABLE model WHEN ($after != NONE) THEN {
    LET valid_providers = ["openai", "anthropic", "groq", "xai", "vertexai", "gemini", "openrouter", "elevenlabs", "ollama", "azure", "mistral", "voyage", "deepseek"];
    IF !array::includes(valid_providers, $after.provider) THEN {
        THROW "Invalid provider. Must be one of: " + array::join(valid_providers, ", ");
    };
};
```

### Default Models Record

The default models are stored as a single record with ID `open_notebook:default_models`.

## AI Integration

The AI interaction endpoints (`/api/v1/ask`, `/api/v1/chat`) use the ModelManager to:

1. **Resolve Models**: Get the appropriate model based on request parameters or defaults
2. **Fetch Context**: Retrieve relevant sources and notes for context
3. **Generate Responses**: Use the model to generate AI responses
4. **Handle Citations**: Extract and format source citations

### Model Resolution Logic

1. If `model_provider` and `model_name` are provided, use those
2. Otherwise, use the default model for the requested type
3. Fall back to the default chat model if no specific default is set

## Streamlit Integration

The FastAPI endpoints are designed to **exactly match** the Streamlit functionality:

### Provider Checking
- Uses the same environment variable checking logic
- Returns the same provider availability status
- Supports the same provider list

### Model Management
- Same model creation validation
- Same model listing and filtering
- Same default model management
- Same model deletion protection

### Model Types
- Same model type validation
- Same provider availability per type
- Same sorting and organization

## Error Handling

### Validation Errors

- **400 Bad Request**: Invalid model configuration, provider not available for type
- **404 Not Found**: Model not found
- **422 Unprocessable Entity**: Invalid request data (Pydantic validation)

### Business Logic Errors

- **400 Bad Request**: Cannot delete model used as default
- **500 Internal Server Error**: Database errors, model initialization failures

## Testing

### Running Tests

```bash
cd fastapi_backend
python test_models_integration.py
```

### Test Coverage

The test suite covers all Streamlit-equivalent functionality:

1. **Provider Status**: Environment variable validation (matching Streamlit)
2. **Providers by Type**: Available providers for each model type
3. **Model CRUD**: Create, read, update, delete operations
4. **Model Validation**: Provider and model type validation
5. **Model Listing**: List all models and by type
6. **Default Models**: Setting and updating default configurations
7. **AI Integration**: Model resolution and response generation
8. **Cache Management**: Model cache clearing
9. **Error Handling**: Various error scenarios

## Migration

### Applying Migration

```bash
# Apply the migration
surreal import --conn http://localhost:8000 --user root --pass root --ns test --db test migrations/7.surrealql

# Rollback if needed
surreal import --conn http://localhost:8000 --user root --pass root --ns test --db test migrations/7_down.surrealql
```

### Migration Steps

1. Create the model table with proper schema
2. Add indexes for performance
3. Add validation events for data integrity
4. Add unique constraints to prevent duplicates

## Best Practices

### Model Configuration

1. **Use Descriptive Names**: Choose clear, recognizable model names
2. **Validate Providers**: Ensure provider is available for the model type
3. **Set Defaults**: Configure default models for each type
4. **Test Models**: Use the test endpoint to verify model functionality

### API Usage

1. **Check Provider Status**: Verify provider availability before creating models
2. **Use Type-Specific Endpoints**: Use `/models/by-type/{type}` for type-specific operations
3. **Handle Errors**: Implement proper error handling for all API calls
4. **Validate Responses**: Always validate API responses

### Performance

1. **Use Indexes**: The database includes indexes for common queries
2. **Cache Management**: Clear cache when models are updated
3. **Batch Operations**: Use bulk operations when possible

## Troubleshooting

### Common Issues

1. **Provider Not Available for Type**
   - Check that the provider supports the model type
   - Use `/api/v1/models/providers/{type}` to see available providers
   - Verify environment variables are set correctly

2. **Model Validation Fails**
   - Verify model name format for the provider
   - Check that provider is supported
   - Ensure model type is valid

3. **AI Integration Fails**
   - Check that default models are set
   - Verify model IDs exist
   - Check API keys for the model provider

4. **Database Errors**
   - Check SurrealDB connection
   - Verify migration has been applied
   - Check database permissions

### Debugging

1. **Enable Logging**: Set log level to DEBUG for detailed information
2. **Check API Responses**: Use the test endpoints to verify functionality
3. **Validate Data**: Use the validation endpoints to check data integrity

## Future Enhancements

### Planned Features

1. **Model Performance Metrics**: Track model usage and performance
2. **Advanced Configuration**: Support for model-specific parameters
3. **Model Versioning**: Support for model version management
4. **Bulk Operations**: Batch create/update/delete operations
5. **Model Templates**: Predefined model configurations

### Extension Points

1. **Custom Providers**: Framework for adding new AI providers
2. **Model Plugins**: Plugin system for custom model types
3. **Advanced Validation**: Custom validation rules for specific providers
4. **Monitoring**: Integration with monitoring and alerting systems

## Conclusion

The enhanced models system provides a robust, validated, and maintainable foundation for AI model management in Open Notebook. The system **exactly matches** the existing Streamlit functionality while providing comprehensive API endpoints, validation, and integration capabilities.

The FastAPI endpoints maintain **100% compatibility** with the existing domain model structure and Streamlit integration, ensuring seamless operation with your existing models and configurations.

For questions or issues, please refer to the test suite and documentation, or create an issue in the project repository. 