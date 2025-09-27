#!/usr/bin/env python3
"""
Test script to check model provision with new thealpha configuration
"""
import os
import sys

# Load environment variables from .env file
# No hardcoded API keys - use environment variables instead

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_model_provision():
    """Test the model provision function"""
    try:
        from open_notebook.graphs.utils import provision_langchain_model
        from langchain_core.messages import SystemMessage, HumanMessage
        
        print("Testing model provision...")
        
        # Test the model provision
        chain = provision_langchain_model('test content', None, 'transformation')
        if chain:
            print("✅ Model provision successful")
            
            # Test the model invocation
            payload = [SystemMessage(content='Test prompt'), HumanMessage(content='Test content')]
            response = chain.invoke(payload)
            print(f"✅ Model invocation successful: {response.content[:100]}...")
            return True
        else:
            print("❌ Model provision returned None")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing thealpha model configuration...")
    success = test_model_provision()
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Tests failed!")
