#!/usr/bin/env python3
"""
Test script for models functionality and AI integration
This script validates the robustness of the models endpoint and AI integration
"""

import asyncio
import os
import sys
from typing import Dict, Any
import httpx
import json

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from fastapi.testclient import TestClient
from main import app

# Test configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

class ModelIntegrationTester:
    def __init__(self):
        self.client = TestClient(app)
        self.test_models = []
        self.test_defaults = {}
        
    def log(self, message: str, level: str = "INFO"):
        """Log messages with timestamp"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
    
    def test_provider_status(self):
        """Test provider status endpoint"""
        self.log("Testing provider status endpoint...")
        
        response = self.client.get(f"{API_BASE}/models/providers")
        assert response.status_code == 200, f"Provider status failed: {response.status_code}"
        
        data = response.json()
        assert "available" in data, "Provider status missing 'available' field"
        assert "unavailable" in data, "Provider status missing 'unavailable' field"
        
        self.log(f"Available providers: {data['available']}")
        self.log(f"Unavailable providers: {data['unavailable']}")
        
        return data
    
    def test_providers_for_type(self):
        """Test providers for specific model types"""
        self.log("Testing providers for model types...")
        
        model_types = ["language", "embedding", "text_to_speech", "speech_to_text"]
        
        for model_type in model_types:
            response = self.client.get(f"{API_BASE}/models/providers/{model_type}")
            assert response.status_code == 200, f"Providers for {model_type} failed: {response.status_code}"
            
            data = response.json()
            assert isinstance(data, list), f"Providers for {model_type} should be a list"
            
            self.log(f"Available providers for {model_type}: {data}")
        
        return True
    
    def test_model_types(self):
        """Test model types endpoint"""
        self.log("Testing model types endpoint...")
        
        response = self.client.get(f"{API_BASE}/models/types")
        assert response.status_code == 200, f"Model types failed: {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Model types should be a list"
        
        expected_types = ["language", "embedding", "text_to_speech", "speech_to_text"]
        for model_type in data:
            assert "type" in model_type, "Model type missing 'type' field"
            assert "available" in model_type, "Model type missing 'available' field"
            assert model_type["type"] in expected_types, f"Unexpected model type: {model_type['type']}"
        
        self.log(f"Model types: {data}")
        return data
    
    def test_create_model(self, model_data: Dict[str, Any]):
        """Test creating a model"""
        self.log(f"Testing model creation: {model_data['name']}")
        
        response = self.client.post(f"{API_BASE}/models", json=model_data)
        assert response.status_code == 201, f"Model creation failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert data["name"] == model_data["name"], "Model name mismatch"
        assert data["provider"] == model_data["provider"], "Model provider mismatch"
        assert data["type"] == model_data["type"], "Model type mismatch"
        
        self.test_models.append(data["id"])
        self.log(f"Created model: {data['id']}")
        return data
    
    def test_list_models(self):
        """Test listing models"""
        self.log("Testing model listing...")
        
        # Test without filters
        response = self.client.get(f"{API_BASE}/models")
        assert response.status_code == 200, f"Model listing failed: {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Model list should be a list"
        
        # Test with type filter
        response = self.client.get(f"{API_BASE}/models?type=language")
        assert response.status_code == 200, f"Model listing with type filter failed: {response.status_code}"
        
        data = response.json()
        for model in data:
            assert model["type"] == "language", f"Filtered model has wrong type: {model['type']}"
        
        # Test with provider filter
        response = self.client.get(f"{API_BASE}/models?provider=openai")
        assert response.status_code == 200, f"Model listing with provider filter failed: {response.status_code}"
        
        self.log(f"Found {len(data)} models")
        return data
    
    def test_list_models_by_type(self):
        """Test listing models by type"""
        self.log("Testing list models by type...")
        
        model_types = ["language", "embedding", "text_to_speech", "speech_to_text"]
        
        for model_type in model_types:
            response = self.client.get(f"{API_BASE}/models/by-type/{model_type}")
            assert response.status_code == 200, f"List models by type {model_type} failed: {response.status_code}"
            
            data = response.json()
            assert "models" in data, f"Response missing 'models' field for {model_type}"
            assert isinstance(data["models"], list), f"Models field should be a list for {model_type}"
            
            self.log(f"Found {len(data['models'])} {model_type} models")
        
        return True
    
    def test_get_model(self, model_id: str):
        """Test getting a specific model"""
        self.log(f"Testing model retrieval: {model_id}")
        
        response = self.client.get(f"{API_BASE}/models/{model_id}")
        assert response.status_code == 200, f"Model retrieval failed: {response.status_code}"
        
        data = response.json()
        assert data["id"] == model_id, "Model ID mismatch"
        assert "provider_status" in data, "Model missing provider_status"
        
        self.log(f"Retrieved model: {data['name']} ({data['provider']})")
        return data
    
    def test_update_model(self, model_id: str, update_data: Dict[str, Any]):
        """Test updating a model"""
        self.log(f"Testing model update: {model_id}")
        
        response = self.client.patch(f"{API_BASE}/models/{model_id}", json=update_data)
        assert response.status_code == 200, f"Model update failed: {response.status_code}"
        
        data = response.json()
        for key, value in update_data.items():
            if key in data:
                assert data[key] == value, f"Model update field mismatch for {key}"
        
        self.log(f"Updated model: {model_id}")
        return data
    
    def test_model_validation(self):
        """Test model validation"""
        self.log("Testing model validation...")
        
        # Test invalid provider
        invalid_model = {
            "name": "test-model",
            "provider": "invalid-provider",
            "type": "language"
        }
        
        response = self.client.post(f"{API_BASE}/models", json=invalid_model)
        assert response.status_code == 422, f"Invalid provider should be rejected: {response.status_code}"
        
        # Test invalid model type
        invalid_model = {
            "name": "test-model",
            "provider": "openai",
            "type": "invalid-type"
        }
        
        response = self.client.post(f"{API_BASE}/models", json=invalid_model)
        assert response.status_code == 422, f"Invalid model type should be rejected: {response.status_code}"
        
        # Test empty model name
        invalid_model = {
            "name": "",
            "provider": "openai",
            "type": "language"
        }
        
        response = self.client.post(f"{API_BASE}/models", json=invalid_model)
        assert response.status_code == 422, f"Empty model name should be rejected: {response.status_code}"
        
        self.log("Model validation tests passed")
    
    def test_default_models(self):
        """Test default models functionality"""
        self.log("Testing default models...")
        
        # Get current defaults
        response = self.client.get(f"{API_BASE}/models/defaults")
        assert response.status_code == 200, f"Get defaults failed: {response.status_code}"
        
        data = response.json()
        assert "id" in data, "Defaults missing ID"
        
        self.test_defaults = data
        self.log(f"Current defaults: {data}")
        
        # Test updating defaults (if we have models)
        if self.test_models:
            update_data = {
                "default_chat_model": self.test_models[0] if self.test_models else None
            }
            
            response = self.client.patch(f"{API_BASE}/models/defaults", json=update_data)
            assert response.status_code == 200, f"Update defaults failed: {response.status_code}"
            
            updated_data = response.json()
            assert updated_data["default_chat_model"] == update_data["default_chat_model"]
            
            self.log("Default models updated successfully")
        
        return data
    
    def test_model_testing(self, model_id: str):
        """Test model testing endpoint"""
        self.log(f"Testing model testing endpoint: {model_id}")
        
        # Get model first to check type
        model = self.test_get_model(model_id)
        
        if model["type"] == "language":
            response = self.client.post(f"{API_BASE}/models/{model_id}/test")
            # This might fail if no API keys are configured, which is expected
            if response.status_code == 200:
                self.log("Model test successful")
            else:
                self.log(f"Model test failed (expected if no API keys): {response.status_code}")
        else:
            self.log(f"Skipping test for non-language model: {model['type']}")
    
    def test_ai_integration(self):
        """Test AI integration endpoints"""
        self.log("Testing AI integration...")
        
        # Test ask endpoint (if we have a chat model)
        if self.test_defaults.get("default_chat_model"):
            ask_request = {
                "question": "Hello, this is a test message.",
                "metadata": {
                    "model_id": self.test_defaults["default_chat_model"]
                }
            }
            
            response = self.client.post(f"{API_BASE}/ask", json=ask_request)
            # This might fail if no API keys are configured, which is expected
            if response.status_code == 200:
                data = response.json()
                assert "answer" in data, "Ask response missing answer"
                self.log("AI integration test successful")
            else:
                self.log(f"AI integration test failed (expected if no API keys): {response.status_code}")
        else:
            self.log("Skipping AI integration test - no chat model configured")
    
    def test_cache_management(self):
        """Test model cache management"""
        self.log("Testing cache management...")
        
        response = self.client.post(f"{API_BASE}/models/cache/clear")
        assert response.status_code == 200, f"Cache clear failed: {response.status_code}"
        
        data = response.json()
        assert data["status"] == "success", "Cache clear should return success"
        
        self.log("Cache management test successful")
    
    def cleanup(self):
        """Clean up test data"""
        self.log("Cleaning up test data...")
        
        for model_id in self.test_models:
            try:
                response = self.client.delete(f"{API_BASE}/models/{model_id}")
                if response.status_code == 200:
                    self.log(f"Deleted test model: {model_id}")
                else:
                    self.log(f"Failed to delete test model {model_id}: {response.status_code}")
            except Exception as e:
                self.log(f"Error deleting test model {model_id}: {e}")
    
    def run_all_tests(self):
        """Run all tests"""
        self.log("Starting comprehensive model integration tests...")
        
        try:
            # Test provider status
            self.test_provider_status()
            
            # Test providers for specific types
            self.test_providers_for_type()
            
            # Test model types
            self.test_model_types()
            
            # Test model validation
            self.test_model_validation()
            
            # Test creating models
            test_models_data = [
                {
                    "name": "gpt-4o-mini",
                    "provider": "openai",
                    "type": "language"
                },
                {
                    "name": "text-embedding-3-small",
                    "provider": "openai",
                    "type": "embedding"
                }
            ]
            
            for model_data in test_models_data:
                self.test_create_model(model_data)
            
            # Test listing models
            self.test_list_models()
            
            # Test listing models by type
            self.test_list_models_by_type()
            
            # Test getting specific models
            if self.test_models:
                self.test_get_model(self.test_models[0])
                
                # Test updating models
                update_data = {
                    "name": "gpt-4o-mini-updated"
                }
                self.test_update_model(self.test_models[0], update_data)
                
                # Test model testing
                self.test_model_testing(self.test_models[0])
            
            # Test default models
            self.test_default_models()
            
            # Test AI integration
            self.test_ai_integration()
            
            # Test cache management
            self.test_cache_management()
            
            self.log("All tests completed successfully!")
            
        except Exception as e:
            self.log(f"Test failed: {e}", "ERROR")
            raise
        finally:
            # Clean up
            self.cleanup()

def main():
    """Main test runner"""
    print("=" * 60)
    print("Models Integration Test Suite")
    print("=" * 60)
    
    tester = ModelIntegrationTester()
    tester.run_all_tests()
    
    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)

if __name__ == "__main__":
    main() 