# FastAPI Backend Testing Guide

This guide will help Mir set up and test the Open Notebook FastAPI backend on his computer.

## 📋 Prerequisites

Before starting, ensure you have the following installed:

- **Python 3.8+** (recommended: Python 3.11 or 3.12)
- **Git** (to clone the repository)
- **SurrealDB** (database server)
- **API Keys** for AI services (OpenAI, Anthropic, Google, etc.)

## 🚀 Quick Setup

### 1. Clone the Repository
```bash
git clone https://github.com/22PA1A45B4/backend.git
cd backend
```

### 2. Install SurrealDB

#### Option A: Using Docker (Recommended)
```bash
# Pull and run SurrealDB
docker run --name surrealdb -p 8000:8000 -d surrealdb/surrealdb:latest start --log trace --user root --pass root memory
```

#### Option B: Direct Installation
```bash
# On macOS
brew install surrealdb/tap/surrealdb

# On Ubuntu/Debian
curl -sSf https://install.surrealdb.com | sh

# Start SurrealDB
surrealdb start --log trace --user root --pass root memory
```

### 3. Set Up Python Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements-backend.txt
```

### 4. Environment Configuration

Create a `.env` file in the `fastapi_backend` directory:

```bash
# Database Configuration
SURREAL_ADDRESS=localhost
SURREAL_PORT=8000
SURREAL_USER=root
SURREAL_PASS=root
SURREAL_NAMESPACE=fastapi_backend
SURREAL_DATABASE=main

# FastAPI Configuration
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8001
FASTAPI_RELOAD=true
FASTAPI_LOG_LEVEL=info
FASTAPI_WORKERS=1

# Data Folder
DATA_FOLDER=./data

# AI Service API Keys (Add your keys here)
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_API_KEY=your_google_api_key_here

# Serper API (for Google Search)
SERPER_API_KEY=your_serper_api_key_here
```

### 5. Initialize Database

```bash
# Run database migrations (if any)
# The application will automatically create necessary tables on first run
```

## 🏃‍♂️ Running the Application

### Start the Backend Server

```bash
# From the fastapi_backend directory
python run.py
```

The server will start on `http://localhost:8001` by default.

### Verify Installation

1. **Health Check**: Visit `http://localhost:8001/health`
2. **API Documentation**: Visit `http://localhost:8001/docs` (Swagger UI)
3. **Alternative Docs**: Visit `http://localhost:8001/redoc`

## 🧪 Testing the API

### 1. Basic Health Check

```bash
curl http://localhost:8001/health
```

Expected response:
```json
{"status": "healthy", "message": "Open Notebook Backend API is running"}
```

### 2. Test Notebook Endpoints

#### Create a Notebook
```bash
curl -X POST "http://localhost:8001/api/v1/notebooks" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Notebook",
    "description": "A test notebook for API testing"
  }'
```

#### List Notebooks
```bash
curl http://localhost:8001/api/v1/notebooks
```

#### Get Notebook by Name
```bash
curl "http://localhost:8001/api/v1/notebooks/by-name/Test%20Notebook"
```

### 3. Test Source Upload

```bash
# Create a test file
echo "This is a test document for API testing" > test_document.txt

# Upload the file as a source
curl -X POST "http://localhost:8001/api/v1/notebooks/by-name/Test%20Notebook/sources" \
  -F "file=@test_document.txt" \
  -F "title=Test Document"
```

### 4. Test Notes Creation

```bash
curl -X POST "http://localhost:8001/api/v1/notebooks/by-name/Test%20Notebook/notes" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Note",
    "content": "This is a test note created via API"
  }'
```

### 5. Test Chat Functionality

```bash
curl -X POST "http://localhost:8001/api/v1/chat/message?notebook_id=Test%20Notebook" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, can you help me understand this notebook?",
    "context_config": {}
  }'
```

### 6. Test Search

```bash
curl "http://localhost:8001/api/v1/search?q=test&notebook_id=Test%20Notebook"
```

## 🔧 Advanced Testing

### 1. Run Automated Tests

The project includes several test files:

```bash
# Test GPT endpoints
python test_gptr_endpoint.py

# Test Serper (Google Search) endpoints
python test_serper_endpoint.py

# Test note endpoints
python test_note_endpoints.py

# Test models integration
python test_models_integration.py
```

### 2. Test with Frontend

If you have the frontend running:

1. Start the frontend on `http://localhost:3000`
2. Ensure the frontend is configured to connect to `http://localhost:8001`
3. Test the full integration

### 3. Load Testing

```bash
# Install Apache Bench (if not installed)
# On macOS: brew install httpd
# On Ubuntu: sudo apt-get install apache2-utils

# Test with multiple requests
ab -n 100 -c 10 http://localhost:8001/health
```

## 🐛 Troubleshooting

### Common Issues

#### 1. SurrealDB Connection Error
```
Error: Could not connect to SurrealDB
```
**Solution**: Ensure SurrealDB is running on port 8000
```bash
# Check if SurrealDB is running
curl http://localhost:8000/health
```

#### 2. Port Already in Use
```
Error: [Errno 48] Address already in use
```
**Solution**: Change the port in `.env` file or kill the process using the port
```bash
# Find process using port 8001
lsof -i :8001
# Kill the process
kill -9 <PID>
```

#### 3. Missing API Keys
```
Error: API key not found
```
**Solution**: Add your API keys to the `.env` file

#### 4. Import Errors
```
ModuleNotFoundError: No module named 'fastapi'
```
**Solution**: Ensure virtual environment is activated and dependencies are installed
```bash
source venv/bin/activate
pip install -r requirements-backend.txt
```

### Debug Mode

To run in debug mode with more verbose logging:

```bash
# Set debug environment variables
export FASTAPI_LOG_LEVEL=debug
export FASTAPI_RELOAD=true

# Run the application
python run.py
```

## 📊 Monitoring and Logs

### View Logs
The application logs are displayed in the console. For production, consider using:
- **Loguru** (already included in requirements)
- **Docker logs** (if running in Docker)
- **System logs** (journalctl on Linux)

### Performance Monitoring
- Use the `/health` endpoint for basic health checks
- Monitor memory usage with `htop` or `top`
- Check database performance with SurrealDB metrics

## 🔄 Development Workflow

### Making Changes
1. Make your code changes
2. The server will auto-reload (if `FASTAPI_RELOAD=true`)
3. Test your changes using the API endpoints
4. Run the test suite to ensure nothing is broken

### Adding New Endpoints
1. Create new router in `src/routers/`
2. Import and include in `src/main.py`
3. Add tests in the `test/` directory
4. Update this documentation

## 📚 API Documentation

Once the server is running, visit:
- **Swagger UI**: `http://localhost:8001/docs`
- **ReDoc**: `http://localhost:8001/redoc`

These provide interactive documentation for all available endpoints.

## 🆘 Getting Help

If you encounter issues:

1. Check the logs for error messages
2. Verify all prerequisites are installed
3. Ensure all environment variables are set correctly
4. Test individual components (database, API keys, etc.)
5. Check the GitHub repository for issues and solutions

## 🎯 Success Criteria

Your setup is successful when:
- ✅ Server starts without errors
- ✅ Health check returns 200 OK
- ✅ API documentation loads correctly
- ✅ You can create notebooks, sources, and notes
- ✅ Chat functionality works (if API keys are configured)
- ✅ All test files pass

Happy testing! 🚀
