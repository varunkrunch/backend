# Standard library imports
from datetime import datetime
import os
import aiofiles
from typing import List, Optional, Dict, Any, Union
import json
import ast

# Third-party imports
from fastapi import (
    APIRouter, Depends, HTTPException, status, Query, Response
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, validator
from loguru import logger
from dotenv import load_dotenv
from surrealdb import AsyncSurreal
from dateutil import parser

# Local imports
from ..database import get_db_connection
from ..models import StatusResponse
from open_notebook.domain.models import Model
from open_notebook.plugins.podcasts import PodcastEpisode, PodcastConfig
from .models import conversation_styles, dialogue_structures, engagement_techniques, participant_roles
from open_notebook.domain.notebook import Note, Source

# Constants
DATA_FOLDER = os.getenv("DATA_FOLDER", "./data")
AUDIO_FORMAT = "audio/mpeg"

# Load environment variables
load_dotenv()

# Database constants
PODCAST_CONFIG_TABLE = "podcast_config"
PODCAST_EPISODE_TABLE = "podcast_episode"

# Required API keys
REQUIRED_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "vertexai": "GOOGLE_APPLICATION_CREDENTIALS"
}

async def get_notebook_content(db: AsyncSurreal, notebook_id: str) -> tuple[str, list[str]]:
    """Get content from a notebook."""
    try:
        notebook = await db.select("notebook", notebook_id)
        if not notebook:
            return "", [f"Notebook {notebook_id} not found"]
            
        # Get the content field from the notebook
        content = notebook.get('content', '')
        if not content:
            return "", [f"Notebook {notebook_id} has no content"]
            
        return content, []
    except Exception as e:
        logger.error(f"Error getting notebook content: {e}")
        return "", [f"Error retrieving notebook content: {str(e)}"]

def check_api_keys(provider: str, transcript_provider: Optional[str] = None) -> None:
    """Check if required API keys are present for the selected providers."""
    providers_to_check = [provider]
    if transcript_provider:
        providers_to_check.append(transcript_provider)
    
    missing_keys = []
    for p in providers_to_check:
        key_name = REQUIRED_API_KEYS.get(p)
        if key_name and not os.getenv(key_name):
            missing_keys.append(f"{p} ({key_name})")
    
    if missing_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required API keys for: {', '.join(missing_keys)}"
        )

def convert_record_id_to_string(data: Any) -> Any:
    """Convert SurrealDB RecordID objects to strings in the response data."""
    if isinstance(data, dict):
        return {k: convert_record_id_to_string(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_record_id_to_string(item) for item in data]
    elif str(type(data)).endswith("RecordID"):
        try:
            if hasattr(data, 'table_name') and hasattr(data, 'id'):
                return f"{data.table_name}:{data.id}"
            return str(data)
        except Exception as e:
            logger.error(f"Error converting RecordID: {e}")
            return str(data)
    return data

# Pydantic models
class PodcastTemplateResponse(PodcastConfig):
    model_config = ConfigDict(from_attributes=True)
    
    @field_validator("person1_role", "person2_role", "conversation_style", "engagement_technique", "dialogue_structure", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [item.strip() for item in v.split(',') if item.strip()]
        if not isinstance(v, list):
            return [str(v)]
        return [str(item) for item in v if item is not None]

    @field_validator("voice1", "voice2")
    @classmethod
    def validate_voice(cls, v: str) -> str:
        if not v:
            raise ValueError("Voice cannot be empty")
        return v

class PodcastEpisodeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    name: Optional[str] = None
    template: str
    template_name: Optional[str] = None
    notebook_name: Optional[str] = None
    created: datetime
    status: str = "pending"
    instructions: Optional[str] = None
    text: Optional[str] = None
    audio_url: Optional[str] = None
    audio_file: Optional[str] = None
    duration: Optional[float] = None

class PodcastGenerateRequest(BaseModel):
    template_name: str
    notebook_name: str
    episode_name: Optional[str] = None
    instructions: Optional[str] = None
    podcast_length: str = Field(
        default="Medium (10-20 min)",
        description="Length of podcast: 'Short (5-10 min)', 'Medium (10-20 min)', or 'Longer (20+ min)'"
    )

class PodcastGenerateResponse(BaseModel):
    status: str
    message: str
    warnings: List[str] = []

class StatusResponse(BaseModel):
    status: str
    message: str
    episodes: Optional[List[Dict[str, Any]]] = None

# Create router
router = APIRouter(prefix="/api/v1/podcasts", tags=["Podcasts"])

# Essential endpoints only
@router.get("/episodes/by-notebook/{notebook_name}", response_model=List[PodcastEpisodeSummary])
async def list_podcast_episodes_by_notebook(
    notebook_name: str,
    db: AsyncSurreal = Depends(get_db_connection)
) -> List[PodcastEpisodeSummary]:
    """List podcast episodes for a specific notebook by name."""
    try:
        logger.info(f"Fetching podcast episodes for notebook: {notebook_name}")
        
        # First, find the notebook by name
        notebook_query = "SELECT id FROM notebook WHERE name = $name"
        notebook_result = await db.query(notebook_query, {"name": notebook_name})
        
        if not notebook_result or len(notebook_result) == 0:
            logger.warning(f"Notebook '{notebook_name}' not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Notebook '{notebook_name}' not found"
            )
        
        notebook_data = notebook_result[0]
        if isinstance(notebook_data, list) and len(notebook_data) > 0:
            notebook_data = notebook_data[0]
        
        notebook_id = notebook_data.get('id')
        if not notebook_id:
            logger.error(f"No ID found for notebook '{notebook_name}'")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"No ID found for notebook '{notebook_name}'"
            )
        
        logger.info(f"Found notebook ID: {notebook_id}")
        
        # First, let's debug by checking what episodes exist and their structure
        logger.info(f"Debugging: Looking for episodes with notebook_id: {notebook_id}")
        
        # Try multiple query approaches to find episodes
        queries_to_try = [
            # Query 1: Direct content_source.id match (most likely to work)
            (f"SELECT * FROM {PODCAST_EPISODE_TABLE} WHERE content_source.id = $notebook_id", 
             {"notebook_id": notebook_id}, "content_source.id match"),
            
            # Query 2: Check if content_source is an object with id field
            (f"SELECT * FROM {PODCAST_EPISODE_TABLE} WHERE content_source->id = $notebook_id", 
             {"notebook_id": notebook_id}, "content_source->id match"),
            
            # Query 3: Check if content_source is just the ID string
            (f"SELECT * FROM {PODCAST_EPISODE_TABLE} WHERE content_source = $notebook_id", 
             {"notebook_id": notebook_id}, "content_source direct match"),
            
            # Query 4: Get all episodes to see their structure
            (f"SELECT * FROM {PODCAST_EPISODE_TABLE}", 
             {}, "all episodes for debugging")
        ]
        
        episodes_result = None
        used_query = None
        
        for query, params, description in queries_to_try:
            try:
                logger.info(f"Trying query: {description}")
                logger.info(f"Query: {query}")
                logger.info(f"Params: {params}")
                
                result = await db.query(query, params)
                logger.info(f"Query result: {result}")
                
                if result and len(result) > 0:
                    episodes_result = result
                    used_query = description
                    logger.info(f"Found episodes using: {description}")
                    break
                    
            except Exception as e:
                logger.warning(f"Query failed ({description}): {e}")
                continue
        
        if not episodes_result:
            logger.warning("No episodes found with any query approach")
            return []
        
        if not episodes_result:
            logger.info(f"No episodes found for notebook '{notebook_name}'")
            return []
        
        # Debug: Log the structure of found episodes
        logger.info(f"Found {len(episodes_result)} episode records using query: {used_query}")
        for i, ep in enumerate(episodes_result):
            logger.info(f"Episode {i}: {ep} (type: {type(ep)})")
        
        episodes = []
        for ep in episodes_result:
            if isinstance(ep, list) and len(ep) > 0:
                ep = ep[0]
            
            ep_dict = ep.model_dump() if hasattr(ep, 'model_dump') else dict(ep)
            
            # Debug: Log the content_source structure
            content_source = ep_dict.get('content_source', {})
            logger.info(f"Episode content_source: {content_source} (type: {type(content_source)})")
            
            # Check if this episode belongs to our notebook
            episode_notebook_id = None
            if isinstance(content_source, dict):
                episode_notebook_id = content_source.get('id')
            elif isinstance(content_source, str):
                episode_notebook_id = content_source
            
            logger.info(f"Episode notebook ID: {episode_notebook_id}, Looking for: {notebook_id}")
            
            # Only include episodes that match our notebook
            if str(episode_notebook_id) != str(notebook_id):
                logger.info(f"Skipping episode - notebook ID mismatch")
                continue
            
            # Convert IDs to strings
            if hasattr(ep_dict.get('id', None), 'table_name') and hasattr(ep_dict.get('id', None), 'id'):
                ep_dict['id'] = f"{ep_dict['id'].table_name}:{ep_dict['id'].id}"
            elif ep_dict.get('id', None) is not None:
                ep_dict['id'] = str(ep_dict['id'])
            
            if hasattr(ep_dict.get('template', None), 'table_name') and hasattr(ep_dict.get('template', None), 'id'):
                ep_dict['template'] = f"{ep_dict['template'].table_name}:{ep_dict['template'].id}"
            elif ep_dict.get('template', None) is not None:
                ep_dict['template'] = str(ep_dict['template'])
            else:
                ep_dict['template'] = ""
            
            # Get template name
            template_id = ep_dict.get('template')
            if template_id:
                if hasattr(template_id, 'table_name') and hasattr(template_id, 'id'):
                    template_id = f"{template_id.table_name}:{template_id.id}"
                
                template_query = f"SELECT name FROM {PODCAST_CONFIG_TABLE} WHERE id = $id"
                template_result = await db.query(template_query, {"id": template_id})
                if template_result and len(template_result) > 0 and len(template_result[0]) > 0:
                    ep_dict['template_name'] = template_result[0].get('name')
            
            # Set notebook name
            ep_dict['notebook_name'] = notebook_name
            
            # Ensure all required fields exist
            if 'created' not in ep_dict or not ep_dict['created']:
                ep_dict['created'] = datetime.now()
            
            # Add default values for optional fields if missing
            if 'name' not in ep_dict:
                ep_dict['name'] = None
            if 'template_name' not in ep_dict:
                ep_dict['template_name'] = None
            if 'status' not in ep_dict:
                ep_dict['status'] = "pending"
            if 'instructions' not in ep_dict:
                ep_dict['instructions'] = None
            if 'text' not in ep_dict:
                ep_dict['text'] = None
            if 'audio_url' not in ep_dict:
                ep_dict['audio_url'] = None
            if 'audio_file' not in ep_dict:
                ep_dict['audio_file'] = None
            if 'duration' not in ep_dict:
                ep_dict['duration'] = None
            
            # Create a valid PodcastEpisodeSummary object
            try:
                episode_summary = PodcastEpisodeSummary(**ep_dict)
                episodes.append(episode_summary.model_dump())
            except Exception as e:
                logger.error(f"Error creating episode summary: {e}")
                logger.error(f"Episode data: {ep_dict}")
                continue
        
        logger.info(f"Found {len(episodes)} episodes for notebook '{notebook_name}'")
        return episodes
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing podcast episodes for notebook '{notebook_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing podcast episodes for notebook '{notebook_name}': {str(e)}"
        )

@router.get("/episodes", response_model=List[PodcastEpisodeSummary])
async def list_podcast_episodes(
    db: AsyncSurreal = Depends(get_db_connection),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
) -> List[PodcastEpisodeSummary]:
    """Lists all generated podcast episodes."""
    try:
        query = f"SELECT * FROM {PODCAST_EPISODE_TABLE} ORDER BY created DESC"
        result = await db.query(query)
        
        episodes = []
        for ep in (result if result is not None else []):
            ep_dict = ep.model_dump() if hasattr(ep, 'model_dump') else dict(ep)
            
            # Convert IDs to strings
            if hasattr(ep_dict.get('id', None), 'table_name') and hasattr(ep_dict.get('id', None), 'id'):
                ep_dict['id'] = f"{ep_dict['id'].table_name}:{ep_dict['id'].id}"
            elif ep_dict.get('id', None) is not None:
                ep_dict['id'] = str(ep_dict['id'])
            
            if hasattr(ep_dict.get('template', None), 'table_name') and hasattr(ep_dict.get('template', None), 'id'):
                ep_dict['template'] = f"{ep_dict['template'].table_name}:{ep_dict['template'].id}"
            elif ep_dict.get('template', None) is not None:
                ep_dict['template'] = str(ep_dict['template'])
            else:
                # Ensure template field exists (required by model)
                ep_dict['template'] = ""
            
            # Get template name
            template_id = ep_dict.get('template')
            if template_id:
                # Handle both string IDs and RecordID objects
                if hasattr(template_id, 'table_name') and hasattr(template_id, 'id'):
                    template_id = f"{template_id.table_name}:{template_id.id}"
                
                template_query = f"SELECT name FROM {PODCAST_CONFIG_TABLE} WHERE id = $id"
                template_result = await db.query(template_query, {"id": template_id})
                if template_result and len(template_result) > 0 and len(template_result[0]) > 0:
                    ep_dict['template_name'] = template_result[0].get('name')
            
            # Get notebook name
            content_source = ep_dict.get('content_source', {})
            if content_source and content_source.get('type') == 'notebook':
                notebook_id = content_source.get('id')
                if notebook_id:
                    notebook_query = "SELECT name FROM notebook WHERE id = $id"
                    notebook_result = await db.query(notebook_query, {"id": notebook_id})
                    if notebook_result and len(notebook_result) > 0:
                        ep_dict['notebook_name'] = notebook_result[0].get('name')
            
            # Ensure all required fields exist
            if 'created' not in ep_dict or not ep_dict['created']:
                ep_dict['created'] = datetime.now()
            
            # Add default values for optional fields if missing
            if 'name' not in ep_dict:
                ep_dict['name'] = None
            if 'template_name' not in ep_dict:
                ep_dict['template_name'] = None
            if 'notebook_name' not in ep_dict:
                ep_dict['notebook_name'] = None
            if 'status' not in ep_dict:
                ep_dict['status'] = "pending"
            if 'instructions' not in ep_dict:
                ep_dict['instructions'] = None
            if 'text' not in ep_dict:
                ep_dict['text'] = None
            # Ensure audio_url and audio_file are always present
            if 'audio_url' not in ep_dict:
                ep_dict['audio_url'] = None
            if 'audio_file' not in ep_dict:
                ep_dict['audio_file'] = None
            # Ensure duration is always present
            if 'duration' not in ep_dict:
                ep_dict['duration'] = None
            
            # Create a valid PodcastEpisodeSummary object to ensure all fields are present
            try:
                episode_summary = PodcastEpisodeSummary(**ep_dict)
                episodes.append(episode_summary.model_dump())
            except Exception as e:
                logger.error(f"Error creating episode summary: {e}")
                logger.error(f"Episode data: {ep_dict}")
                continue
        
        return episodes
    except Exception as e:
        logger.error(f"Error listing podcast episodes: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing podcast episodes: {str(e)}")

@router.delete("/episodes/{episode_id_or_name}", response_model=StatusResponse)
async def delete_podcast_episode(
    episode_id_or_name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Delete a podcast episode and its associated audio file.
    
    Args:
        episode_id_or_name: Either the full episode ID (e.g., 'podcast_episode:hb6f45iai6qwfbk4tppy') 
                          or just the name of the episode (e.g., 'i')
    """
    try:
        logger.info(f"Starting delete_podcast_episode for: {episode_id_or_name}")
        
        # Check if the input is a full record ID (contains ':')
        if ':' in episode_id_or_name:
            # It's a full record ID
            episode_id = episode_id_or_name
            # Get the episode by ID
            query = f"SELECT * FROM {episode_id}"
            params = {}
        else:
            # It's just a name, try to find by name
            episode_name = episode_id_or_name.strip()
            query = f"""
                SELECT * FROM {PODCAST_EPISODE_TABLE} 
                WHERE name = $name
                LIMIT 1
            """
            params = {"name": episode_id_or_name}
        
        logger.info(f"Executing query: {query} with params: {params}")
        
        # Execute the query
        result = await db.query(query, params) if params else await db.query(query)
        
        # Log the raw result for debugging
        logger.info(f"Database query result type: {type(result)}")
        if hasattr(result, '__len__'):
            logger.info(f"Result length: {len(result)}")
        logger.info(f"Raw database result: {result}")
        
        # Check if result is valid
        if not result:
            logger.warning(f"Empty result for episode: {episode_id_or_name}")
            raise HTTPException(status_code=404, detail=f"Episode '{episode_id_or_name}' not found")
        
        # Handle different possible result formats
        if isinstance(result, list):
            if not result:
                raise HTTPException(status_code=404, detail=f"No results for episode: {episode_id_or_name}")
            
            # Get the first result
            first_result = result[0]
            logger.info(f"First result type: {type(first_result)}, value: {first_result}")
            
            # Handle case where result is a list of lists
            if isinstance(first_result, list):
                if not first_result:
                    raise HTTPException(status_code=404, detail=f"Empty result set for episode: {episode_id_or_name}")
                first_row = first_result[0]
            else:
                first_row = first_result
        else:
            first_row = result
        
        if not first_row:
            raise HTTPException(status_code=404, detail=f"No data in result for episode: {episode_id_or_name}")
        
        # Get the episode data
        episode = first_row[0] if isinstance(first_row, (list, tuple)) and first_row else first_row
        if not episode or not isinstance(episode, dict):
            logger.error(f"Invalid episode data format: {episode}")
            raise HTTPException(status_code=500, detail="Invalid episode data format")
        
        # Get episode ID
        episode_id = episode.get('id')
        if not episode_id:
            logger.warning(f"No ID found in episode data: {episode}")
            raise HTTPException(status_code=404, detail=f"No ID found for episode: {episode_id_or_name}")
        
        # Convert RecordID to string if needed
        episode_id_str = str(episode_id)
        
        # Get audio file path if it exists
        audio_file_path = episode.get('audio_file')
        
        # Delete the audio file if it exists
        if audio_file_path and os.path.exists(audio_file_path):
            try:
                os.remove(audio_file_path)
                logger.info(f"Deleted audio file: {audio_file_path}")
            except Exception as e:
                logger.error(f"Error deleting audio file {audio_file_path}: {e}")
                # Continue with DB deletion even if file deletion fails
        
        # Delete the episode record
        delete_query = f"DELETE {episode_id_str}"
        logger.info(f"Executing delete query: {delete_query}")
        
        delete_result = await db.query(delete_query)
        logger.info(f"Delete result: {delete_result}")
        
        # Verify deletion
        check_query = f"SELECT * FROM {episode_id_str}"
        check_result = await db.query(check_query)
        
        if check_result and len(check_result) > 0 and len(check_result[0]) > 0:
            logger.error(f"Failed to delete episode {episode_id_str}")
            raise HTTPException(status_code=500, detail=f"Failed to delete episode {episode_id_str}")
        
        logger.info(f"Successfully deleted episode {episode_id_str}")
        return {"status": "success", "message": f"Episode {episode_id_or_name} deleted successfully"}
    
    except HTTPException as http_exc:
        logger.error(f"HTTP error in delete_podcast_episode: {http_exc.status_code}: {http_exc.detail}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in delete_podcast_episode: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")



@router.get("/episodes/{episode_identifier}/audio")
async def get_episode_audio(
    episode_identifier: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Get the audio file for a specific episode by ID or name.
    
    Parameters:
    - episode_identifier: Either the episode ID (e.g., 'podcast_episode:123') or episode name
    """
    try:
        # Get the episode using our helper function
        episode = await get_episode_by_id_or_name(episode_identifier, db)
        
        # Convert RecordID to string if needed
        episode = convert_record_id_to_string(episode)
        
        # Get the audio file path and URL
        audio_path = episode.get('audio_file')
        audio_url = episode.get('audio_url')
        
        logger.info(f"Retrieving audio for episode {episode_identifier}")
        logger.info(f"Audio file path: {audio_path}")
        logger.info(f"Audio URL: {audio_url}")
        
        if not audio_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No audio file path available in episode record"
            )
        
        # Try multiple approaches to find the audio file
        possible_paths = []
        
        # 1. Direct path as stored
        possible_paths.append(audio_path)
        
        # 2. Handle relative paths
        if not os.path.isabs(audio_path):
            if audio_path.startswith('./'):
                possible_paths.append(audio_path[2:])  # Remove './' prefix
            possible_paths.append(os.path.join(DATA_FOLDER, audio_path))
            
        # 3. Try just the filename in the data folder
        filename = os.path.basename(audio_path)
        possible_paths.append(os.path.join(DATA_FOLDER, "podcasts", "audio", filename))
        
        # 4. If audio_url is set, try to extract path from it
        if audio_url and audio_url.startswith('/data/'):
            possible_paths.append(os.path.join(DATA_FOLDER, audio_url[6:]))  # Remove '/data/' prefix
            
        # Log all paths we're going to try
        logger.info(f"Trying the following paths: {possible_paths}")
        
        # Try each path
        file_path = None
        for path in possible_paths:
            if os.path.exists(path):
                file_path = path
                logger.info(f"Found audio file at: {file_path}")
                break
                
        if not file_path:
            # If file not found, log all attempted paths
            logger.error(f"Audio file not found at any of these locations: {possible_paths}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Audio file not found. Tried: {', '.join(possible_paths)}"
            )
            
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Create streaming response
        async def file_generator():
            async with aiofiles.open(file_path, 'rb') as f:
                while True:
                    chunk = await f.read(8192)
                    if not chunk:
                        break
                    yield chunk
                    
        return StreamingResponse(
            file_generator(),
            media_type="audio/mpeg",
            headers={
                'Content-Disposition': f'inline; filename="{os.path.basename(file_path)}"',
                'Content-Length': str(file_size),
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET',
                'Access-Control-Allow-Headers': '*'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error getting episode audio: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

async def get_template_by_id_or_name(template_identifier: str, db: AsyncSurreal):
    """
    Helper function to get a template by ID or name.
    
    Args:
        template_identifier: Either the template ID (e.g., 'podcast_config:123') or template name
        db: Database connection
        
    Returns:
        dict: Template data with properly formatted ID
        
    Raises:
        HTTPException: 404 if template not found, 500 for other errors
    """
    try:
        logger.debug(f"Looking up template by identifier: {template_identifier}")
        
        # First try to get by ID if it looks like an ID
        if ':' in template_identifier:
            try:
                logger.debug(f"Attempting to get template by ID: {template_identifier}")
                template = await db.select(template_identifier)
                if template:
                    logger.debug(f"Found template by ID: {template_identifier}")
                    template = dict(template)
                    template['id'] = template_identifier  # Ensure we keep the full ID
                    return template
            except Exception as e:
                logger.warning(f"Error looking up by ID {template_identifier}: {e}")
        
        # If not found by ID or not an ID, try by name
        logger.debug(f"Attempting to find template by name: '{template_identifier}'")
        
        # First, try to list all templates to see what we have
        try:
            all_templates = await db.select(PODCAST_CONFIG_TABLE)
            logger.debug(f"Found {len(all_templates) if all_templates else 0} templates in database")
            
            # Try to find a case-insensitive match manually
            for t in all_templates or []:
                try:
                    t_dict = dict(t)
                    t_name = t_dict.get('name', '').lower()
                    if t_name == template_identifier.lower():
                        logger.debug(f"Found matching template by name: {t_dict}")
                        # Ensure ID is properly formatted
                        if 'id' in t_dict:
                            if hasattr(t_dict['id'], 'id'):
                                t_dict['id'] = str(t_dict['id'].id)
                            elif hasattr(t_dict['id'], 'table_name'):
                                t_dict['id'] = f"{t_dict['id'].table_name}:{t_dict['id'].id}"
                            else:
                                t_dict['id'] = str(t_dict['id'])
                        return t_dict
                except Exception as e:
                    logger.warning(f"Error processing template: {e}")
                    continue
        except Exception as debug_error:
            logger.warning(f"Error listing all templates: {debug_error}")
        
        # If manual search didn't work, try direct queries
        queries_to_try = [
            (f"SELECT * FROM {PODCAST_CONFIG_TABLE} WHERE name = $name LIMIT 1",
             {"name": template_identifier},
             "exact match"),
            
            (f"SELECT * FROM {PODCAST_CONFIG_TABLE} WHERE name ILIKE $name LIMIT 1",
             {"name": template_identifier},
             "case-insensitive match"),
            
            (f"SELECT * FROM {PODCAST_CONFIG_TABLE} WHERE name ~* $name LIMIT 1",
             {"name": f"^{template_identifier}$"},
             "regex match")
        ]
        
        for query, params, query_type in queries_to_try:
            try:
                logger.debug(f"Trying {query_type} query: {query} with params {params}")
                result = await db.query(query, params)
                
                if result and result[0] and result[0][0]:
                    template = dict(result[0][0])
                    logger.debug(f"Found template using {query_type}: {template}")
                    # Ensure ID is properly formatted
                    if 'id' in template:
                        if hasattr(template['id'], 'id'):
                            template['id'] = str(template['id'].id)
                        elif hasattr(template['id'], 'table_name'):
                            template['id'] = f"{template['id'].table_name}:{template['id'].id}"
                        else:
                            template['id'] = str(template['id'])
                    return template
                    
            except Exception as query_error:
                logger.warning(f"Query failed ({query_type}): {query_error}")
                continue
        
        # If we get here, no template was found
        logger.warning(f"Template not found: {template_identifier}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found: {template_identifier}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error getting template {template_identifier}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

@router.get("/templates/{template_identifier}", response_model=PodcastTemplateResponse)
async def get_podcast_template(
    template_identifier: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Get a specific podcast template by ID or name.
    
    Parameters:
    - template_identifier: Either the template ID (e.g., 'podcast_config:123') or template name
    """
    try:
        template = await get_template_by_id_or_name(template_identifier, db)
        return PodcastTemplateResponse(**template)
    except HTTPException as he:
        raise
    except Exception as e:
        logger.error(f"Error getting template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/templates", response_model=List[PodcastTemplateResponse])
async def list_podcast_templates(
    db: AsyncSurreal = Depends(get_db_connection)
):
    """List all podcast templates."""
    try:
        logger.debug(f"Attempting to list all templates from table: {PODCAST_CONFIG_TABLE}")
        
        # Try to get table info first to check if it exists
        try:
            # This is a SurrealDB-specific way to check if table exists
            table_info = await db.query(f"INFO FOR TABLE {PODCAST_CONFIG_TABLE}")
            logger.debug(f"Table info: {table_info}")
        except Exception as e:
            logger.warning(f"Error getting table info: {e}")
            # Continue anyway, as the table might exist but we might not have permissions to get info
        
        # Get all templates
        templates = await db.select(PODCAST_CONFIG_TABLE)
        logger.debug(f"Raw templates from DB: {templates}")
        
        if not templates:
            logger.info("No templates found in the database")
            return []
        
        # Process templates
        processed_templates = []
        for template in templates:
            try:
                if not template:
                    logger.warning("Found empty template in results, skipping")
                    continue
                    
                template_dict = dict(template)
                logger.debug(f"Processing template: {template_dict}")
                
                # Ensure ID is properly converted to string
                if 'id' in template_dict and hasattr(template_dict['id'], 'id'):
                    template_dict['id'] = str(template_dict['id'].id)
                elif 'id' in template_dict:
                    template_dict['id'] = str(template_dict['id'])
                
                # Validate the template data
                try:
                    validated = PodcastTemplateResponse(**template_dict)
                    processed_templates.append(validated.model_dump())
                except Exception as ve:
                    logger.error(f"Validation error for template {template_dict.get('id', 'unknown')}: {ve}")
                    # Skip invalid templates but continue processing others
                    continue
                    
            except Exception as te:
                logger.error(f"Error processing template: {te}", exc_info=True)
                continue
        
        logger.info(f"Successfully processed {len(processed_templates)} templates")
        return [PodcastTemplateResponse(**t) for t in processed_templates]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing templates: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list templates: {str(e)}"
        )

from fastapi import Form

def parse_list_field(value: Optional[str]) -> List[str]:
    """Parse a comma-separated string into a list of strings."""
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]

@router.post("/templates", response_model=StatusResponse)
async def create_podcast_template(
    name: str = Form(...),
    podcast_name: str = Form(...),
    podcast_tagline: str = Form(...),
    output_language: str = Form("English"),
    person1_role: str = Form(...),
    person2_role: str = Form(...),
    conversation_style: str = Form(...),
    engagement_technique: str = Form(...),
    dialogue_structure: str = Form(...),
    transcript_model: Optional[str] = Form(None),
    transcript_model_provider: Optional[str] = Form(None),
    user_instructions: Optional[str] = Form(None),
    ending_message: Optional[str] = Form(None),
    creativity: float = Form(..., ge=0, le=1),
    provider: str = Form("openai"),
    voice1: str = Form(...),
    voice2: str = Form(...),
    model: str = Form(...),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Create a new podcast template using form data.
    
    This endpoint accepts form data and creates a new podcast template.
    List fields (person1_role, person2_role, etc.) should be comma-separated strings.
    The 'creativity' field should be a float between 0 and 1 (inclusive).
    """
    try:
        # Prepare the template data
        template_data = {
            "name": name,
            "podcast_name": podcast_name,
            "podcast_tagline": podcast_tagline,
            "output_language": output_language,
            "person1_role": parse_list_field(person1_role),
            "person2_role": parse_list_field(person2_role),
            "conversation_style": parse_list_field(conversation_style),
            "engagement_technique": parse_list_field(engagement_technique),
            "dialogue_structure": parse_list_field(dialogue_structure),
            "transcript_model": transcript_model,
            "transcript_model_provider": transcript_model_provider,
            "user_instructions": user_instructions,
            "ending_message": ending_message,
            "creativity": min(max(0.0, float(creativity)), 1.0),  # Ensure between 0 and 1
            "provider": provider,
            "voice1": voice1,
            "voice2": voice2,
            "model": model
        }
        
        # Convert the request data to PodcastTemplateResponse for validation
        try:
            template = PodcastTemplateResponse(**template_data)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e)
            )
        
        # Create the template in the database
        result = await db.create(PODCAST_CONFIG_TABLE, template.model_dump())
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create template in the database"
            )
            
        # Convert the result to a dict and ensure all fields are serializable
        result_dict = dict(result)
        result_dict['id'] = str(result_dict.get('id', ''))
        
        # Return the standard response format
        return StatusResponse(
            status="success",
            message="Podcast template created successfully",
            data=result_dict
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating podcast template: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while creating the podcast template: {str(e)}"
        )

@router.put("/templates/{template_identifier}", response_model=StatusResponse)
async def update_podcast_template(
    template_identifier: str,
    name: str = Form(...),
    podcast_name: str = Form(...),
    podcast_tagline: str = Form(...),
    output_language: str = Form("English"),
    person1_role: str = Form(...),
    person2_role: str = Form(...),
    conversation_style: str = Form(...),
    engagement_technique: str = Form(...),
    dialogue_structure: str = Form(...),
    transcript_model: Optional[str] = Form(None),
    transcript_model_provider: Optional[str] = Form(None),
    user_instructions: Optional[str] = Form(None),
    ending_message: Optional[str] = Form(None),
    creativity: float = Form(..., ge=0, le=1),
    provider: str = Form("openai"),
    voice1: str = Form(...),
    voice2: str = Form(...),
    model: str = Form(...),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Update an existing podcast template by ID or name using form data.
    
    Parameters:
    - template_identifier: Either the template ID (e.g., 'podcast_config:123') or template name
    """
    try:
        # First get the existing template to ensure it exists
        existing_template = await get_template_by_id_or_name(template_identifier, db)
        
        # Prepare the update data
        update_data = {
            "name": name,
            "podcast_name": podcast_name,
            "podcast_tagline": podcast_tagline,
            "output_language": output_language,
            "person1_role": parse_list_field(person1_role),
            "person2_role": parse_list_field(person2_role),
            "conversation_style": parse_list_field(conversation_style),
            "engagement_technique": parse_list_field(engagement_technique),
            "dialogue_structure": parse_list_field(dialogue_structure),
            "transcript_model": transcript_model,
            "transcript_model_provider": transcript_model_provider,
            "user_instructions": user_instructions,
            "ending_message": ending_message,
            "creativity": min(max(0.0, float(creativity)), 1.0),
            "provider": provider,
            "voice1": voice1,
            "voice2": voice2,
            "model": model
        }
        
        # Validate the template data
        try:
            validated = PodcastTemplateResponse(**update_data)
        except Exception as ve:
            logger.error(f"Validation error: {ve}")
            raise HTTPException(status_code=422, detail=str(ve))
        
        # Update the template in the database
        # Ensure the ID is in the correct format for the UPDATE query
        template_id = existing_template['id']
        if hasattr(template_id, 'table_name') and hasattr(template_id, 'record_id'):
            # It's a RecordID object
            template_id = f"{template_id.table_name}:{template_id.record_id}"
        elif ':' not in template_id:
            template_id = f"{PODCAST_CONFIG_TABLE}:{template_id}"
        
        # Use merge operation instead of UPDATE for better SurrealDB compatibility
        update_data = validated.model_dump(exclude_unset=True)
        # Remove id from update data to avoid conflicts
        if 'id' in update_data:
            del update_data['id']
        
        # Use merge to update the record
        result = await db.merge(template_id, update_data)
        
        if not result:
            raise HTTPException(status_code=404, detail="Failed to update template")
        
        # Get the updated template - merge returns the updated record directly
        updated_template = dict(result)
        if 'id' in updated_template:
            updated_template['id'] = str(updated_template['id'])
        
        return StatusResponse(
            status="success",
            message=f"Template '{template_identifier}' updated successfully",
            data=updated_template
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating template: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update template: {str(e)}"
        )

@router.delete("/templates/{template_identifier}", response_model=StatusResponse)
async def delete_podcast_template(
    template_identifier: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Delete a podcast template by ID or name.
    
    Parameters:
    - template_identifier: Either the template ID (e.g., 'podcast_config:123') or template name
    """
    try:
        logger.info(f"Attempting to delete template: {template_identifier}")
        
        # Get the template to ensure it exists and get its ID
        try:
            template = await get_template_by_id_or_name(template_identifier, db)
            logger.debug(f"Found template for deletion: {template}")
            
            if not template or 'id' not in template:
                logger.warning(f"Template not found: {template_identifier}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template not found: {template_identifier}"
                )
                
            # Get the template ID
            template_id = template['id']
            logger.info(f"Deleting template with ID: {template_id}")
            
            # Ensure the ID is in the correct format for deletion
            if ':' not in template_id:
                template_id = f"{PODCAST_CONFIG_TABLE}:{template_id}"
                logger.debug(f"Formatted template ID for deletion: {template_id}")
            
            # First try to delete using the direct delete method
            try:
                logger.debug(f"Attempting direct delete with ID: {template_id}")
                result = await db.delete(template_id)
                
                if not result:
                    # If direct delete fails, try with a query
                    logger.debug("Direct delete failed, trying with query")
                    query = f"DELETE FROM {PODCAST_CONFIG_TABLE} WHERE id = $id"
                    result = await db.query(query, {"id": template_id})
                    
                    # Check if the query was successful
                    if not result or not result[0]:
                        logger.warning(f"Template with ID {template_id} not found in database")
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Template with ID {template_id} not found"
                        )
                
                logger.info(f"Successfully deleted template: {template_id}")
                return StatusResponse(
                    status="success",
                    message=f"Template '{template_identifier}' deleted successfully",
                    data={"deleted_id": str(template_id)}
                )
                
            except Exception as delete_error:
                logger.error(f"Error during template deletion: {str(delete_error)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error deleting template: {str(delete_error)}"
                )
                
        except HTTPException:
            raise
            
    except HTTPException as http_err:
        # Re-raise HTTP exceptions as-is
        raise
        
    except Exception as e:
        error_msg = f"Unexpected error deleting template {template_identifier}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

@router.get("/models", response_model=Dict[str, Dict[str, List[str]]], operation_id="get_podcast_models")
async def get_available_models():
    """Get available models for podcast generation."""
    try:
        # Get text-to-speech models
        tts_models = Model.get_models_by_type("text_to_speech")
        provider_models = {}
        for model in tts_models:
            if model.provider not in provider_models:
                provider_models[model.provider] = []
            provider_models[model.provider].append(model.name)

        # Get language models
        text_models = Model.get_models_by_type("language")
        transcript_provider_models = {}
        for model in text_models:
            if model.provider not in ["gemini", "openai", "anthropic"]:
                continue
            if model.provider not in transcript_provider_models:
                transcript_provider_models[model.provider] = []
            transcript_provider_models[model.provider].append(model.name)

        return {
            "provider_models": provider_models,
            "transcript_provider_models": transcript_provider_models,
            "suggestions": {
                "participant_roles": participant_roles,
                "conversation_styles": conversation_styles,
                "engagement_techniques": engagement_techniques,
                "dialogue_structures": dialogue_structures
            }
        }
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate", response_model=PodcastGenerateResponse)
async def generate_podcast_episode(
    request: PodcastGenerateRequest,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Generate a new podcast episode based on a template and notebook content."""
    try:
        warnings = []
        audio_file = None
        template_data = None
        context_text = ""
        
        # Find the template
        template_query = f"SELECT * FROM {PODCAST_CONFIG_TABLE} WHERE name = $name"
        template_result = await db.query(template_query, {"name": request.template_name})
        if not template_result or not isinstance(template_result, list) or len(template_result) == 0:
            logger.error(f"Template query returned unexpected result: {template_result}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Podcast template '{request.template_name}' not found (empty result)"
            )
        first_item = template_result[0]
        if isinstance(first_item, dict):
            template_data = first_item
        elif isinstance(first_item, list):
            if len(first_item) == 0:
                logger.error(f"Template query returned empty list in first item: {template_result}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Podcast template '{request.template_name}' not found (empty inner list)"
                )
            template_data = first_item[0]
        else:
            logger.error(f"Template query returned unexpected structure: {template_result}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected template query result structure: {type(first_item)}"
            )
        logger.info(f"Found template: {template_data}")

        # Convert to PodcastConfig instance
        try:
            template_data = convert_record_id_to_string(template_data)
            # Explicitly convert id to string if needed
            if 'id' in template_data and not isinstance(template_data['id'], str):
                template_data['id'] = str(template_data['id'])
            logger.debug(f"Template data after RecordID conversion: {template_data}")
            podcast_config = PodcastConfig(**template_data)
        except Exception as e:
            logger.error(f"Error converting template to PodcastConfig: {e}")
            raise HTTPException(status_code=500, detail=f"Invalid template data: {e}")

        # Build context from notebook notes and sources if notebook_name is provided
        if request.notebook_name:
            notebook_query = "SELECT * FROM notebook WHERE name = $name"
            notebook_result = await db.query(notebook_query, {"name": request.notebook_name})
            logger.info(f"Raw notebook_result: {notebook_result} (type: {type(notebook_result)})")
            
            if not notebook_result or len(notebook_result) == 0:
                raise HTTPException(status_code=404, detail=f"Notebook '{request.notebook_name}' not found")
                
            notebook_data = notebook_result[0]
            if isinstance(notebook_data, list) and len(notebook_data) > 0:
                notebook_data = notebook_data[0]
            
            logger.info(f"Notebook ID: {notebook_data.get('id')}")
            
            # Get notes and sources for the notebook
            notes_query = "select * omit note.embedding from (select in as note from artifact where out=$id fetch note) order by note.updated desc"
            sources_query = "select * from (select in as source from reference where out=$id fetch source) order by source.updated desc"
            
            logger.info(f"Notes query: {notes_query}")
            logger.info(f"Sources query: {sources_query}")
            
            notes_result = await db.query(notes_query, {"id": notebook_data.get("id")})
            sources_result = await db.query(sources_query, {"id": notebook_data.get("id")})
            
            logger.info(f"Fetched notes_result: {notes_result} (type: {type(notes_result)})")
            logger.info(f"Fetched sources_result: {sources_result} (type: {type(sources_result)})")
            
            # Extract notes and sources content
            note_contexts = []
            source_contexts = []
            
            # Process notes
            if notes_result:
                for note_item in notes_result:
                    if isinstance(note_item, dict) and "note" in note_item:
                        note = note_item["note"]
                        if note:
                            note_contexts.append({
                                "id": str(note.get("id")),
                                "title": note.get("title"),
                                "content": note.get("content")
                            })
            
            # Process sources
            if sources_result:
                for source_item in sources_result:
                    if isinstance(source_item, dict) and "source" in source_item:
                        source = source_item["source"]
                        if source:
                            source_contexts.append({
                                "id": str(source.get("id")),
                                "title": source.get("title"),
                                "full_text": source.get("full_text")
                            })
            
            logger.info(f"Extracted notes: {note_contexts} (type: {type(note_contexts)})")
            logger.info(f"Extracted sources: {source_contexts} (type: {type(source_contexts)})")
            
            # Build context dictionary
            context = {
                "note": note_contexts,
                "source": source_contexts
            }
            
            # If context is empty, use notebook description as fallback
            if not note_contexts and not source_contexts:
                notebook_description = notebook_data.get("description", "")
                if notebook_description:
                    logger.warning("No notes or sources found, using notebook description as context.")
                    # Pad the description to avoid fallback to Gemini/Google
                    min_length = 500
                    padded_description = (notebook_description + " ") * ((min_length // len(notebook_description)) + 1)
                    padded_description = padded_description[:min_length]
                    context = {"note": [], "source": [], "description": padded_description}
                else:
                    logger.error("Cannot generate podcast: notebook context is empty (no notes, sources, or description). Add content to your notebook and try again.")
                    raise HTTPException(status_code=400, detail="Cannot generate podcast: notebook context is empty (no notes, sources, or description). Add content to your notebook and try again.")
            context_text = json.dumps(context)
        else:
            context_text = ""

        # Ensure context_text is always valid JSON (handle legacy or Streamlit dict strings)
        if isinstance(context_text, str):
            try:
                # Try to parse as JSON first
                json.loads(context_text)
            except Exception:
                try:
                    # Parse as Python dict and convert to JSON
                    context_obj = ast.literal_eval(context_text)
                    context_text = json.dumps(context_obj)
                except Exception:
                    pass

        # Use PodcastConfig.generate_episode to create the episode (matches Streamlit logic)
        episode_name = request.episode_name or f"Episode {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        podcast_length = request.podcast_length or "Medium (10-20 min)"
        # Set chunking params as in Streamlit
        if podcast_length == "Short (5-10 min)":
            longform = False
            chunks = 2
            min_chunk_size = 300
        elif podcast_length == "Medium (10-20 min)":
            longform = True
            chunks = 4
            min_chunk_size = 600
        else:
            longform = True
            chunks = 8
            min_chunk_size = 600
        
        # Generate episode
        try:
            # Generate the podcast - the PodcastConfig.generate_episode method now handles
            # creating the episode record with the proper audio_url
            audio_file = podcast_config.generate_episode(
                episode_name=episode_name,
                text=context_text,
                instructions=request.instructions or podcast_config.user_instructions or "",
                longform=longform,
                chunks=chunks,
                min_chunk_size=min_chunk_size
            )
            
            # Update the episode with notebook reference if we have a notebook
            if request.notebook_name and notebook_data:
                # Find the episode we just created and update it with notebook reference
                episode_query = f"SELECT * FROM {PODCAST_EPISODE_TABLE} WHERE name = $name ORDER BY created DESC LIMIT 1"
                episode_result = await db.query(episode_query, {"name": episode_name})
                
                if episode_result and len(episode_result) > 0:
                    episode_data = episode_result[0]
                    if isinstance(episode_data, list) and len(episode_data) > 0:
                        episode_data = episode_data[0]
                    
                    episode_id = episode_data.get('id')
                    if episode_id:
                        # Update the episode with content_source information
                        content_source = {
                            "type": "notebook",
                            "id": notebook_data.get("id"),
                            "name": request.notebook_name
                        }
                        
                        update_query = f"UPDATE {episode_id} SET content_source = $content_source"
                        await db.query(update_query, {"content_source": content_source})
                        logger.info(f"Updated episode {episode_id} with notebook reference: {request.notebook_name}")
            
            # No need to update the episode with audio_url as it's now handled in the generate_episode method
            
        except Exception as e:
            logger.error(f"Failed to generate episode: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to generate episode: {e}")

        return PodcastGenerateResponse(
            status="success",
            message=f"Podcast generation completed successfully for episode: {episode_name}",
            warnings=warnings
        )
    except HTTPException as http_exc:
        logger.error(f"HTTP Exception: {str(http_exc)}")
        raise http_exc
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Unexpected error in podcast generation: {error_type}")
        logger.error(f"Error message: {error_msg}")
        logger.error(f"Full traceback:", exc_info=True)
        logger.error(f"Current template: {template_data if template_data else 'Not available'}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error during podcast generation: {error_type}. Error: {error_msg}"
        )

@router.get("/models")
async def get_available_models() -> Dict[str, Dict[str, List[str]]]:
    """Gets available models for podcast generation."""
    try:
        # Check which providers have API keys configured
        available_providers = {
            provider: bool(os.getenv(key_name))
            for provider, key_name in REQUIRED_API_KEYS.items()
        }
        
        # Get text-to-speech models
        tts_models = Model.get_models_by_type("text_to_speech")
        provider_models = {}
        for model in tts_models:
            if not available_providers.get(model.provider, False):
                continue
            if model.provider not in provider_models:
                provider_models[model.provider] = []
            provider_models[model.provider].append(model.name)
        
        # Get language models
        text_models = Model.get_models_by_type("language")
        transcript_provider_models = {}
        for model in text_models:
            if model.provider not in ["gemini", "openai", "anthropic"]:
                continue
            if not available_providers.get(model.provider, False):
                continue
            if model.provider not in transcript_provider_models:
                transcript_provider_models[model.provider] = []
            transcript_provider_models[model.provider].append(model.name)
        
        return {
            "provider_models": provider_models,
            "transcript_provider_models": transcript_provider_models,
            "available_providers": available_providers
        }
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error getting models: {e}"
        )

@router.get("/suggestions")
async def get_suggestions() -> Dict[str, List[str]]:
    """Gets suggestion lists for template creation."""
    return {
        "conversation_styles": conversation_styles,
        "dialogue_structures": dialogue_structures,
        "engagement_techniques": engagement_techniques,
        "participant_roles": participant_roles
    }

@router.post("/reassign-episodes", response_model=StatusResponse)
async def reassign_episodes_by_content(
    db: AsyncSurreal = Depends(get_db_connection),
    debug: bool = False
):
    """Reassign existing episodes to notebooks based on content analysis."""
    try:
        logger.info("Starting episode reassignment based on content analysis")
        
        # Get all episodes
        episodes_query = f"SELECT * FROM {PODCAST_EPISODE_TABLE}"
        episodes_result = await db.query(episodes_query)
        
        if not episodes_result:
            logger.info("No episodes found")
            return StatusResponse(
                status="success",
                message="No episodes found to reassign"
            )
        
        # Get all notebooks
        notebook_query = "SELECT * FROM notebook"
        notebooks_result = await db.query(notebook_query)
        
        if not notebooks_result:
            logger.error("No notebooks found")
            return StatusResponse(
                status="error",
                message="No notebooks found"
            )
        
        # Keywords for different notebooks
        notebook_keywords = {
            "spacetime": ["spacetime", "einstein", "relativity", "gravity", "minkowski", "equivalence principle", "general relativity", "special relativity"],
            "Quantum mechanics": ["quantum", "mechanics", "physics", "particle", "wave", "quantum mechanics"],
            "Big Data Analytics": ["data", "analytics", "big data", "machine learning", "algorithm", "rpa", "automation"]
        }
        
        reassigned_count = 0
        
        for ep in episodes_result:
            if isinstance(ep, list) and len(ep) > 0:
                ep = ep[0]
            
            ep_dict = ep.model_dump() if hasattr(ep, 'model_dump') else dict(ep)
            episode_id = ep_dict.get('id')
            episode_name = ep_dict.get('name', '')
            episode_text = ep_dict.get('text', '')
            
            if not episode_id:
                continue
            
            # Analyze content to find best matching notebook
            best_match = None
            best_score = 0
            
            for notebook in notebooks_result:
                if isinstance(notebook, list) and len(notebook) > 0:
                    notebook = notebook[0]
                
                notebook_dict = notebook.model_dump() if hasattr(notebook, 'model_dump') else dict(notebook)
                notebook_id = notebook_dict.get('id')
                notebook_name = notebook_dict.get('name', '')
                
                if notebook_id and notebook_name:
                    # Calculate score based on keyword matches
                    score = 0
                    keywords = notebook_keywords.get(notebook_name, [])
                    
                    # Check episode name and text for keywords
                    search_text = f"{episode_name} {episode_text}".lower()
                    for keyword in keywords:
                        if keyword.lower() in search_text:
                            score += 1
                    
                    # Bonus for exact notebook name match in episode name
                    if notebook_name.lower() in episode_name.lower():
                        score += 2
                    
                    if score > best_score:
                        best_score = score
                        best_match = {
                            "id": notebook_id,
                            "name": notebook_name
                        }
            
            if best_match and best_score > 0:
                # Update the episode with the new notebook reference
                content_source = {
                    "type": "notebook",
                    "id": best_match["id"],
                    "name": best_match["name"]
                }
                
                if debug:
                    logger.info(f"Would reassign episode {episode_id} from current to {best_match['name']} (score: {best_score})")
                else:
                    update_query = f"UPDATE {episode_id} SET content_source = $content_source"
                    await db.query(update_query, {"content_source": content_source})
                    logger.info(f"Reassigned episode {episode_id} to notebook: {best_match['name']} (score: {best_score})")
                
                reassigned_count += 1
        
        return StatusResponse(
            status="success",
            message=f"Reassignment completed. Reassigned {reassigned_count} episodes based on content analysis."
        )
        
    except Exception as e:
        logger.error(f"Error reassigning episodes: {e}")
        raise HTTPException(status_code=500, detail=f"Error reassigning episodes: {e}")

@router.post("/migrate-episodes", response_model=StatusResponse)
async def migrate_episodes_with_notebook_references(
    db: AsyncSurreal = Depends(get_db_connection),
    debug: bool = False
):
    """Migrate existing episodes to add notebook references based on their names or other clues."""
    try:
        logger.info("Starting episode migration to add notebook references")
        
        # Get all episodes without content_source
        episodes_query = f"SELECT * FROM {PODCAST_EPISODE_TABLE} WHERE content_source IS NONE OR content_source = NONE"
        episodes_result = await db.query(episodes_query)
        
        if not episodes_result:
            logger.info("No episodes found without content_source")
            return StatusResponse(
                status="success",
                message="No episodes need migration"
            )
        
        migrated_count = 0
        skipped_count = 0
        
        for ep in episodes_result:
            if isinstance(ep, list) and len(ep) > 0:
                ep = ep[0]
            
            ep_dict = ep.model_dump() if hasattr(ep, 'model_dump') else dict(ep)
            episode_id = ep_dict.get('id')
            episode_name = ep_dict.get('name', '')
            
            if not episode_id:
                logger.warning(f"Skipping episode without ID: {ep_dict}")
                skipped_count += 1
                continue
            
            # Try to find a notebook that might be related to this episode based on content
            notebook_query = "SELECT * FROM notebook"
            notebooks_result = await db.query(notebook_query)
            
            best_match = None
            if notebooks_result:
                # Analyze episode content to find the best matching notebook
                episode_text = ep_dict.get('text', '')
                episode_name = ep_dict.get('name', '')
                
                # Keywords for different notebooks
                notebook_keywords = {
                    "spacetime": ["spacetime", "einstein", "relativity", "gravity", "minkowski", "equivalence principle"],
                    "Quantum mechanics": ["quantum", "mechanics", "physics", "particle", "wave"],
                    "Big Data Analytics": ["data", "analytics", "big data", "machine learning", "algorithm"]
                }
                
                # Score each notebook based on keyword matches
                best_score = 0
                for notebook in notebooks_result:
                    if isinstance(notebook, list) and len(notebook) > 0:
                        notebook = notebook[0]
                    
                    notebook_dict = notebook.model_dump() if hasattr(notebook, 'model_dump') else dict(notebook)
                    notebook_id = notebook_dict.get('id')
                    notebook_name = notebook_dict.get('name', '')
                    
                    if notebook_id and notebook_name:
                        # Calculate score based on keyword matches
                        score = 0
                        keywords = notebook_keywords.get(notebook_name, [])
                        
                        # Check episode name and text for keywords
                        search_text = f"{episode_name} {episode_text}".lower()
                        for keyword in keywords:
                            if keyword.lower() in search_text:
                                score += 1
                        
                        # Bonus for exact notebook name match in episode name
                        if notebook_name.lower() in episode_name.lower():
                            score += 2
                        
                        if score > best_score:
                            best_score = score
                            best_match = {
                                "id": notebook_id,
                                "name": notebook_name
                            }
                
                # If no good match found, use the first notebook as fallback
                if not best_match and notebooks_result:
                    notebook = notebooks_result[0]
                    if isinstance(notebook, list) and len(notebook) > 0:
                        notebook = notebook[0]
                    
                    notebook_dict = notebook.model_dump() if hasattr(notebook, 'model_dump') else dict(notebook)
                    notebook_id = notebook_dict.get('id')
                    notebook_name = notebook_dict.get('name', '')
                    
                    if notebook_id and notebook_name:
                        best_match = {
                            "id": notebook_id,
                            "name": notebook_name
                        }
            
            if best_match:
                # Update the episode with the notebook reference
                content_source = {
                    "type": "notebook",
                    "id": best_match["id"],
                    "name": best_match["name"]
                }
                
                if debug:
                    logger.info(f"Would update episode {episode_id} with notebook reference: {best_match['name']}")
                else:
                    update_query = f"UPDATE {episode_id} SET content_source = $content_source"
                    await db.query(update_query, {"content_source": content_source})
                    logger.info(f"Updated episode {episode_id} with notebook reference: {best_match['name']}")
                
                migrated_count += 1
            else:
                logger.warning(f"No suitable notebook found for episode {episode_id}")
                skipped_count += 1
        
        return StatusResponse(
            status="success",
            message=f"Migration completed. Migrated {migrated_count} episodes, skipped {skipped_count} episodes."
        )
        
    except Exception as e:
        logger.error(f"Error migrating episodes: {e}")
        raise HTTPException(status_code=500, detail=f"Error migrating episodes: {e}")

@router.post("/cleanup", response_model=StatusResponse)
async def cleanup_incomplete_episodes(
    db: AsyncSurreal = Depends(get_db_connection),
    debug: bool = False,
    fix_missing_audio_url: bool = False
):
    """Clean up incomplete podcast episodes."""
    try:
        # Specific problematic episode IDs
        problem_ids = [
            "podcast_episode:n2qyiv57lkukkzlc4x2n",
            "podcast_episode:u4qgzateazqrrc36gzit"
        ]
        
        deleted_count = 0
        fixed_count = 0
        episode_details = []
        
        # Delete known problematic episodes
        for episode_id in problem_ids:
            try:
                await db.delete(episode_id)
                deleted_count += 1
                logger.info(f"Deleted known problematic episode: {episode_id}")
            except Exception as e:
                logger.error(f"Error deleting episode {episode_id}: {e}")
        
        # Find and delete episodes with missing audio files
        try:
            # Get all episodes
            all_episodes = await db.select(PODCAST_EPISODE_TABLE)
            
            for episode in all_episodes:
                episode_id = episode.get('id')
                audio_file = episode.get('audio_file')
                audio_url = episode.get('audio_url')
                
                # Log episode details if debug is True
                if debug:
                    episode_details.append({
                        "id": str(episode_id),
                        "name": episode.get('name'),
                        "audio_file": audio_file,
                        "audio_url": audio_url
                    })
                    logger.info(f"Episode details: {episode_id}, audio_file: {audio_file}, audio_url: {audio_url}")
                
                # Check if audio file exists
                file_exists = False
                file_path = None
                
                if audio_file:
                    # Check various possible paths
                    paths_to_check = [
                        audio_file,
                        os.path.join(DATA_FOLDER, "podcasts", "audio", os.path.basename(audio_file)),
                        os.path.join(DATA_FOLDER, audio_file) if not os.path.isabs(audio_file) else audio_file
                    ]
                    
                    for path in paths_to_check:
                        if os.path.exists(path):
                            file_exists = True
                            file_path = path
                            break
                
                # If audio file doesn't exist, delete the episode
                if not file_exists:
                    if debug:
                        logger.info(f"Would delete episode with missing audio: {episode_id}")
                    else:
                        try:
                            await db.delete(episode_id)
                            deleted_count += 1
                            logger.info(f"Deleted episode with missing audio: {episode_id}")
                        except Exception as e:
                            logger.error(f"Error deleting episode {episode_id}: {e}")
                # If audio file exists but audio_url is missing, fix it
                elif fix_missing_audio_url and file_exists and not audio_url:
                    try:
                        audio_filename = os.path.basename(audio_file)
                        new_audio_url = f"/data/podcasts/audio/{audio_filename}"
                        
                        if debug:
                            logger.info(f"Would update episode {episode_id} with audio_url: {new_audio_url}")
                        else:
                            await db.update(episode_id, {"audio_url": new_audio_url})
                            fixed_count += 1
                            logger.info(f"Fixed episode {episode_id} with audio_url: {new_audio_url}")
                    except Exception as e:
                        logger.error(f"Error fixing audio_url for episode {episode_id}: {e}")
        except Exception as e:
            logger.error(f"Error cleaning up episodes with missing audio: {e}")
        
        response = {
            "status": "success",
            "message": f"Cleanup completed. Deleted {deleted_count} incomplete episodes. Fixed {fixed_count} episodes with missing audio_url."
        }
        
        if debug:
            response["episodes"] = episode_details
            
        return StatusResponse(**response)
    except Exception as e:
        logger.error(f"Error cleaning up episodes: {e}")
        raise HTTPException(status_code=500, detail=f"Error cleaning up episodes: {e}")

async def process_episode(episode, episode_identifier: str, available_episodes: list):
    """
    Helper function to process an episode and check for name matches.
    
    Args:
        episode: The episode data (dict or object)
        episode_identifier: The name or ID to match against
        available_episodes: List to append episode names to for error reporting
        
    Returns:
        dict: The matched episode with converted IDs, or None if no match
    """
    try:
        if not episode:
            return None
            
        # Convert to dict if it's not already
        if not isinstance(episode, dict) and hasattr(episode, '__dict__'):
            episode = vars(episode)  # Use vars() to handle both objects and namedtuples
        elif not isinstance(episode, dict):
            logger.warning(f"Unexpected episode type: {type(episode)}")
            return None
            
        # Try to get episode name
        episode_name = None
        if 'name' in episode:
            episode_name = str(episode.get('name', '')).strip()
        elif 'title' in episode:  # Some databases might use 'title' instead of 'name'
            episode_name = str(episode.get('title', '')).strip()
            
        if not episode_name:
            logger.warning(f"Episode has no name/title: {episode}")
            return None
            
        logger.info(f"Checking episode: {episode_name}")
        available_episodes.append(episode_name)
        
        # Check for exact match first
        if episode_name == episode_identifier:
            logger.info(f"Found exact name match: {episode_name}")
            # Make sure we return a dict with string IDs
            episode_dict = dict(episode) if not isinstance(episode, dict) else episode
            return convert_record_id_to_string(episode_dict)
            
        # Then check case-insensitive match
        if episode_name.lower() == episode_identifier.lower():
            logger.info(f"Found case-insensitive name match: {episode_name}")
            # Make sure we return a dict with string IDs
            episode_dict = dict(episode) if not isinstance(episode, dict) else episode
            return convert_record_id_to_string(episode_dict)
            
        return None
        
    except Exception as e:
        logger.error(f"Error processing episode: {str(e)}", exc_info=True)
        return None

async def get_episode_by_id_or_name(episode_identifier: str, db: AsyncSurreal):
    """
    Helper function to get an episode by ID or name.
    
    Args:
        episode_identifier: Either the episode ID (e.g., 'podcast_episode:123') or episode name
        db: Database connection
        
    Returns:
        dict: Episode data with properly formatted ID
        
    Raises:
        HTTPException: 404 if episode not found, 500 for other errors
    """
    try:
        logger.info(f"Looking up episode by identifier: {episode_identifier}")
        
        # First check if the table exists
        try:
            table_info = await db.query(f"INFO FOR TABLE {PODCAST_EPISODE_TABLE}")
            logger.info(f"Table info: {table_info}")
        except Exception as e:
            logger.error(f"Error checking table {PODCAST_EPISODE_TABLE}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}"
            )
        
        # Try to get by ID first if it looks like an ID
        if ':' in episode_identifier:
            try:
                episode_id = episode_identifier
                if not episode_id.startswith(PODCAST_EPISODE_TABLE):
                    episode_id = f"{PODCAST_EPISODE_TABLE}:{episode_id}"
                
                logger.info(f"Attempting to get episode by ID: {episode_id}")
                episode = await db.select(episode_id)
                if episode:
                    logger.info(f"Found episode by ID: {episode_id}")
                    episode = dict(episode)
                    episode['id'] = episode_id  # Ensure we keep the full ID
                    return episode
                else:
                    logger.warning(f"No episode found with ID: {episode_id}")
            except Exception as e:
                logger.warning(f"Error looking up by ID {episode_identifier}: {e}")
        
        # If not found by ID or not an ID, try by name
        logger.info(f"Attempting to find episode by name: '{episode_identifier}'")
        
        # First, try to list all episodes to see what we have
        try:
            logger.info(f"Fetching all episodes from {PODCAST_EPISODE_TABLE}")
            query = f"SELECT * FROM {PODCAST_EPISODE_TABLE}"
            result = await db.query(query)
            
            if not result:
                logger.warning(f"No episodes found in {PODCAST_EPISODE_TABLE}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No episodes found in the database. Please create an episode first."
                )
                
            logger.info(f"Found {len(result)} episode records")
            
            # Debug the structure of the result
            logger.info(f"Raw result structure: {type(result)}")
            if isinstance(result, list):
                logger.info(f"Result is a list with {len(result)} rows")
                for i, row in enumerate(result):
                    logger.info(f"Row {i} type: {type(row)}")
                    if hasattr(row, '__dict__'):
                        logger.info(f"Row {i} attributes: {row.__dict__}")
                    if isinstance(row, (list, tuple)):
                        for j, item in enumerate(row):
                            logger.info(f"  Item {j} type: {type(item)}")
                            if hasattr(item, '__dict__'):
                                logger.info(f"  Item {j} attributes: {item.__dict__}")
            
            # Look for matching episode with more robust extraction
            available_episodes = []
            
            # Handle different possible result structures
            for row in result:
                # If row is a list of episodes
                if isinstance(row, (list, tuple)):
                    for episode in row:
                        matched_episode = await process_episode(episode, episode_identifier, available_episodes)
                        if matched_episode:
                            return matched_episode
                # If row is a dict representing an episode
                elif isinstance(row, dict):
                    matched_episode = await process_episode(row, episode_identifier, available_episodes)
                    if matched_episode:
                        return matched_episode
                # If row is an object with attributes
                elif hasattr(row, '__dict__'):
                    matched_episode = await process_episode(row.__dict__, episode_identifier, available_episodes)
                    if matched_episode:
                        return matched_episode
            
            # If we get here, no match was found
            
            logger.warning(f"Episode not found. Available episodes: {available_episodes}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": f"Episode not found: {episode_identifier}",
                    "available_episodes": available_episodes
                }
            )
            
        except HTTPException:
            raise
            
        except Exception as e:
            logger.error(f"Error querying episodes: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error querying episodes: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Unexpected error getting episode {episode_identifier}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

@router.get("/episodes/{episode_identifier}/details")
async def get_episode_details(
    episode_identifier: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Get detailed information about a specific episode.
    
    Parameters:
    - episode_identifier: Either the episode ID (e.g., 'podcast_episode:123') or episode name
    """
    try:
        # Get the episode using our helper function
        episode = await get_episode_by_id_or_name(episode_identifier, db)
        
        # Convert RecordID to string if needed
        episode = convert_record_id_to_string(episode)
        
        return {
            "id": episode.get("id"),
            "name": episode.get("name"),
            "template": episode.get("template"),
            "audio_file": episode.get("audio_file"),
            "audio_url": episode.get("audio_url"),
            "created": episode.get("created"),
            "status": episode.get("status", "unknown")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting episode details: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while getting episode details: {str(e)}"
        )

@router.get("/episodes/debug/list")
async def debug_list_episodes(
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Debug endpoint to list all episodes with all fields."""
    try:
        logger.info(f"PODCAST_EPISODE_TABLE: {PODCAST_EPISODE_TABLE}")
        
        # First try to list all tables to see what we have
        try:
            tables_result = await db.query("INFO FOR DB")
            logger.info(f"Database info: {tables_result}")
        except Exception as e:
            logger.error(f"Error getting database info: {str(e)}", exc_info=True)
        
        # Then try to query the episodes table
        query = f"SELECT * FROM {PODCAST_EPISODE_TABLE}"
        logger.info(f"Executing query: {query}")
        
        result = await db.query(query)
        logger.info(f"Query result type: {type(result)}")
        logger.info(f"Query result: {result}")
        
        if not result:
            logger.warning("Query returned no results")
            return {
                "status": "success", 
                "count": 0, 
                "episodes": [],
                "debug": {"query_result": str(result), "query_type": str(type(result))}
            }
            
        if not isinstance(result, list):
            logger.warning(f"Unexpected result type: {type(result)}")
            return {
                "status": "success", 
                "count": 0, 
                "episodes": [],
                "debug": {"query_result": str(result), "query_type": str(type(result))}
            }
            
        episodes = []
        for i, row in enumerate(result):
            logger.info(f"Row {i}: {row} (type: {type(row)})")
            if row and isinstance(row, list):
                for j, item in enumerate(row):
                    logger.info(f"  Item {j}: {item} (type: {type(item)})")
                    if isinstance(item, dict):
                        # Convert RecordID to string
                        episode = convert_record_id_to_string(item)
                        episodes.append(episode)
        
        return {
            "status": "success",
            "count": len(episodes),
            "episodes": episodes,
            "debug": {
                "query": query,
                "result_type": str(type(result)),
                "result_length": len(result) if hasattr(result, '__len__') else 'N/A'
            }
        }
        
    except Exception as e:
        logger.error(f"Error in debug_list_episodes: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing episodes: {str(e)}"
        )

@router.get("/episodes/list")
async def list_all_episodes(
    db: AsyncSurreal = Depends(get_db_connection)
):
    """List all podcast episodes with their names and IDs."""
    try:
        query = f"SELECT id, name, created FROM {PODCAST_EPISODE_TABLE} ORDER BY created DESC"
        result = await db.query(query)
        
        if not result or not isinstance(result, list):
            return []
            
        episodes = []
        for row in result:
            if row and isinstance(row, list) and row:
                episode = row[0]
                if isinstance(episode, dict):
                    episodes.append({
                        'id': str(episode.get('id', '')),
                        'name': episode.get('name', ''),
                        'created': str(episode.get('created', ''))
                    })
        
        return episodes
        
    except Exception as e:
        logger.error(f"Error listing episodes: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing episodes: {str(e)}"
        )

@router.get("/episodes/{episode_id}/debug")
async def debug_episode(
    episode_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Debug endpoint to check the status of a specific podcast episode."""
    try:
        # Format the episode ID correctly
        if not episode_id.startswith(PODCAST_EPISODE_TABLE):
            episode_id = f"{PODCAST_EPISODE_TABLE}:{episode_id}"
            
        # Query the episode
        query = f"SELECT * FROM {episode_id}"
        result = await db.query(query)
        
        if not result or len(result) == 0 or len(result[0]) == 0:
            return {"status": "error", "message": "Episode not found"}
        
        episode = result[0][0]
        audio_path = episode.get('audio_file')
        audio_url = episode.get('audio_url')
        
        # Check if the audio file exists
        file_exists = False
        file_path = None
        
        # Try multiple approaches to find the audio file
        possible_paths = []
        
        # 1. Direct path as stored
        possible_paths.append(audio_path)
        
        # 2. Handle relative paths
        if not os.path.isabs(audio_path):
            if audio_path.startswith('./'):
                possible_paths.append(audio_path[2:])  # Remove './' prefix
            possible_paths.append(os.path.join(DATA_FOLDER, audio_path))
            
        # 3. Try just the filename in the data folder
        filename = os.path.basename(audio_path)
        possible_paths.append(os.path.join(DATA_FOLDER, "podcasts", "audio", filename))
        
        # 4. If audio_url is set, try to extract path from it
        if audio_url and audio_url.startswith('/data/'):
            possible_paths.append(os.path.join(DATA_FOLDER, audio_url[6:]))  # Remove '/data/' prefix
        
        # Check each path
        found_paths = []
        for path in possible_paths:
            if os.path.exists(path):
                found_paths.append(path)
                file_exists = True
                if not file_path:  # Keep the first found path
                    file_path = path
        
        # Prepare the response
        response = {
            "id": str(episode.get('id')),
            "name": episode.get('name'),
            "template": str(episode.get('template')),
            "audio_file": audio_path,
            "audio_url": audio_url,
            "file_exists": file_exists,
            "found_at": found_paths,
            "tried_paths": possible_paths,
            "created": str(episode.get('created')),
            "data_folder": DATA_FOLDER
        }
        
        # Try to get template name
        if episode.get('template'):
            template_id = episode.get('template')
            if hasattr(template_id, 'table_name') and hasattr(template_id, 'id'):
                template_id = f"{template_id.table_name}:{template_id.id}"
            
            template_query = f"SELECT name FROM {PODCAST_CONFIG_TABLE} WHERE id = $id"
            template_result = await db.query(template_query, {"id": template_id})
            if template_result and len(template_result) > 0 and len(template_result[0]) > 0:
                response["template_name"] = template_result[0].get('name')
        
        return response
        
    except Exception as e:
        logger.error(f"Error debugging episode: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e), "traceback": str(e.__traceback__)}