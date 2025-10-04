"""
Patch for OpenAITextToSpeechModel to add the missing 'provider' attribute.
This is a workaround for the issue where the esperanto library's OpenAITextToSpeechModel
class doesn't have a 'provider' attribute that some parts of the code expect.
"""

# Import the original class
from esperanto.providers.tts.openai import OpenAITextToSpeechModel as OriginalOpenAITTS

# Create a patched version of the class
class PatchedOpenAITextToSpeechModel(OriginalOpenAITTS):
    """Patched version of OpenAITextToSpeechModel that includes the provider attribute."""
    
    def __init__(self, *args, **kwargs):
        """Initialize the patched TTS model with a provider attribute."""
        super().__init__(*args, **kwargs)
        # Add the missing provider attribute
        self.provider = "openai"

# Replace the original class with our patched version
import sys
import esperanto.providers.tts.openai as tts_openai
setattr(tts_openai, 'OpenAITextToSpeechModel', PatchedOpenAITextToSpeechModel)

# This ensures that any code that imports OpenAITextToSpeechModel gets our patched version
sys.modules['esperanto.providers.tts.openai'].OpenAITextToSpeechModel = PatchedOpenAITextToSpeechModel
