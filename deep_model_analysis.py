import sys
import os
from dotenv import load_dotenv

sys.path.append('src')

from open_notebook.domain.models import model_manager, Model, DefaultModels
from open_notebook.database.repository import repo_query

def deep_model_analysis():
    load_dotenv()
    print('=' * 80)
    print('DEEP MODEL ANALYSIS - CROSS-CHECKING ENTIRE CODEBASE')
    print('=' * 80)
    
    # 1. Check all models in database
    print('\n1. ALL MODELS IN DATABASE:')
    print('-' * 40)
    try:
        all_models = Model.get_all_models()
        if all_models:
            for model in all_models:
                print(f"  ID: {model.id}")
                print(f"  Name: {model.name}")
                print(f"  Provider: {model.provider}")
                print(f"  Type: {model.type}")
                print(f"  Created: {getattr(model, 'created', 'N/A')}")
                print(f"  Updated: {getattr(model, 'updated', 'N/A')}")
                print()
        else:
            print("  No models found in the database.")
    except Exception as e:
        print(f"  Error fetching all models: {e}")
    
    # 2. Check models by type
    print('\n2. MODELS BY TYPE:')
    print('-' * 40)
    model_types = ["language", "embedding", "text_to_speech", "speech_to_text"]
    for model_type in model_types:
        print(f"\n{model_type.upper()} MODELS:")
        try:
            models = Model.get_models_by_type(model_type)
            if models:
                for model in models:
                    print(f"  - {model.name} ({model.provider}) - ID: {model.id}")
            else:
                print(f"  No {model_type} models found.")
        except Exception as e:
            print(f"  Error fetching {model_type} models: {e}")
    
    # 3. Check default models configuration
    print('\n3. DEFAULT MODELS CONFIGURATION:')
    print('-' * 40)
    try:
        defaults = model_manager.defaults
        print(f"  default_chat_model: {defaults.default_chat_model}")
        print(f"  default_transformation_model: {defaults.default_transformation_model}")
        print(f"  large_context_model: {defaults.large_context_model}")
        print(f"  default_text_to_speech_model: {defaults.default_text_to_speech_model}")
        print(f"  default_speech_to_text_model: {defaults.default_speech_to_text_model}")
        print(f"  default_embedding_model: {defaults.default_embedding_model}")
        print(f"  default_tools_model: {defaults.default_tools_model}")
    except Exception as e:
        print(f"  Error getting default models: {e}")
    
    # 4. Check default models from database directly
    print('\n4. DEFAULT MODELS FROM DATABASE (DIRECT QUERY):')
    print('-' * 40)
    try:
        result = repo_query("SELECT * FROM open_notebook:default_models;")
        if result and len(result) > 0:
            defaults_data = result[0]
            print(f"  Database record: {defaults_data}")
        else:
            print("  No default models record found in database.")
    except Exception as e:
        print(f"  Error querying default models from database: {e}")
    
    # 5. Test model manager methods
    print('\n5. MODEL MANAGER METHODS:')
    print('-' * 40)
    
    # Test get_default_model for each type
    model_types_to_test = ["chat", "transformation", "tools", "embedding", "text_to_speech", "speech_to_text", "large_context"]
    for model_type in model_types_to_test:
        try:
            model = model_manager.get_default_model(model_type)
            if model:
                print(f"  {model_type}: {model.provider} - {model.models[0] if hasattr(model, 'models') else 'N/A'}")
            else:
                print(f"  {model_type}: None")
        except Exception as e:
            print(f"  {model_type}: Error - {e}")
    
    # 6. Test specific model properties
    print('\n6. MODEL MANAGER PROPERTIES:')
    print('-' * 40)
    
    try:
        embedding_model = model_manager.embedding_model
        if embedding_model:
            print(f"  embedding_model: {embedding_model.provider} - {embedding_model.models[0] if hasattr(embedding_model, 'models') else 'N/A'}")
        else:
            print(f"  embedding_model: None")
    except Exception as e:
        print(f"  embedding_model: Error - {e}")
    
    try:
        tts_model = model_manager.text_to_speech
        if tts_model:
            print(f"  text_to_speech: {tts_model.provider} - {tts_model.models[0] if hasattr(tts_model, 'models') else 'N/A'}")
        else:
            print(f"  text_to_speech: None")
    except Exception as e:
        print(f"  text_to_speech: Error - {e}")
    
    try:
        stt_model = model_manager.speech_to_text
        if stt_model:
            print(f"  speech_to_text: {stt_model.provider} - {stt_model.models[0] if hasattr(stt_model, 'models') else 'N/A'}")
        else:
            print(f"  speech_to_text: None")
    except Exception as e:
        print(f"  speech_to_text: Error - {e}")
    
    # 7. Check environment variables
    print('\n7. ENVIRONMENT VARIABLES:')
    print('-' * 40)
    env_vars = [
        "OPENAI_API_KEY", "THEALPHA_API_KEY", "THEALPHA_API_BASE",
        "GROQ_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY",
        "SERPER_API_KEY", "SURREAL_NAMESPACE", "SURREAL_DATABASE"
    ]
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            # Mask sensitive keys
            if "API_KEY" in var:
                masked_value = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
                print(f"  {var}: {masked_value}")
            else:
                print(f"  {var}: {value}")
        else:
            print(f"  {var}: Not set")
    
    # 8. Test model instantiation
    print('\n8. MODEL INSTANTIATION TESTS:')
    print('-' * 40)
    
    # Test each default model
    default_model_ids = [
        model_manager.defaults.default_chat_model,
        model_manager.defaults.default_embedding_model,
        model_manager.defaults.default_text_to_speech_model,
        model_manager.defaults.default_speech_to_text_model
    ]
    
    for model_id in default_model_ids:
        if model_id:
            try:
                model = model_manager.get_model(model_id)
                print(f"  {model_id}: ✅ Successfully instantiated")
                print(f"    Type: {type(model)}")
                print(f"    Provider: {model.provider}")
                if hasattr(model, 'models'):
                    print(f"    Models: {model.models}")
            except Exception as e:
                print(f"  {model_id}: ❌ Failed to instantiate - {e}")
        else:
            print(f"  {model_id}: No model ID set")
    
    # 9. Summary
    print('\n9. SUMMARY:')
    print('-' * 40)
    print("ASSIGNED MODELS:")
    
    # Language models
    try:
        chat_model = model_manager.get_default_model("chat")
        transformation_model = model_manager.get_default_model("transformation")
        tools_model = model_manager.get_default_model("tools")
        large_context_model = model_manager.get_default_model("large_context")
        
        print(f"  LANGUAGE MODELS:")
        print(f"    Chat Model: {chat_model.provider} - {chat_model.models[0] if chat_model and hasattr(chat_model, 'models') else 'None'}")
        print(f"    Transformation Model: {transformation_model.provider} - {transformation_model.models[0] if transformation_model and hasattr(transformation_model, 'models') else 'None'}")
        print(f"    Tools Model: {tools_model.provider} - {tools_model.models[0] if tools_model and hasattr(tools_model, 'models') else 'None'}")
        print(f"    Large Context Model: {large_context_model.provider} - {large_context_model.models[0] if large_context_model and hasattr(large_context_model, 'models') else 'None'}")
    except Exception as e:
        print(f"  LANGUAGE MODELS: Error - {e}")
    
    # Embedding model
    try:
        embedding_model = model_manager.get_default_model("embedding")
        print(f"  EMBEDDING MODEL: {embedding_model.provider} - {embedding_model.models[0] if embedding_model and hasattr(embedding_model, 'models') else 'None'}")
    except Exception as e:
        print(f"  EMBEDDING MODEL: Error - {e}")
    
    # TTS model
    try:
        tts_model = model_manager.get_default_model("text_to_speech")
        print(f"  TTS MODEL: {tts_model.provider} - {tts_model.models[0] if tts_model and hasattr(tts_model, 'models') else 'None'}")
    except Exception as e:
        print(f"  TTS MODEL: Error - {e}")
    
    # STT model
    try:
        stt_model = model_manager.get_default_model("speech_to_text")
        print(f"  STT MODEL: {stt_model.provider} - {stt_model.models[0] if stt_model and hasattr(stt_model, 'models') else 'None'}")
    except Exception as e:
        print(f"  STT MODEL: Error - {e}")
    
    print('\n' + '=' * 80)
    print('DEEP MODEL ANALYSIS COMPLETE')
    print('=' * 80)

if __name__ == "__main__":
    deep_model_analysis()




