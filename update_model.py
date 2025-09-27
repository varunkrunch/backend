#!/usr/bin/env python3
"""
Script to update the thealpha model name in the database
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Load environment variables from .env file
# No hardcoded API keys - use environment variables instead

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from open_notebook.domain.models import Model

def update_thealpha_model():
    """Update the thealpha model name to the new format"""
    try:
        # Get all language models
        models = Model.get_models_by_type('language')
        print(f"Found {len(models)} language models")
        
        for model in models:
            print(f"Model: {model.name} ({model.provider})")
            
            if model.provider == 'thealpha':
                print(f"  Current name: {model.name}")
                print(f"  Updating to: OpenAI.gpt-4.1-mini")
                
                # Update the model name
                model.name = "OpenAI.gpt-4.1-mini"
                model.save()
                
                print(f"  ✅ Updated successfully!")
                return True
        
        print("No thealpha model found to update")
        return False
        
    except Exception as e:
        print(f"Error updating model: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Updating thealpha model configuration...")
    success = update_thealpha_model()
    if success:
        print("✅ Model updated successfully!")
    else:
        print("❌ Failed to update model")
