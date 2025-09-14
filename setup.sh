#!/bin/bash

# Open Notebook FastAPI Backend Setup Script
# This script helps Mir set up the backend for testing

set -e  # Exit on any error

echo "🚀 Setting up Open Notebook FastAPI Backend..."
echo "=============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if Python is installed
check_python() {
    print_info "Checking Python installation..."
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        print_status "Python $PYTHON_VERSION found"
    else
        print_error "Python 3 is not installed. Please install Python 3.8+ first."
        exit 1
    fi
}

# Check if pip is installed
check_pip() {
    print_info "Checking pip installation..."
    if command -v pip3 &> /dev/null; then
        print_status "pip3 found"
    else
        print_error "pip3 is not installed. Please install pip first."
        exit 1
    fi
}

# Check if Docker is installed (for SurrealDB)
check_docker() {
    print_info "Checking Docker installation..."
    if command -v docker &> /dev/null; then
        print_status "Docker found"
        return 0
    else
        print_warning "Docker not found. You'll need to install SurrealDB manually."
        return 1
    fi
}

# Create virtual environment
setup_venv() {
    print_info "Setting up Python virtual environment..."
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_status "Virtual environment created"
    else
        print_status "Virtual environment already exists"
    fi
    
    print_info "Activating virtual environment..."
    source venv/bin/activate
    print_status "Virtual environment activated"
}

# Install dependencies
install_dependencies() {
    print_info "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements-backend.txt
    print_status "Dependencies installed successfully"
}

# Start SurrealDB with Docker
start_surrealdb() {
    print_info "Starting SurrealDB with Docker..."
    if check_docker; then
        # Check if SurrealDB container is already running
        if docker ps | grep -q surrealdb; then
            print_status "SurrealDB is already running"
        else
            # Start SurrealDB container
            docker run --name surrealdb -p 8000:8000 -d surrealdb/surrealdb:latest start --log trace --user root --pass root memory
            print_status "SurrealDB started successfully"
        fi
    else
        print_warning "Please install and start SurrealDB manually:"
        echo "  brew install surrealdb/tap/surrealdb  # On macOS"
        echo "  curl -sSf https://install.surrealdb.com | sh  # On Linux"
        echo "  surrealdb start --log trace --user root --pass root memory"
    fi
}

# Create .env file if it doesn't exist
create_env_file() {
    print_info "Setting up environment configuration..."
    if [ ! -f ".env" ]; then
        cat > .env << EOF
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
EOF
        print_status ".env file created with default configuration"
        print_warning "Please update the API keys in .env file with your actual keys"
    else
        print_status ".env file already exists"
    fi
}

# Create data directories
create_data_dirs() {
    print_info "Creating data directories..."
    mkdir -p data/podcasts/audio
    mkdir -p data/podcasts/transcripts
    mkdir -p data/uploads
    mkdir -p data/sqlite-db
    print_status "Data directories created"
}

# Test the setup
test_setup() {
    print_info "Testing the setup..."
    
    # Test SurrealDB connection
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        print_status "SurrealDB is responding"
    else
        print_warning "SurrealDB is not responding. Please check if it's running."
    fi
    
    # Test Python imports
    if python -c "import fastapi, uvicorn, surrealdb" 2>/dev/null; then
        print_status "Python dependencies are working"
    else
        print_error "Python dependencies are not working properly"
        exit 1
    fi
}

# Main setup function
main() {
    echo "Starting setup process..."
    echo ""
    
    check_python
    check_pip
    setup_venv
    install_dependencies
    start_surrealdb
    create_env_file
    create_data_dirs
    test_setup
    
    echo ""
    echo "🎉 Setup completed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Update your API keys in the .env file"
    echo "2. Run the server: python run.py"
    echo "3. Visit http://localhost:8001/docs for API documentation"
    echo "4. Check TESTING_GUIDE.md for detailed testing instructions"
    echo ""
    echo "To start the server:"
    echo "  source venv/bin/activate"
    echo "  python run.py"
    echo ""
}

# Run main function
main "$@"
