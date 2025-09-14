#!/bin/bash

# FastAPI Backend Dependencies Installation Script
# This script installs all required dependencies including git dependencies

set -e

echo "🚀 Installing FastAPI Backend Dependencies..."

# Check if we're in a virtual environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Warning: No virtual environment detected. Consider using a virtual environment."
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 1
    fi
fi

# Install git dependencies first
echo "📦 Installing git dependencies..."

# Install sblpy (SurrealDB Python client)
echo "Installing sblpy..."
pip install git+https://github.com/lfnovo/surreal-lite-py.git

# Install podcastfy (Podcast generation)
echo "Installing podcastfy..."
pip install git+https://github.com/lfnovo/podcastfy.git

# Fix NumPy compatibility issues first
echo "🔧 Fixing NumPy compatibility..."
pip install "numpy>=1.22.4,<2.0.0" --force-reinstall

# Install main requirements
echo "📦 Installing main requirements..."
pip install -r requirements-backend.txt

echo "✅ All dependencies installed successfully!"
echo ""
echo "🔧 Initializing default models..."
python init_models.py
echo ""
echo "🎉 FastAPI Backend is ready to run!"
echo ""
echo "To start the server:"
echo "  python run.py"
echo ""
echo "To access the API documentation:"
echo "  http://localhost:8000/docs"
echo ""
echo "⚠️  Make sure to set up your .env file with API keys:"
echo "  OPENAI_API_KEY=your_key_here"
echo "  ANTHROPIC_API_KEY=your_key_here"
echo "  GROQ_API_KEY=your_key_here"
