# Open Notebook FastAPI Backend

A comprehensive FastAPI backend for the Open Notebook application, providing RESTful APIs for notebook management, AI-powered features, and data processing.

## 🚀 Quick Start

### For Mir - Testing Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/22PA1A45B4/backend.git
   cd backend
   ```

2. **Run the automated setup:**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

3. **Start the server:**
   ```bash
   source venv/bin/activate
   python run.py
   ```

4. **Test the API:**
   ```bash
   python quick_test.py
   ```

5. **View API documentation:**
   - Swagger UI: http://localhost:8001/docs
   - ReDoc: http://localhost:8001/redoc

## 📚 Documentation

- **[TESTING_GUIDE.md](./TESTING_GUIDE.md)** - Comprehensive testing guide
- **[NOTE_CREATION_GUIDE.md](./NOTE_CREATION_GUIDE.md)** - Guide for note creation features
- **[MODELS_ENHANCEMENT.md](./MODELS_ENHANCEMENT.md)** - AI models integration guide

## 🔧 Manual Setup

If you prefer manual setup, see the [TESTING_GUIDE.md](./TESTING_GUIDE.md) for detailed instructions.

## 🧪 Testing

The project includes several test files:
- `quick_test.py` - Quick API functionality test
- `test_*.py` - Individual component tests
- `TESTING_GUIDE.md` - Comprehensive testing documentation

## 📡 API Endpoints

### Core Endpoints
- `GET /health` - Health check
- `GET /docs` - API documentation
- `GET /api/v1/notebooks` - List notebooks
- `POST /api/v1/notebooks` - Create notebook
- `GET /api/v1/notebooks/by-name/{name}` - Get notebook by name
- `PATCH /api/v1/notebooks/by-name/{name}` - Update notebook

### Features
- **Notebook Management** - CRUD operations for notebooks
- **Source Upload** - File upload and processing
- **AI Chat** - Conversational AI with context
- **Notes Creation** - AI-powered note generation
- **Search** - Full-text search across content
- **Podcast Generation** - AI-generated podcasts
- **Transformations** - Content transformation tools

## 🛠️ Technology Stack

- **FastAPI** - Modern Python web framework
- **SurrealDB** - Multi-model database
- **LangChain** - AI/LLM integration
- **OpenAI/Anthropic/Google** - AI model providers
- **Uvicorn** - ASGI server

## 📝 Environment Variables

Create a `.env` file with:
```env
# Database
SURREAL_ADDRESS=localhost
SURREAL_PORT=8000
SURREAL_USER=root
SURREAL_PASS=root
SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=main

# FastAPI
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8001
FASTAPI_RELOAD=true

# AI API Keys
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
GOOGLE_API_KEY=your_key_here
SERPER_API_KEY=your_key_here
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request
