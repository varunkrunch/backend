from typing import ClassVar, Dict, Optional, Union

from esperanto import (
    AIFactory,
    EmbeddingModel,
    LanguageModel,
    SpeechToTextModel,
    TextToSpeechModel,
)

from ..database.repository import repo_query
from .base import ObjectModel, RecordModel

ModelType = Union[LanguageModel, EmbeddingModel, SpeechToTextModel, TextToSpeechModel]


class Model(ObjectModel):
    table_name: ClassVar[str] = "model"
    name: str
    provider: str
    type: str

    @classmethod
    def get_models_by_type(cls, model_type):
        models = repo_query(
            "SELECT * FROM model WHERE type=$model_type;", {"model_type": model_type}
        )
        return [Model(**model) for model in models]


class DefaultModels(RecordModel):
    record_id: ClassVar[str] = "open_notebook:default_models"
    default_chat_model: Optional[str] = None
    default_transformation_model: Optional[str] = None
    large_context_model: Optional[str] = None
    default_text_to_speech_model: Optional[str] = None
    default_speech_to_text_model: Optional[str] = None
    # default_vision_model: Optional[str]
    default_embedding_model: Optional[str] = None
    default_tools_model: Optional[str] = None


class ModelManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._model_cache: Dict[str, ModelType] = {}
            self._default_models = None
            self.refresh_defaults()
    
    def clear_cache(self):
        """Clear the model cache to force reload of models"""
        self._model_cache.clear()
        self._default_models = None
        self.refresh_defaults()

    def get_model(self, model_id: str, **kwargs) -> Optional[ModelType]:
        import os
        
        if not model_id:
            return None

        cache_key = f"{model_id}:{str(kwargs)}"

        if cache_key in self._model_cache:
            cached_model = self._model_cache[cache_key]
            if not isinstance(
                cached_model,
                (LanguageModel, EmbeddingModel, SpeechToTextModel, TextToSpeechModel),
            ):
                raise TypeError(
                    f"Cached model is of unexpected type: {type(cached_model)}"
                )
            return cached_model

        model: Model = Model.get(model_id)

        if not model:
            raise ValueError(f"Model with ID {model_id} not found")

        if not model.type or model.type not in [
            "language",
            "embedding",
            "speech_to_text",
            "text_to_speech",
        ]:
            raise ValueError(f"Invalid model type: {model.type}")

        # Special handling for thealpha provider - treat as custom OpenAI endpoint
        if model.provider == "thealpha":
            # Clear any cached thealpha models to ensure fresh configuration
            keys_to_remove = [key for key in self._model_cache.keys() if key.startswith(model_id)]
            for key in keys_to_remove:
                print(f"DEBUG: Removing cached thealpha model: {key}")
                del self._model_cache[key]
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings
            
            # Get thealpha configuration from environment
            thealpha_api_key = os.environ.get("THEALPHA_API_KEY")
            thealpha_base_url = os.environ.get("THEALPHA_API_BASE", "https://thealpha.dev/api")
            
            # Clear cache to ensure fresh models with current environment variables
            cache_key = f"{model_id}:{str(kwargs)}"
            if cache_key in self._model_cache:
                print(f"DEBUG: Clearing cached model for key: {cache_key}")
                del self._model_cache[cache_key]
            
            # Debug logging
            print(f"DEBUG: THEALPHA_API_KEY = {thealpha_api_key}")
            print(f"DEBUG: THEALPHA_API_BASE = {thealpha_base_url}")
            print(f"DEBUG: All env vars with THEALPHA: {[k for k in os.environ.keys() if 'THEALPHA' in k]}")
            print(f"DEBUG: Expected API key: sk-b914a7397daa42088f47bfc825cc995d")
            print(f"DEBUG: API key matches expected: {thealpha_api_key == 'sk-b914a7397daa42088f47bfc825cc995d'}")
            print(f"DEBUG: Expected base URL: https://thealpha.dev/api/v1/")
            print(f"DEBUG: Base URL matches expected: {thealpha_base_url == 'https://thealpha.dev/api/v1/'}")
            
            if not thealpha_api_key:
                raise ValueError("THEALPHA_API_KEY not found in environment variables")
            
            # Test the API key by making a simple request
            try:
                import requests
                test_response = requests.get(
                    f"{thealpha_base_url}/models",
                    headers={"Authorization": f"Bearer {thealpha_api_key}"},
                    timeout=5
                )
                print(f"DEBUG: TheAlpha API test response: {test_response.status_code}")
                if test_response.status_code == 200:
                    models_data = test_response.json()
                    print(f"DEBUG: Available models: {models_data}")
                else:
                    print(f"DEBUG: TheAlpha API test failed: {test_response.text}")
            except Exception as e:
                print(f"DEBUG: TheAlpha API test error: {e}")
            
            # Create model based on type using LangChain directly with thealpha config
            if model.type == "language":
                # Create a wrapper that inherits from LanguageModel
                class TheAlphaLanguageModel(LanguageModel):
                    def __init__(self, model_name, api_key, base_url, **kwargs):
                        super().__init__()
                        self._model = ChatOpenAI(
                            model=model_name,
                            api_key=api_key,
                            base_url=base_url,
                            **kwargs
                        )
                        self._model_name = model_name
                        self._api_key = api_key
                        self._base_url = base_url
                    
                    def _get_default_model(self):
                        return self._model_name
                    
                    def achat_complete(self, *args, **kwargs):
                        return self._model.ainvoke(*args, **kwargs)
                    
                    def chat_complete(self, *args, **kwargs):
                        return self._model.invoke(*args, **kwargs)
                    
                    @property
                    def models(self):
                        return [self._model_name]
                    
                    @property
                    def provider(self):
                        return "thealpha"
                    
                    def to_langchain(self):
                        return self._model
                    
                    def __getattr__(self, name):
                        return getattr(self._model, name)
                
                model_instance = TheAlphaLanguageModel(
                    model_name=model.name,
                    api_key=thealpha_api_key,
                    base_url=thealpha_base_url,
                    **kwargs
                )
            elif model.type == "embedding":
                # Create a wrapper that inherits from EmbeddingModel
                class TheAlphaEmbeddingModel(EmbeddingModel):
                    def __init__(self, model_name, api_key, base_url, **kwargs):
                        super().__init__()
                        # The thealpha API doesn't support embeddings
                        # We'll create a dummy embedding model that returns empty embeddings
                        self._model = None  # No actual embedding model
                        self._model_name = model_name
                        self._api_key = api_key
                        self._base_url = base_url
                        
                        # Debug: Verify the model configuration
                        print(f"DEBUG: TheAlphaEmbeddingModel created with:")
                        print(f"  - model_name: {model_name}")
                        print(f"  - api_key: {api_key}")
                        print(f"  - base_url: {base_url}")
                        print(f"  - Note: TheAlpha API doesn't support embeddings, returning empty embeddings")
                    
                    def _get_default_model(self):
                        return self._model_name
                    
                    def aembed_documents(self, *args, **kwargs):
                        # Return empty embeddings since thealpha doesn't support embeddings
                        return [[] for _ in args[0]] if args else []
                    
                    def aembed_query(self, *args, **kwargs):
                        # Return empty embedding since thealpha doesn't support embeddings
                        return []
                    
                    def embed_documents(self, *args, **kwargs):
                        # Return empty embeddings since thealpha doesn't support embeddings
                        return [[] for _ in args[0]] if args else []
                    
                    def embed_query(self, *args, **kwargs):
                        # Return empty embedding since thealpha doesn't support embeddings
                        return []
                    
                    def aembed(self, *args, **kwargs):
                        # Return empty embeddings since thealpha doesn't support embeddings
                        return [[] for _ in args[0]] if args else []
                    
                    def embed(self, *args, **kwargs):
                        # Return empty embeddings since thealpha doesn't support embeddings
                        return [[] for _ in args[0]] if args else []
                    
                    @property
                    def models(self):
                        return [self._model_name]
                    
                    @property
                    def provider(self):
                        return "thealpha"
                    
                    def to_langchain(self):
                        # Return a simple object since we don't have an actual embedding model
                        return type('LangChainEmbedding', (), {})()
                    
                    def __getattr__(self, name):
                        # Since we don't have an actual model, return None for any attribute access
                        return None
                
                model_instance = TheAlphaEmbeddingModel(
                    model_name=model.name,
                    api_key=thealpha_api_key,
                    base_url=thealpha_base_url,
                    **kwargs
                )
                print(f"DEBUG: Created TheAlphaEmbeddingModel with api_key={thealpha_api_key}, base_url={thealpha_base_url}")
                
                # Test the model immediately
                try:
                    test_embedding = model_instance.embed(["test"])
                    print(f"DEBUG: Model test successful, embedding length: {len(test_embedding)}")
                    print(f"DEBUG: Note: TheAlpha API doesn't support embeddings, returning empty embeddings")
                except Exception as e:
                    print(f"DEBUG: Model test failed: {e}")
                    print(f"DEBUG: Model instance attributes:")
                    print(f"  - _api_key: {getattr(model_instance, '_api_key', 'NOT SET')}")
                    print(f"  - _base_url: {getattr(model_instance, '_base_url', 'NOT SET')}")
                    print(f"  - _model_name: {getattr(model_instance, '_model_name', 'NOT SET')}")
                    print(f"  - Note: TheAlpha API doesn't support embeddings")
            elif model.type == "text_to_speech":
                # TheAlpha doesn't support TTS models - raise an error instead of creating a placeholder
                raise ValueError(f"TheAlpha provider doesn't support TTS models. Please use a different provider for text-to-speech functionality.")
            elif model.type == "speech_to_text":
                # TheAlpha doesn't support STT models - raise an error instead of creating a placeholder
                raise ValueError(f"TheAlpha provider doesn't support STT models. Please use a different provider for speech-to-text functionality.")
            else:
                raise ValueError(f"Unsupported model type for thealpha: {model.type}")
        else:
            # Handle other providers based on model type
            if model.type == "language":
                model_instance: LanguageModel = AIFactory.create_language(
                    model_name=model.name,
                    provider=model.provider,
                    config=kwargs,
                )
            elif model.type == "embedding":
                model_instance: EmbeddingModel = AIFactory.create_embedding(
                    model_name=model.name,
                    provider=model.provider,
                    config=kwargs,
                )
            elif model.type == "text_to_speech":
                model_instance: TextToSpeechModel = AIFactory.create_text_to_speech(
                    model_name=model.name,
                    provider=model.provider,
                    config=kwargs,
                )
            elif model.type == "speech_to_text":
                model_instance: SpeechToTextModel = AIFactory.create_speech_to_text(
                    model_name=model.name,
                    provider=model.provider,
                    config=kwargs,
                )
            else:
                raise ValueError(f"Unsupported model type: {model.type}")

        self._model_cache[cache_key] = model_instance
        return model_instance

    def refresh_defaults(self):
        """Refresh the default models from the database"""
        self._default_models = DefaultModels()

    @property
    def defaults(self) -> DefaultModels:
        """Get the default models configuration"""
        if not self._default_models:
            self.refresh_defaults()
            if not self._default_models:
                raise RuntimeError("Failed to initialize default models configuration")
        return self._default_models

    @property
    def speech_to_text(self, **kwargs) -> Optional[SpeechToTextModel]:
        """Get the default speech-to-text model"""
        model_id = self.defaults.default_speech_to_text_model
        if not model_id:
            return None
        model = self.get_model(model_id, **kwargs)
        assert model is None or isinstance(model, SpeechToTextModel), (
            f"Expected SpeechToTextModel but got {type(model)}"
        )
        return model

    @property
    def text_to_speech(self, **kwargs) -> Optional[TextToSpeechModel]:
        """Get the default text-to-speech model"""
        model_id = self.defaults.default_text_to_speech_model
        if not model_id:
            return None
        model = self.get_model(model_id, **kwargs)
        assert model is None or isinstance(model, TextToSpeechModel), (
            f"Expected TextToSpeechModel but got {type(model)}"
        )
        return model

    @property
    def embedding_model(self, **kwargs) -> Optional[EmbeddingModel]:
        """Get the default embedding model"""
        print(f"DEBUG: embedding_model property called")
        model_id = self.defaults.default_embedding_model
        print(f"DEBUG: Default embedding model ID: {model_id}")
        
        if not model_id:
            print("DEBUG: No default embedding model set")
            return None
        
        print(f"DEBUG: Getting embedding model with ID: {model_id}")
        model = self.get_model(model_id, **kwargs)
        print(f"DEBUG: Got embedding model: {type(model)}")
        
        assert model is None or isinstance(model, EmbeddingModel), (
            f"Expected EmbeddingModel but got {type(model)}"
        )
        return model

    def get_default_model(self, model_type: str, **kwargs) -> Optional[ModelType]:
        """
        Get the default model for a specific type.

        Args:
            model_type: The type of model to retrieve (e.g., 'chat', 'embedding', etc.)
            **kwargs: Additional arguments to pass to the model constructor
        """
        model_id = None

        if model_type == "chat":
            model_id = self.defaults.default_chat_model
        elif model_type == "transformation":
            model_id = (
                self.defaults.default_transformation_model
                or self.defaults.default_chat_model
            )
        elif model_type == "tools":
            model_id = (
                self.defaults.default_tools_model or self.defaults.default_chat_model
            )
        elif model_type == "embedding":
            model_id = self.defaults.default_embedding_model
        elif model_type == "text_to_speech":
            model_id = self.defaults.default_text_to_speech_model
        elif model_type == "speech_to_text":
            model_id = self.defaults.default_speech_to_text_model
        elif model_type == "large_context":
            model_id = self.defaults.large_context_model

        if not model_id:
            return None

        return self.get_model(model_id, **kwargs)

    def clear_cache(self):
        """Clear the model cache"""
        self._model_cache.clear()


model_manager = ModelManager()
