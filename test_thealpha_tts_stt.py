#!/usr/bin/env python3
import requests
import os
from dotenv import load_dotenv

def test_thealpha_tts_stt():
    load_dotenv()
    
    print('=== TESTING THEALPHA TTS/STT MODELS ===')
    
    api_key = os.environ.get("THEALPHA_API_KEY")
    base_url = os.environ.get("THEALPHA_API_BASE", "https://thealpha.dev/api")
    
    print(f'API Key: {api_key}')
    print(f'Base URL: {base_url}')
    
    # Test TTS models
    tts_models = [
        "tts-1",
        "tts-1-hd", 
        "gpt-4o-mini-tts",
        "openai/tts-1",
        "openai/tts-1-hd",
        "openaigpt-41-mini-tts"
    ]
    
    print('\n--- TESTING TTS MODELS ---')
    for model_name in tts_models:
        try:
            tts_data = {
                "model": model_name,
                "input": "Hello, this is a test message for text to speech.",
                "voice": "alloy"
            }
            response = requests.post(
                f"{base_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json=tts_data,
                timeout=10
            )
            print(f'{model_name}: {response.status_code}')
            if response.status_code == 200:
                print(f'  ✅ SUCCESS: TTS model working')
            else:
                print(f'  ❌ ERROR: {response.text}')
        except Exception as e:
            print(f'{model_name}: ERROR - {e}')
    
    # Test STT models
    stt_models = [
        "whisper-1",
        "whisper-1-large",
        "openai/whisper-1",
        "openaigpt-41-mini-stt"
    ]
    
    print('\n--- TESTING STT MODELS ---')
    for model_name in stt_models:
        try:
            # Create a simple test audio file (just a placeholder)
            stt_data = {
                "model": model_name,
                "file": "test_audio.wav",
                "language": "en"
            }
            response = requests.post(
                f"{base_url}/audio/transcriptions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json=stt_data,
                timeout=10
            )
            print(f'{model_name}: {response.status_code}')
            if response.status_code == 200:
                print(f'  ✅ SUCCESS: STT model working')
            elif response.status_code == 400:
                print(f'  ⚠️  Model exists but needs proper audio file')
            else:
                print(f'  ❌ ERROR: {response.text}')
        except Exception as e:
            print(f'{model_name}: ERROR - {e}')

if __name__ == "__main__":
    test_thealpha_tts_stt()
