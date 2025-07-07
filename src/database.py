# /home/ubuntu/open_notebook_full_backend/fastapi_backend/src/database.py

import os
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from surrealdb import AsyncSurreal

# Load environment variables from .env file
# Try multiple possible locations for the .env file
env_paths = [
    Path(__file__).parent.parent / '.env',  # fastapi_backend/.env
    Path(__file__).parent.parent.parent / '.env',  # project root .env
    Path.cwd() / '.env',  # current working directory .env
]

for env_path in env_paths:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        print(f"Loaded environment from {env_path}")
        break

# Use the same variables as Streamlit
SURREAL_ADDRESS = os.getenv("SURREAL_ADDRESS", "localhost")
SURREAL_PORT = int(os.getenv("SURREAL_PORT", "8000"))
SURREAL_USER = os.getenv("SURREAL_USER", "root")
SURREAL_PASS = os.getenv("SURREAL_PASS", "root")
SURREAL_NAMESPACE = os.getenv("SURREAL_NAMESPACE", "open_notebook")
SURREAL_DATABASE = os.getenv("SURREAL_DATABASE", "staging")

# Use WebSocket URL for SurrealDB
SURREAL_URL = f"ws://{SURREAL_ADDRESS}:{SURREAL_PORT}/rpc"

db: Optional[AsyncSurreal] = None

async def connect_db():
    """Establishes the SurrealDB connection during application startup."""
    global db
    if db is None:
        print(f"Attempting to connect to SurrealDB at {SURREAL_URL}...")
        try:
            db = AsyncSurreal(SURREAL_URL)
            await db.signin({"username": SURREAL_USER, "password": SURREAL_PASS})
            await db.use(SURREAL_NAMESPACE, SURREAL_DATABASE)
            # Test query with proper SurrealQL syntax
            try:
                result = await db.query("SELECT * FROM notebook LIMIT 1")
                print(f"Successfully connected to SurrealDB! Namespace: {SURREAL_NAMESPACE}, Database: {SURREAL_DATABASE}")
            except Exception as query_error:
                print(f"Warning: Connection established but query test failed: {query_error}")
        except Exception as e:
            print(f"FATAL: Failed to connect to SurrealDB during startup: {e}")
            db = None
            raise HTTPException(
                status_code=503,
                detail=f"Database connection failed: {str(e)}"
            )

async def close_db():
    """Close the database connection."""
    global db
    if db is not None:
        try:
            await db.close()
        except NotImplementedError:
            pass
        except Exception as e:
            print(f"Error closing database connection: {e}")
        finally:
            db = None

async def get_db_connection() -> AsyncSurreal:
    """FastAPI dependency function to get the active SurrealDB connection."""
    global db
    if db is None:
        try:
            await connect_db()
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail="Database connection is not available. Please try again later."
            )
    # Verify connection is still alive using a simple query with proper syntax
    try:
        # Use a simple query that should work with any SurrealDB version
        await db.query("SELECT * FROM notebook LIMIT 1")
    except Exception as e:
        print(f"Database connection lost, attempting to reconnect: {e}")
        try:
            await connect_db()
        except Exception as reconnect_error:
            raise HTTPException(
                status_code=503,
                detail="Database connection lost and reconnect failed. Please try again later."
            )
    return db

