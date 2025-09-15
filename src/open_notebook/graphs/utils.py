from esperanto import LanguageModel
from langchain_core.language_models.chat_models import BaseChatModel
from loguru import logger

from ..domain.models import model_manager
from ..utils import token_count


def provision_langchain_model(
    content, model_id, default_type, **kwargs
) -> BaseChatModel:
    """
    Returns the best model to use based on the context size and on whether there is a specific model being requested in Config.
    If context > 105_000, returns the large_context_model
    If model_id is specified in Config, returns that model
    Otherwise, returns the default model for the given type
    """
    tokens = token_count(content)

    if tokens > 105_000:
        logger.debug(
            f"Using large context model because the content has {tokens} tokens"
        )
        model = model_manager.get_default_model("large_context", **kwargs)
    elif model_id:
        model = model_manager.get_model(model_id, **kwargs)
    else:
        model = model_manager.get_default_model(default_type, **kwargs)

    # If no model is configured, try to get any available language model as fallback
    if model is None:
        logger.warning(f"No default {default_type} model configured, trying to find any available language model")
        try:
            # Try to get the first available language model as fallback
            # This is a temporary fix until proper default model configuration is set up
            from ..domain.models import Model
            from esperanto import AIFactory
            
            # Get all language models from the database
            available_models = Model.select().where(Model.type == "language").limit(1)
            if available_models:
                fallback_model = available_models[0]
                logger.info(f"Using fallback model: {fallback_model.name} ({fallback_model.provider})")
                model = AIFactory.create_language(
                    model_name=fallback_model.name,
                    provider=fallback_model.provider,
                    config=kwargs,
                )
            else:
                # Last resort: create a basic OpenAI model
                logger.warning("No models found in database, creating fallback OpenAI model")
                model = AIFactory.create_language(
                    model_name="gpt-3.5-turbo",
                    provider="openai",
                    config=kwargs,
                )
        except Exception as e:
            logger.error(f"Failed to create fallback model: {e}")
            # Create a basic OpenAI model as last resort
            model = AIFactory.create_language(
                model_name="gpt-3.5-turbo",
                provider="openai",
                config=kwargs,
            )

    logger.debug(f"Using model: {model}")
    assert isinstance(model, LanguageModel), f"Model is not a LanguageModel: {model}"
    return model.to_langchain()
