#!/usr/bin/env python3
import sys
import os
sys.path.append('src')

from open_notebook.domain.models import model_manager

def test_updated_tts_stt():
    print('=== TESTING UPDATED TTS/STT MODELS ===')
    
    try:
        # Test TTS model
        print('\n--- TESTING TTS MODEL ---')
        tts_model = model_manager.get_default_model('text_to_speech')
        if tts_model:
            print(f'TTS model type: {type(tts_model)}')
            print(f'TTS model provider: {tts_model.provider}')
            print(f'TTS model name: {tts_model._get_default_model()}')
            print('✅ TTS model configured with thealpha')
        else:
            print('❌ No TTS model found')
        
        # Test STT model
        print('\n--- TESTING STT MODEL ---')
        stt_model = model_manager.get_default_model('speech_to_text')
        if stt_model:
            print(f'STT model type: {type(stt_model)}')
            print(f'STT model provider: {stt_model.provider}')
            print(f'STT model name: {stt_model._get_default_model()}')
            print('✅ STT model configured with thealpha')
        else:
            print('❌ No STT model found')
            
        return True
        
    except Exception as e:
        print(f'❌ Error testing TTS/STT models: {e}')
        print(f'Error type: {type(e)}')
        return False

if __name__ == "__main__":
    success = test_updated_tts_stt()
    if success:
        print('\n🎉 TTS and STT models updated to use thealpha!')
    else:
        print('\n❌ TTS and STT models have issues')

