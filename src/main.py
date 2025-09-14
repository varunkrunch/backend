# FastAPI Backend Main Application
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
import os

from .database import connect_db, close_db, SURREAL_URL, SURREAL_NAMESPACE, SURREAL_DATABASE
from .routers import notebooks, notes, sources, podcasts, search, models, transformations, chat, serper

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    print("Application startup...")
    await connect_db() # Establish DB connection
    yield
    # Code to run on shutdown
    print("Application shutdown...")
    await close_db() # Close DB connection

# Create the FastAPI app instance with lifespan management
app = FastAPI(
    title="Open Notebook Backend API",
    description="API providing backend functionality for the Open Notebook application, mirroring Streamlit UI features.",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Mount static files for podcasts audio
data_folder = os.getenv("DATA_FOLDER", "./data")
podcast_audio_path = os.path.join(data_folder, "podcasts", "audio")
if os.path.exists(podcast_audio_path):
    app.mount("/data/podcasts/audio", StaticFiles(directory=podcast_audio_path), name="podcast_audio")
    print(f"Mounted podcast audio directory: {podcast_audio_path}")
else:
    print(f"Warning: Podcast audio directory not found at {podcast_audio_path}. Creating directory...")
    os.makedirs(podcast_audio_path, exist_ok=True)
    app.mount("/data/podcasts/audio", StaticFiles(directory=podcast_audio_path), name="podcast_audio")
    print(f"Created and mounted podcast audio directory: {podcast_audio_path}")

# Include routers from different modules
app.include_router(notebooks.router)
app.include_router(notes.router)
app.include_router(sources.router)
app.include_router(podcasts.router)
app.include_router(search.router)
app.include_router(models.router)
app.include_router(transformations.router)
app.include_router(chat.router)
app.include_router(serper.router)


# Simple root endpoint for health check / info
@app.get("/")
async def read_root():
    return {
        "message": "Welcome to the Open Notebook Backend API!",
        "database_status": f"Connected to {SURREAL_URL} (NS: {SURREAL_NAMESPACE}, DB: {SURREAL_DATABASE})",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json"
    }

# Placeholder for task status endpoint (if needed globally)
# @app.get("/api/v1/tasks/{task_id}", tags=["Tasks"])
# async def get_task_status(task_id: str):
#     # Logic to check task status from a background task queue (e.g., Celery, ARQ)
#     return {"task_id": task_id, "status": "unknown"}

print("FastAPI application instance created.")

