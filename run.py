import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    # Get configuration from environment variables with defaults
    host = os.getenv("FASTAPI_HOST", "0.0.0.0")
    port = int(os.getenv("FASTAPI_PORT", "8000"))
    reload = os.getenv("FASTAPI_RELOAD", "true").lower() == "true"
    
    # Configure logging
    log_level = os.getenv("FASTAPI_LOG_LEVEL", "info")
    
    print(f"Starting Open Notebook Backend API server...")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Auto-reload: {reload}")
    print(f"Log level: {log_level}")
    print(f"API documentation available at: http://{host}:{port}/docs")
    
    # Run the server
    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
        workers=int(os.getenv("FASTAPI_WORKERS", "1"))
    )

if __name__ == "__main__":
    main() 