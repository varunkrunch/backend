#!/bin/bash

# Open Notebook FastAPI Backend Setup Script
# This script sets up the backend environment with all necessary dependencies

set -e  # Exit on any error

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

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if Python is installed with minimum version
check_python() {
    print_info "Checking Python installation..."
    if command_exists python3; then
        PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
        PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
        PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
        
        if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 8 ]; then
            print_status "Python $PYTHON_VERSION found (meets minimum requirement 3.8+)"
        else
            print_error "Python 3.8+ is required. Found Python $PYTHON_VERSION"
            exit 1
        fi
    else
        print_error "Python 3 is not installed. Please install Python 3.8+ first."
        exit 1
    fi
}

# Check if pip is installed
check_pip() {
    print_info "Checking pip installation..."
    if command_exists pip3; then
        PIP_VERSION=$(pip3 --version | awk '{print $2}')
        print_status "pip $PIP_VERSION found"
    else
        print_error "pip is not installed. Please install pip first."
        exit 1
    fi
}

# Check if Docker is installed and running
check_docker() {
    print_info "Checking Docker installation..."
    if command_exists docker; then
        if docker info > /dev/null 2>&1; then
            DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
            print_status "Docker $DOCKER_VERSION is running"
        else
            print_error "Docker is not running. Please start Docker daemon."
            exit 1
        fi
    else
        print_warning "Docker is not installed. Some features may not work without Docker."
        return 1
    fi
    return 0
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

    # Activate virtual environment
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        print_status "Virtual environment activated"
    else
        print_error "Failed to activate virtual environment"
        exit 1
    fi
}

# Install Python dependencies
install_dependencies() {
    print_info "Installing Python dependencies..."
    
    # Upgrade pip first
    pip install --upgrade pip
    
    # Install build dependencies
    pip install setuptools wheel
    
    # Install the package in development mode
    if [ -f "pyproject.toml" ]; then
        pip install -e ".[dev]"
        print_status "Installed development dependencies"
    else
        print_error "pyproject.toml not found. Cannot install dependencies."
        exit 1
    fi
}

# Create .env file if it doesn't exist
setup_environment() {
    print_info "Setting up environment..."
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_status "Created .env file from .env.example"
            print_warning "Please edit the .env file with your configuration"
        else
            print_warning "No .env.example file found. Creating a basic .env file..."
            cat > .env <<EOL
# Database Configuration
SURREAL_ADDRESS=localhost
SURREAL_PORT=8000
SURREAL_USER=root
SURREAL_PASS=root
SURREAL_NAMESPACE=fastapi_backend
SURREAL_DATABASE=staging

# Application Settings
DATA_FOLDER=./data
LOG_LEVEL=INFO

# API Keys (uncomment and set as needed)
# OPENAI_API_KEY=your_openai_api_key
# ANTHROPIC_API_KEY=your_anthropic_api_key
# GROQ_API_KEY=your_groq_api_key
# MISTRAL_API_KEY=your_mistral_api_key
# GOOGLE_API_KEY=your_google_api_key
# VERTEXAI_PROJECT=your_vertexai_project
# VERTEXAI_LOCATION=your_vertexai_location
EOL
            print_status "Created .env file with default settings"
            print_warning "Please edit the .env file with your configuration"
        fi
    else
        print_status ".env file already exists"
    fi
}

# Create necessary directories
create_directories() {
    print_info "Creating data directories..."
    
    # Create data directory if it doesn't exist
    mkdir -p data/podcasts/audio
    mkdir -p data/uploads
    mkdir -p data/logs
    
    # Set proper permissions
    chmod -R 755 data
    
    print_status "Created data directory structure"
}

# Start SurrealDB with Docker
start_surrealdb() {
    if command_exists docker; then
        print_info "Checking if SurrealDB container is running..."
        
        if ! docker ps --format '{{.Names}}' | grep -q 'surrealdb'; then
            print_info "Starting SurrealDB container..."
            
            # Stop and remove existing container if it exists
            if docker ps -a --format '{{.Names}}' | grep -q 'surrealdb'; then
                docker stop surrealdb > /dev/null
                docker rm surrealdb > /dev/null
            fi
            
            # Start new container
            docker run -d \
                --name surrealdb \
                -p 8000:8000 \
                -v "$(pwd)/data/surrealdb:/data" \
                surrealdb/surrealdb:latest \
                start --log trace --user root --pass root \
                --auth --allow-scripting \
                file:///data/db
                
            # Wait for SurrealDB to start
            sleep 5
            
            # Initialize the database
            if [ -f "scripts/init.surql" ]; then
                print_info "Initializing SurrealDB database..."
                docker cp scripts/init.surql surrealdb:/init.surql
                docker exec -it surrealdb surrealdb import --conn http://localhost:8000 --user root --pass root --ns fastapi_backend --db staging /init.surql
            fi
            
            print_status "SurrealDB container started"
        else
            print_status "SurrealDB container is already running"
        fi
    else
        print_warning "Docker not found. Please install Docker to use SurrealDB."
    fi
}

# Run database migrations
run_migrations() {
    print_info "Running database migrations..."
    
    if [ -f "scripts/migrate.py" ]; then
        python scripts/migrate.py
        print_status "Database migrations completed"
    else
        print_warning "No migration scripts found. Skipping database migrations."
    fi
}

# Run tests
run_tests() {
    print_info "Running tests..."
    
    if command_exists pytest; then
        python -m pytest tests/ -v
    else
        print_warning "pytest not found. Skipping tests."
        print_info "Install test dependencies with: pip install -e \".[dev]\""
    fi
}

# Main setup function
main() {
    echo -e "\n${BLUE}🚀 Setting up Open Notebook FastAPI Backend...${NC}"
    echo -e "${BLUE}==============================================${NC}\n"
    
    # Check system requirements
    check_python
    check_pip
    check_docker
    
    # Setup environment
    setup_venv
    install_dependencies
    setup_environment
    create_directories
    
    # Start services
    start_surrealdb
    
    # Run migrations and tests
    run_migrations
    run_tests
    
    echo -e "\n${GREEN}✅ Setup completed successfully!${NC}"
    echo -e "\nTo start the application, run:\n"
    echo -e "  ${BLUE}source venv/bin/activate${NC}"
    echo -e "  ${BLUE}python -m uvicorn src.main:app --reload${NC}\n"
    echo -e "Then open your browser to: ${BLUE}http://localhost:8000${NC}"
    echo -e "API documentation: ${BLUE}http://localhost:8000/docs${NC}\n"
}

# Run main function
main "$@"
