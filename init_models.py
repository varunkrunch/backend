#!/usr/bin/env python3
"""
Initialize default models in the database for FastAPI backend.
This script sets up the default model configurations.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from open_notebook.database.repository import db_connection
from open_notebook.domain.models import DefaultModels, Model

def init_default_models():
    """Initialize default models configuration"""
    print("🔧 Initializing default models...")
    
    with db_connection() as db:
        # Create default models record
        default_models = DefaultModels(
            default_chat_model="gpt-4o-mini",
            default_transformation_model="gpt-4o-mini", 
            large_context_model="gpt-4o",
            default_embedding_model="text-embedding-3-small",
            default_text_to_speech_model=None,
            default_speech_to_text_model=None,
            default_tools_model="gpt-4o-mini"
        )
        
        try:
            default_models.save()
            print("✅ Default models configuration saved")
        except Exception as e:
            print(f"⚠️  Default models may already exist: {e}")
        
        # Create some basic model records
        models_to_create = [
            {
                "name": "gpt-4o-mini",
                "provider": "openai", 
                "type": "language"
            },
            {
                "name": "gpt-4o",
                "provider": "openai",
                "type": "language"
            },
            {
                "name": "text-embedding-3-small",
                "provider": "openai",
                "type": "embedding"
            },
            {
                "name": "claude-3-sonnet-20240229",
                "provider": "anthropic",
                "type": "language"
            }
        ]
        
        for model_data in models_to_create:
            try:
                model = Model(**model_data)
                model.save()
                print(f"✅ Created model: {model_data['name']}")
            except Exception as e:
                print(f"⚠️  Model {model_data['name']} may already exist: {e}")

def check_environment():
    """Check if required environment variables are set"""
    print("🔍 Checking environment variables...")
    
    required_vars = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY", 
        "GROQ_API_KEY"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"⚠️  Missing environment variables: {', '.join(missing_vars)}")
        print("   The backend will work but some AI features may not be available.")
    else:
        print("✅ All required environment variables are set")

if __name__ == "__main__":
    print("🚀 FastAPI Backend Model Initialization")
    print("=" * 50)
    
    check_environment()
    print()
    
    try:
        init_default_models()
        print()
        print("🎉 Model initialization completed successfully!")
        print()
        print("Next steps:")
        print("1. Make sure your .env file has the required API keys")
        print("2. Start the backend: python run.py")
        print("3. Test the AI Assistant in the frontend")
        
    except Exception as e:
        print(f"❌ Error during initialization: {e}")
        print("Make sure the database is running and accessible.")
        sys.exit(1)
