# Open Notebook - AI-Powered Knowledge Management

A comprehensive knowledge management system with AI-powered features for organizing, processing, and interacting with your notes, documents, and multimedia content.

## 🚀 Features

- **Notebook Management** - Organize your knowledge in notebooks with rich text and media support
- **AI-Powered Insights** - Generate summaries, key points, and insights from your content
- **Multi-Media Support** - Work with text, audio (podcasts), and other media types
- **Conversational AI** - Chat with your notes using AI with full context awareness
- **Advanced Search** - Semantic and full-text search across all your content
- **API-First** - Fully documented REST API for integration with other tools

## 🛠️ Technology Stack

- **Backend**: FastAPI (Python 3.10+)
- **Database**: SurrealDB (graph database with document store)
- **AI/ML**: LangChain, OpenAI, Anthropic, Google AI, and other LLM providers
- **Search**: Vector and full-text search capabilities
- **API Documentation**: Swagger UI and ReDoc
- **Containerization**: Docker and Docker Compose

## 📦 Prerequisites

- Python 3.10 or higher
- Docker and Docker Compose (for containerized deployment)
- Git
- (Optional) AI API keys (OpenAI, Anthropic, Google, etc.)

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/open-notebook.git
cd open-notebook

# Copy example environment file
cp .env.example .env

# Update .env with your API keys and settings
# nano .env

# Start the application
make docker-up
```

The application will be available at http://localhost:8000

### Option 2: Local Development

```bash
# Clone the repository
git clone https://github.com/yourusername/open-notebook.git
cd open-notebook

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .[dev]

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Initialize the database
docker-compose up -d surrealdb

# Run database migrations
alembic upgrade head

# Start the development server
uvicorn src.main:app --reload
```

## 🔍 API Documentation

Once the application is running, you can access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 📚 Core Concepts

### Notebooks
Organize your content in notebooks. Each notebook can contain:
- Notes (text content)
- Sources (documents, web pages, etc.)
- Chat sessions
- Media files

### Notes
Rich text notes with support for:
- Markdown formatting
- Code blocks
- Embedded media
- AI-generated content

### Sources
Import and process various content types:
- Text documents
- Web pages
- Podcasts (audio processing)
- PDFs and other document formats

### AI Features
- **Chat with Context**: Have conversations about your content with AI
- **Automatic Summarization**: Generate summaries of long documents
- **Content Generation**: Create new content based on your notes
- **Semantic Search**: Find relevant content using natural language

## 🔧 Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# Application
DEBUG=true
ENVIRONMENT=development

# Database (SurrealDB)
SURREAL_ADDRESS=localhost
SURREAL_PORT=8000
SURREAL_USER=root
SURREAL_PASS=root
SURREAL_NAMESPACE=fastapi_backend
SURREAL_DATABASE=staging

# AI Providers (at least one required)
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
GOOGLE_API_KEY=your_google_api_key

# Optional Settings
LOG_LEVEL=INFO
DATA_FOLDER=./data
```

## 🧪 Testing

Run the test suite:

```bash
# Install test dependencies
pip install -e .[test]

# Run tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=term-missing
```

## 🛠️ Model Configuration

The application uses the following models for different tasks:

### 1. Language Models
- **Provider**: TheAlpha
- **Model**: `openaigpt-41-mini`
- **Used For**: Chat, text generation, transformation, and tools
- **Base URL**: `https://thealpha.dev/api`
- **Environment Variable**: `THEALPHA_API_KEY`

### 2. Embedding Model
- **Provider**: OpenAI
- **Model**: `text-embedding-3-small`
- **Used For**: Text embeddings and similarity search
- **Environment Variable**: `OPENAI_API_KEY`

### 3. Text-to-Speech (TTS)
- **Provider**: OpenAI
- **Model**: `tts-1`
- **Used For**: Converting text to speech
- **Environment Variable**: `OPENAI_API_KEY`

### 4. Speech-to-Text (STT)
- **Provider**: OpenAI
- **Model**: `whisper-1`
- **Used For**: Converting speech to text
- **Environment Variable**: `OPENAI_API_KEY`

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with ❤️ using FastAPI and SurrealDB
- Powered by cutting-edge AI models from OpenAI, Anthropic, and Google
- Inspired by modern knowledge management tools like Notion and Obsidian
SERPER_API_KEY=your_key_here
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request
