import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import (
    APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Body
)
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import io
import sys
from pathlib import Path
import asyncio

from surrealdb import AsyncSurreal

from ..database import get_db_connection
from ..models import (
    Source, SourceSummary, StatusResponse, TaskStatus, SourceResponse, Note
)
from .notes import link_note_to_notebook, create_note_embedding
from pydantic import BaseModel, HttpUrl

from open_notebook.domain.content_settings import ContentSettings
from open_notebook.domain.transformation import Transformation
from open_notebook.domain.notebook import Source as DomainSource, Asset
from open_notebook.domain.models import model_manager
from open_notebook.config import UPLOADS_FOLDER

# LLM-powered source processing
try:
    from open_notebook.graphs.source import source_graph
    SOURCE_GRAPH_AVAILABLE = True
except ImportError as e:
    source_graph = None
    SOURCE_GRAPH_IMPORT_ERROR = e
    SOURCE_GRAPH_AVAILABLE = False

# Create a router for source-related endpoints
router = APIRouter(
    tags=["Sources"],
)

# Define the table name for sources in SurrealDB
SOURCE_TABLE = "source"
NOTEBOOK_TABLE = "notebook" # Needed for context checks

# Reintroduce SourceListResponse for list endpoints
class SourceListResponse(BaseModel):
    sources: List[SourceSummary]
    logs: List[str] = []

def convert_record_id_to_string(data):
    """Convert SurrealDB RecordID objects to strings in the response data."""
    if isinstance(data, dict):
        return {k: convert_record_id_to_string(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_record_id_to_string(item) for item in data]
    elif hasattr(data, 'table_name') and hasattr(data, 'record_id'):
        return f"{data.table_name}:{data.record_id}"
    return data

# --- Simplified Source Processing (without content_core) ---

async def process_source_simplified(
    content_state: Dict[str, Any],
    notebook_id: str,
    transformations: List[Transformation],
    embed: bool
) -> DomainSource:
    """
    Simplified source processing that works without content_core.
    Handles basic source creation, transformations, and embedding.
    """
    # Create source from content_state
    asset = None
    if content_state.get("url"):
        asset = Asset(url=content_state["url"])
    elif content_state.get("file_path"):
        asset = Asset(file_path=content_state["file_path"])
    
    # For text sources, use the content directly
    full_text = content_state.get("content", "")
    title = content_state.get("title", "Untitled Source")
    
    # Create the source
    source = DomainSource(
        asset=asset,
        full_text=full_text,
        title=title,
    )
    source.save()
    
    # Add to notebook
    if notebook_id:
        source.add_to_notebook(notebook_id)
    
    # Apply transformations (simplified - just create insights)
    for transformation in transformations:
        try:
            # For now, create a simple insight based on transformation
            insight_content = f"Transformation '{transformation.name}' applied: {transformation.description}"
            source.add_insight(transformation.title, insight_content)
        except Exception as e:
            print(f"Error applying transformation {transformation.name}: {e}")
    
    # Embed if requested
    if embed:
        try:
            source.vectorize()
        except Exception as e:
            print(f"Error vectorizing source: {e}")
    
    return source

# --- Unified Source Creation Endpoint ---

class SourceRequest(BaseModel):
    type: str
    url: Optional[str] = None
    content: Optional[str] = None
    apply_transformations: Optional[str] = None
    embed: Optional[bool] = False

@router.post("/api/v1/notebooks/{notebook_id}/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def add_source_to_notebook(
    notebook_id: str,
    type: str = Form(..., description="Type of source: link, upload, or text"),
    content: Optional[str] = Form(None, description="Text content for text sources"),
    url: Optional[str] = Form(None, description="URL for link sources"),
    file: Optional[UploadFile] = None,
    apply_transformations: Optional[str] = Form(None, description="Comma-separated list of transformation names"),
    embed: Optional[bool] = Form(False, description="Whether to embed the content for vector search"),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Add a new source to a notebook. Supports three types of sources:
    
    - *text*: Provide text content in the ⁠ content ⁠ field
    - *link*: Provide a URL in the ⁠ url ⁠ field
    - *upload*: Upload a file using the ⁠ file ⁠ field
    
    You can also specify transformations to apply and whether to embed the content.
    """
    if not SOURCE_GRAPH_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"The 'content_core' or LLM dependency is missing and is required for source processing. Please install it. Import error: {SOURCE_GRAPH_IMPORT_ERROR}")

    if type not in ["link", "upload", "text"]:
        raise HTTPException(status_code=400, detail="Invalid source type. Must be one of: link, upload, text.")

    if ":" not in notebook_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notebook ID format.")

    req: Dict[str, Any] = {}
    content_settings = ContentSettings()

    # Validate and process based on type
    if type == "text":
        if not content:
            raise HTTPException(status_code=400, detail="Content must be provided for text type.")
        req["content"] = content
    elif type == "link":
        if not url:
            raise HTTPException(status_code=400, detail="URL must be provided for link type.")
        req["url"] = url
    elif type == "upload":
        if not file:
            raise HTTPException(status_code=400, detail="File must be provided for upload type.")
        
        # Create uploads directory if it doesn't exist
        os.makedirs(UPLOADS_FOLDER, exist_ok=True)
        
        file_name = file.filename
        file_extension = Path(file_name).suffix
        base_name = Path(file_name).stem
        new_path = os.path.join(UPLOADS_FOLDER, file_name)
        counter = 0
        while os.path.exists(new_path):
            counter += 1
            new_file_name = f"{base_name}_{counter}{file_extension}"
            new_path = os.path.join(UPLOADS_FOLDER, new_file_name)
        
        # Save the uploaded file
        file_content = await file.read()
        with open(new_path, "wb") as f:
            f.write(file_content)
            
        req["file_path"] = str(new_path)
        req["delete_source"] = content_settings.auto_delete_files == "yes"

    transformations = []
    if apply_transformations:
        if isinstance(apply_transformations, str):
            names = [n.strip() for n in apply_transformations.split(",") if n.strip()]
            for t in Transformation.get_all():
                if t.name in names:
                    transformations.append(t)
        elif isinstance(apply_transformations, list):
            for t in Transformation.get_all():
                if t.name in apply_transformations:
                    transformations.append(t)
    else:
        transformations = [t for t in Transformation.get_all() if getattr(t, "apply_default", False)]

    state = {
        "content_state": req,
        "notebook_id": notebook_id,
        "apply_transformations": transformations,
        "embed": embed,
    }

    try:
        result = await source_graph.ainvoke(state)
        source = result.get("source")
        if not source:
            raise HTTPException(status_code=500, detail="Source creation failed.")
        
        # Generate title if not present (enhanced logic from Streamlit)
        title = source.title or ""
        if not title and source.full_text:
            try:
                from open_notebook.graphs.prompt import graph as prompt_graph
                from open_notebook.utils import surreal_clean
                
                # Generate title based on content type
                if type == "link" and url:
                    prompt = f"Based on this URL: {url}, provide a concise title (max 10 words) that describes the main topic or content."
                    input_text = url
                elif type == "upload" and file:
                    prompt = f"Based on this file: {file.filename}, provide a concise title (max 10 words) that describes the main topic or content."
                    input_text = source.full_text[:500]  # Use first 500 chars for title generation
                else:
                    prompt = "Based on the content below, provide a concise title (max 10 words) that describes the main topic or agenda."
                    input_text = source.full_text[:500]  # Use first 500 chars for title generation
                
                title_result = prompt_graph.invoke(dict(input_text=input_text, prompt=prompt))
                title = surreal_clean(title_result["output"])
                
                # Update the source with the generated title
                if title and title != "Untitled Source":
                    source.title = title
                    source.save()
                    
            except Exception as title_error:
                print(f"Error generating title: {title_error}")
                # Fallback to default title
                if type == "link":
                    title = f"Link: {url[:50]}..." if url else "Untitled Link"
                elif type == "upload":
                    title = f"File: {file.filename}" if file else "Untitled File"
                else:
                    title = "Untitled Source"
        
        return SourceResponse(
            id=str(source.id),
            title=title,
            type=type,
            status="completed",
            created=safe_datetime(getattr(source, "created", None)),
            updated=safe_datetime(getattr(source, "updated", None)),
            metadata=getattr(source, "metadata", {}),
            full_text=getattr(source, "full_text", ""),
            notebook_id=notebook_id,
            insights=[i.model_dump() for i in getattr(source, "insights", [])],
            embedded_chunks=getattr(source, "embedded_chunks", 0),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error creating source: {e}")

@router.post("/api/v1/notebooks/by-name/{notebook_name}/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def add_source_to_notebook_by_name(
    notebook_name: str,
    type: str = Form(..., description="Type of source: link, upload, or text"),
    content: Optional[str] = Form(None, description="Text content for text sources"),
    url: Optional[str] = Form(None, description="URL for link sources"),
    file: Optional[UploadFile] = File(None, description="File for upload sources"),
    apply_transformations: Optional[str] = Form(None, description="Comma-separated list of transformation names"),
    embed: Optional[bool] = Form(False, description="Whether to embed the content for vector search"),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Add a new source to a notebook specified by name. Supports three types of sources:
    
    - **text**: Provide text content in the `content` field
    - **link**: Provide a URL in the `url` field
    - **upload**: Upload a file using the `file` field
    
    You can also specify transformations to apply and whether to embed the content.
    """
    if not SOURCE_GRAPH_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"The 'content_core' or LLM dependency is missing and is required for source processing. Please install it. Import error: {SOURCE_GRAPH_IMPORT_ERROR}")

    if type not in ["link", "upload", "text"]:
        raise HTTPException(status_code=400, detail="Invalid source type. Must be one of: link, upload, text.")

    # Validate required fields based on type
    if type == "text" and not content:
        raise HTTPException(status_code=400, detail="Content must be provided for text type.")
    elif type == "link" and not url:
        raise HTTPException(status_code=400, detail="URL must be provided for link type.")
    elif type == "upload":
        if not file:
            raise HTTPException(status_code=400, detail="File must be provided for upload type.")
        if not hasattr(file, "filename") or not file.filename:
            raise HTTPException(status_code=400, detail="Invalid file upload: No filename provided.")
        try:
            # Try to read a small part of the file to verify it's valid
            test_content = await file.read(1024)  # Read first 1KB
            await file.seek(0)  # Reset file pointer to beginning
            if not test_content:
                raise HTTPException(status_code=400, detail="Invalid file upload: File appears to be empty.")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid file upload: Unable to read file content. Error: {str(e)}")

    query = f"SELECT * FROM {NOTEBOOK_TABLE} WHERE name = $name"
    bindings = {"name": notebook_name}
    result = await db.query(query, bindings)
    if not result or len(result) == 0:
        raise HTTPException(status_code=404, detail=f"Notebook with name '{notebook_name}' not found")
    notebook = dict(result[0])
    notebook_id = notebook['id']
    if hasattr(notebook_id, 'table_name') and hasattr(notebook_id, 'record_id'):
        notebook_id = f"{notebook_id.table_name}:{notebook_id.record_id}"
    else:
        notebook_id = str(notebook_id)

    req: Dict[str, Any] = {}
    content_settings = ContentSettings()

    # Validate and process based on type
    if type == "text":
        req["content"] = content
    elif type == "link":
        req["url"] = url
    elif type == "upload" and file:
        # Create uploads directory if it doesn't exist
        os.makedirs(UPLOADS_FOLDER, exist_ok=True)
        
        file_name = file.filename
        file_extension = Path(file_name).suffix
        base_name = Path(file_name).stem
        new_path = os.path.join(UPLOADS_FOLDER, file_name)
        counter = 0
        while os.path.exists(new_path):
            counter += 1
            new_file_name = f"{base_name}_{counter}{file_extension}"
            new_path = os.path.join(UPLOADS_FOLDER, new_file_name)
        
        # Save the uploaded file
        file_content = await file.read()
        with open(new_path, "wb") as f:
            f.write(file_content)
            
        req["file_path"] = str(new_path)
        req["delete_source"] = content_settings.auto_delete_files == "yes"

    transformations = []
    if apply_transformations:
        if isinstance(apply_transformations, str):
            names = [n.strip() for n in apply_transformations.split(",") if n.strip()]
            for t in Transformation.get_all():
                if t.name in names:
                    transformations.append(t)
        elif isinstance(apply_transformations, list):
            for t in Transformation.get_all():
                if t.name in apply_transformations:
                    transformations.append(t)
    else:
        transformations = [t for t in Transformation.get_all() if getattr(t, "apply_default", False)]

    state = {
        "content_state": req,
        "notebook_id": notebook_id,
        "apply_transformations": transformations,
        "embed": embed,
    }

    try:
        result = await source_graph.ainvoke(state)
        source = result.get("source")
        if not source:
            raise HTTPException(status_code=500, detail="Source creation failed.")
        
        # Generate title if not present
        title = source.title or ""
        if not title and source.full_text:
            try:
                from open_notebook.graphs.prompt import graph as prompt_graph
                from open_notebook.utils import surreal_clean
                
                # Generate title based on content
                if type == "link" and url:
                    prompt = f"Based on this URL: {url}, provide a concise title (max 10 words) that describes the main topic or content."
                    input_text = url
                elif type == "upload" and hasattr(file, 'filename'):
                    prompt = f"Based on this file: {file.filename}, provide a concise title (max 10 words) that describes the main topic or content."
                    input_text = source.full_text[:500]  # Use first 500 chars for title generation
                else:
                    prompt = "Based on the content below, provide a concise title (max 10 words) that describes the main topic or agenda."
                    input_text = source.full_text[:500]  # Use first 500 chars for title generation
                
                title_result = prompt_graph.invoke(dict(input_text=input_text, prompt=prompt))
                title = surreal_clean(title_result["output"])
                
                # Update the source with the generated title
                if title and title != "Untitled Source":
                    source.title = title
                    source.save()
                    
            except Exception as title_error:
                print(f"Error generating title: {title_error}")
                # Fallback to default title
                if type == "link":
                    title = f"Link: {url[:50]}..." if url else "Untitled Link"
                elif type == "upload":
                    title = f"File: {file.filename}" if hasattr(file, 'filename') else "Untitled File"
                else:
                    title = "Untitled Source"
        
        return SourceResponse(
            id=str(source.id),
            title=title,
            type=type,
            status="completed",
            created=safe_datetime(getattr(source, "created", None)),
            updated=safe_datetime(getattr(source, "updated", None)),
            metadata=getattr(source, "metadata", {}),
            full_text=getattr(source, "full_text", ""),
            notebook_id=notebook_id,
            insights=[i.model_dump() for i in getattr(source, "insights", [])],
            embedded_chunks=getattr(source, "embedded_chunks", 0),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error creating source: {e}")

# --- Keep/Update Listing, Getting, Deleting Endpoints ---
# (No change to list, get, delete endpoints except to ensure they use the domain Source model)

@router.get("/api/v1/notebooks/by-name/{name}/sources", response_model=SourceListResponse)
async def list_sources_for_notebook_by_name(
    name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Lists all sources associated with a specific notebook by name."""
    captured_output = io.StringIO()
    sys.stdout = captured_output

    logs = []
    try:
        logs.append(f"Listing sources for notebook: {name}")
        # First get the notebook by name
        query = f"SELECT * FROM {NOTEBOOK_TABLE} WHERE name = $name"
        bindings = {"name": name}
        result = await db.query(query, bindings)
        logs.append(f"Notebook query result: {result}")
        
        if not result or len(result) == 0:
            logs.append(f"Notebook with name \'{name}\' not found")
            raise HTTPException(status_code=404, detail=f"Notebook with name \'{name}\' not found")
            
        notebook = dict(result[0])
        notebook_id = notebook['id']
        if hasattr(notebook_id, 'table_name') and hasattr(notebook_id, 'record_id'):
            notebook_id = f"{notebook_id.table_name}:{notebook_id.record_id}"
        else:
            notebook_id = str(notebook_id)
        logs.append(f"Found notebook with ID: {notebook_id}")

        # Get all sources in the database for debugging
        all_sources_query = "SELECT * FROM source"
        all_sources = await db.query(all_sources_query)
        logs.append(f"All sources in database: {all_sources}")

        # Get all reference relations for debugging
        all_references_query = "SELECT * FROM reference"
        all_references = await db.query(all_references_query)
        logs.append(f"All reference relations: {all_references}")

        # Query sources for this notebook using the reference relation
        # First get the reference records that point to this notebook
        # The reference structure shows 'out' contains the notebook RecordID
        # We need to create a RecordID object for the query
        from surrealdb import RecordID
        notebook_parts = notebook_id.split(":")
        if len(notebook_parts) >= 2:
            notebook_record_id = RecordID("notebook", notebook_parts[1])
        else:
            logs.append(f"Invalid notebook ID format: {notebook_id}")
            raise HTTPException(status_code=400, detail=f"Invalid notebook ID format: {notebook_id}")
        ref_query = "SELECT in FROM reference WHERE out = $nb_id"
        ref_bindings = {"nb_id": notebook_record_id}
        logs.append(f"Executing reference query: {ref_query}")
        logs.append(f"With bindings: {ref_bindings}")
        ref_result = await db.query(ref_query, ref_bindings)
        logs.append(f"Reference query result: {ref_result}")
        
        if not ref_result or len(ref_result) == 0:
            logs.append("No references found")
            return SourceListResponse(sources=[], logs=logs + captured_output.getvalue().splitlines())
        
        # Extract source IDs from the reference results
        source_ids = []
        for ref in ref_result:
            ref_dict = dict(ref)
            if 'in' in ref_dict:
                source_id = ref_dict['in']
                if hasattr(source_id, 'table_name') and hasattr(source_id, 'record_id'):
                    source_id = f"{source_id.table_name}:{source_id.record_id}"
                source_ids.append(source_id)
        
        logs.append(f"Found source IDs: {source_ids}")
        
        if not source_ids:
            logs.append("No source IDs found")
            return SourceListResponse(sources=[], logs=logs + captured_output.getvalue().splitlines())
        
        # Now get the actual source data for each source ID
        sources = []
        for source_id in source_ids:
            # Query the source by ID
            source_query = f"SELECT * FROM source WHERE id = $source_id"
            source_result = await db.query(source_query, {"source_id": source_id})
            
            if source_result and len(source_result) > 0:
                source_dict = dict(source_result[0])
                # Convert RecordID to string
                source_dict = convert_record_id_to_string(source_dict)
            
            # Handle title from metadata if not directly present
            if not source_dict.get('title'):
                source_dict['title'] = source_dict.get('metadata', {}).get('title', 'Untitled Source')

            # Determine type from asset or metadata
            source_type = "unknown"
            asset_url = source_dict.get('asset', {}).get('url') or ''
            if asset_url.startswith('https://youtu.be'):
                source_type = "youtube"
            elif asset_url:
                source_type = "url"
            elif source_dict.get('full_text'):
                source_type = "text"

            # Get insights for this source
            insights_query = f"""
                SELECT * FROM source_insight
                WHERE source = $source_id
                ORDER BY created DESC
            """
            insights_result = await db.query(insights_query, {"source_id": source_id})
            
            # Convert insights to the expected format
            insights = []
            if insights_result:
                for insight in insights_result:
                    insight_dict = dict(insight)
                    insight_dict = convert_record_id_to_string(insight_dict)
                    insights.append({
                        "id": str(insight_dict.get('id', '')),
                        "insight_type": str(insight_dict.get('insight_type', '')),
                        "content": str(insight_dict.get('content', '')),
                        "created": insight_dict.get('created'),
                        "updated": insight_dict.get('updated'),
                    })

            # Create SourceSummary with all available fields including insights
            sources.append(SourceSummary(
                id=str(source_dict.get('id', '')),
                title=str(source_dict.get('title', '')),
                type=source_type,
                status="completed",  # Default to completed since we have the data
                created=source_dict.get('created'),
                updated=source_dict.get('updated'),
                metadata=source_dict.get('metadata', {}),
                insights=insights
            ))

        logs.append(f"Returning {len(sources)} sources")
        return SourceListResponse(sources=sources, logs=logs + captured_output.getvalue().splitlines())

    except Exception as e:
        logs.append(f"Error listing sources for notebook {name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error listing sources: {e}")
    finally:
        sys.stdout = sys.__stdout__  # Restore stdout correctly

@router.get("/api/v1/notebooks/{notebook_id}/sources", response_model=SourceListResponse)
async def list_sources_for_notebook(
    notebook_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Lists all sources associated with a specific notebook."""
    if ":" not in notebook_id:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notebook ID format.")
    try:
        logs = []
        captured_output = io.StringIO()
        notebook_result = await db.query(f"SELECT * FROM {NOTEBOOK_TABLE} WHERE id = $notebook_id", {"notebook_id": notebook_id})
        if not notebook_result or not notebook_result[0]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Notebook {notebook_id} not found")
        notebook = notebook_result[0]

        # Query sources for this notebook using the reference relation
        # First get the source IDs from the reference table
        ref_query = "SELECT * FROM source WHERE <-reference.in = $nb_id"
        ref_bindings = {"nb_id": notebook_id}
        logs.append(f"Executing reference query: {ref_query}")
        logs.append(f"With bindings: {ref_bindings}")
        ref_result = await db.query(ref_query, ref_bindings)
        logs.append(f"Reference query result: {ref_result}")
        
        if not ref_result or len(ref_result) == 0:
            logs.append("No references found")
            return SourceListResponse(sources=[], logs=logs + captured_output.getvalue().splitlines())
        
        sources = []
        for source in ref_result:
            source_dict = dict(source)
            # Convert RecordID to string
            source_dict = convert_record_id_to_string(source_dict)
            
            # Handle title from metadata if not directly present
            if not source_dict.get('title'):
                source_dict['title'] = source_dict.get('metadata', {}).get('title', 'Untitled Source')

            # Determine type from asset or metadata
            source_type = "unknown"
            asset_url = source_dict.get('asset', {}).get('url') or ''
            if asset_url.startswith('https://youtu.be'):
                source_type = "youtube"
            elif asset_url:
                source_type = "url"
            elif source_dict.get('full_text'):
                source_type = "text"

            # Create SourceSummary with all available fields
            sources.append(SourceSummary(
                id=str(source_dict.get('id', '')),
                title=str(source_dict.get('title', '')),
                type=source_type,
                status="completed",  # Default to completed since we have the data
                created=source_dict.get('created'),
                updated=source_dict.get('updated'),
                metadata=source_dict.get('metadata', {})
            ))

        logs.append(f"Returning {len(sources)} sources")
        return SourceListResponse(sources=sources, logs=logs + captured_output.getvalue().splitlines())

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error listing sources for notebook {notebook_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error listing sources")

@router.get("/api/v1/sources/by-title/{title}", response_model=SourceResponse)
async def get_source_by_title(
    title: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Gets full details of a specific source by its title."""
    # URL decode the title to handle encoded characters
    import urllib.parse
    decoded_title = urllib.parse.unquote(title)
    
    try:
        # Find the source by title
        query = f"""
            SELECT * FROM {SOURCE_TABLE}
            WHERE title = $title
        """
        bindings = {"title": decoded_title}
        result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source with title '{decoded_title}' not found")
        
        source_dict = dict(result[0])
        source_dict = convert_record_id_to_string(source_dict)
        
        # Get insights for this source
        insights_query = f"""
            SELECT * FROM source_insight
            WHERE source = $source_id
            ORDER BY created DESC
        """
        insights_result = await db.query(insights_query, {"source_id": source_dict['id']})
        
        # Convert insights to the expected format
        insights = []
        if insights_result:
            for insight in insights_result:
                insight_dict = dict(insight)
                insight_dict = convert_record_id_to_string(insight_dict)
                insights.append({
                    "id": str(insight_dict.get('id', '')),
                    "insight_type": str(insight_dict.get('insight_type', '')),
                    "content": str(insight_dict.get('content', '')),
                    "created": insight_dict.get('created'),
                    "updated": insight_dict.get('updated'),
                })
        
        # Ensure all fields are properly converted to strings
        source_dict['id'] = str(source_dict.get('id', ''))
        source_dict['title'] = str(source_dict.get('title', ''))
        source_dict['type'] = str(source_dict.get('type', 'unknown'))
        source_dict['status'] = str(source_dict.get('status', 'completed'))
        source_dict['notebook_id'] = str(source_dict.get('notebook_id', ''))
        source_dict['full_text'] = str(source_dict.get('full_text', ''))
        source_dict['insights'] = insights
        
        return SourceResponse(**source_dict)
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error getting source by title {decoded_title}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting source: {e}")

@router.get("/api/v1/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Gets full details of a specific source by its ID."""
    # URL decode the source_id to handle encoded colons
    import urllib.parse
    decoded_source_id = urllib.parse.unquote(source_id)
    
    if ":" not in decoded_source_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source ID format.")
    try:
        # Query source with all fields except insights (insights are in separate table)
        # First try direct record access
        try:
            result = await db.query(f"SELECT * FROM {decoded_source_id}")
            print(f"Direct record access result: {result}")
        except Exception as e:
            print(f"Direct record access failed: {e}")
            # Fallback to table query
            query = f"""
                SELECT id, title, type, status, created, updated, metadata,
                       full_text, notebook_id
                FROM {SOURCE_TABLE}
                WHERE id = $source_id
            """
            bindings = {"source_id": decoded_source_id}
            result = await db.query(query, bindings)
            print(f"Table query result: {result}")
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {decoded_source_id} not found")
            
        source_dict = dict(result[0])
        source_dict = convert_record_id_to_string(source_dict)
        
        # Ensure all fields are properly converted to strings
        source_dict['id'] = str(source_dict.get('id', ''))
        source_dict['title'] = str(source_dict.get('title', ''))
        source_dict['type'] = str(source_dict.get('type', ''))
        source_dict['status'] = str(source_dict.get('status', ''))
        source_dict['notebook_id'] = str(source_dict.get('notebook_id', ''))
        
        # Handle title from metadata if not directly present
        if not source_dict.get('title') or source_dict.get('title') == 'None':
            source_dict['title'] = source_dict.get('metadata', {}).get('title', 'Untitled Source')
        
        # Create domain source object to get insights properly
        from open_notebook.domain.notebook import Source as DomainSource, Asset
        
        asset = None
        if source_dict.get('asset', {}).get('url'):
            asset = Asset(url=source_dict['asset']['url'])
        elif source_dict.get('asset', {}).get('file_path'):
            asset = Asset(file_path=source_dict['asset']['file_path'])
        
        # Convert RecordID to string for the domain source
        source_id_str = str(source_dict.get('id')) if source_dict.get('id') else decoded_source_id
        
        source = DomainSource(
            id=source_id_str,
            asset=asset,
            full_text=source_dict.get('full_text', ''),
            title=source_dict.get('title', 'Untitled Source'),
        )
        
        # Load insights from the database
        try:
            # Create RecordID for the source to match the database format
            from surrealdb import RecordID
            source_record_id = RecordID("source", decoded_source_id.split(":")[1])
            
            insights_query = f"""
                SELECT * FROM source_insight WHERE source = $source_id
            """
            insights_result = await db.query(insights_query, {"source_id": source_record_id})
            print(f"Insights query result for {decoded_source_id}: {insights_result}")
            insights = []
            if insights_result:
                for insight in insights_result:
                    insight_dict = dict(insight)
                    insight_dict = convert_record_id_to_string(insight_dict)
                    
                    # Ensure all insight fields are properly converted to strings
                    insight_dict['id'] = str(insight_dict.get('id', ''))
                    insight_dict['source'] = str(insight_dict.get('source', ''))
                    insight_dict['title'] = str(insight_dict.get('title', ''))
                    insight_dict['content'] = str(insight_dict.get('content', ''))
                    insight_dict['type'] = str(insight_dict.get('type', ''))
                    
                    insights.append(insight_dict)
        except Exception as e:
            print(f"Error loading insights for source {decoded_source_id}: {e}")
            insights = []
            
        # Create full source response
        return SourceResponse(
            id=str(source_dict.get('id', '')),
            title=str(source_dict.get('title', '')),
            type=str(source_dict.get('type', '')),
            status=str(source_dict.get('status', '')),
            created=safe_datetime(source_dict.get('created')),
            updated=safe_datetime(source_dict.get('updated')),
            metadata=source_dict.get('metadata', {}),
            full_text=source_dict.get('full_text', ''),
            notebook_id=str(source_dict.get('notebook_id', '')),
            insights=insights,
            embedded_chunks=getattr(source, "embedded_chunks", 0)
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error getting source {decoded_source_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting source: {e}")



@router.delete("/api/v1/sources/{source_id}", response_model=StatusResponse)
async def delete_source(
    source_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Deletes a source. Note: Does not currently delete associated insights/embeddings."""
    # URL decode the source_id to handle encoded colons
    import urllib.parse
    decoded_source_id = urllib.parse.unquote(source_id)
    
    if ":" not in decoded_source_id:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source ID format.")
    try:
        # Delete the source
        result = await db.delete(decoded_source_id)
        if result:
            return StatusResponse(status="success", message=f"Source {decoded_source_id} deleted successfully")
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {decoded_source_id} not found")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error deleting source {source_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error deleting source: {e}")

@router.delete("/api/v1/sources/by-title/{title}", response_model=StatusResponse)
async def delete_source_by_title(
    title: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Deletes a source by its title. Note: Does not currently delete associated insights/embeddings."""
    try:
        # Find the source by title - try multiple approaches
        query = f"SELECT id FROM {SOURCE_TABLE} WHERE title = $title"
        bindings = {"title": title}
        result = await db.query(query, bindings)
        
        # If not found, try with a more flexible query
        if not result or len(result) == 0:
            query = f"SELECT id FROM {SOURCE_TABLE} WHERE title CONTAINS $title"
            result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source with title \'{title}\' not found")
        
        # Get the source ID
        source_id = result[0].get('id')
        if hasattr(source_id, 'table_name') and hasattr(source_id, 'record_id'):
            source_id = f"{source_id.table_name}:{source_id.record_id}"
        else:
            source_id = str(source_id)
        
        # Delete the source
        delete_result = await db.delete(source_id)
        if delete_result:
            return StatusResponse(status="success", message=f"Source \'{title}\' deleted successfully")
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source \'{title}\' not found")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error deleting source with title \'{title}\' : {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error deleting source: {e}")

@router.put("/api/v1/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: str,
    data: dict = Body(...),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Updates a source by its ID."""
    # URL decode the source_id to handle encoded colons
    import urllib.parse
    decoded_source_id = urllib.parse.unquote(source_id)
    
    if ":" not in decoded_source_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source ID format.")
    
    try:
        # Check if source exists
        try:
            result = await db.query(f"SELECT * FROM {decoded_source_id}")
            if not result or len(result) == 0:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {decoded_source_id} not found")
        except Exception as e:
            print(f"Error checking source existence: {e}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {decoded_source_id} not found")
        
        # Update the source
        update_data = {k: v for k, v in data.items() if v is not None}
        if not update_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid fields to update")
        
        # Add updated timestamp
        update_data['updated'] = datetime.now()
        
        # Perform the update
        update_result = await db.update(decoded_source_id, update_data)
        
        if update_result:
            # Return the updated source
            updated_source = await db.query(f"SELECT * FROM {decoded_source_id}")
            if updated_source and len(updated_source) > 0:
                source_dict = dict(updated_source[0])
                source_dict = convert_record_id_to_string(source_dict)
                
                # Ensure all required fields are present and properly converted
                if 'id' in source_dict and hasattr(source_dict['id'], 'table_name'):
                    # Handle different RecordID structures
                    if hasattr(source_dict['id'], 'record_id'):
                        source_dict['id'] = f"{source_dict['id'].table_name}:{source_dict['id'].record_id}"
                    else:
                        source_dict['id'] = str(source_dict['id'])
                if 'type' not in source_dict:
                    source_dict['type'] = 'unknown'
                if 'status' not in source_dict:
                    source_dict['status'] = 'completed'
                if 'title' not in source_dict:
                    source_dict['title'] = 'Untitled'
                
                return SourceResponse(**source_dict)
        
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update source")
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error updating source {decoded_source_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error updating source: {e}")

@router.post("/api/v1/sources/{source_id}/generate-title", response_model=dict)
async def generate_source_title(
    source_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Generate an AI-powered title for a source based on its content.
    This endpoint can be used to regenerate titles for existing sources.
    """
    if not SOURCE_GRAPH_AVAILABLE:
        raise HTTPException(
            status_code=500, 
            detail=f"The 'content_core' or LLM dependency is missing and is required for title generation. Import error: {SOURCE_GRAPH_IMPORT_ERROR}"
        )

    # URL decode the source_id to handle encoded colons
    import urllib.parse
    decoded_source_id = urllib.parse.unquote(source_id)
    
    if ":" not in decoded_source_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source ID format.")
    
    try:
        # Get the source from the database
        try:
            result = await db.query(f"SELECT * FROM {decoded_source_id}")
        except Exception:
            query = f"SELECT * FROM {SOURCE_TABLE} WHERE id = $source_id"
            bindings = {"source_id": decoded_source_id}
            result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source with ID '{decoded_source_id}' not found")
        
        source_dict = dict(result[0])
        source_dict = convert_record_id_to_string(source_dict)
        
        # Create domain source object
        from open_notebook.domain.notebook import Source as DomainSource, Asset
        
        asset = None
        if source_dict.get('asset', {}).get('url'):
            asset = Asset(url=source_dict['asset']['url'])
        elif source_dict.get('asset', {}).get('file_path'):
            asset = Asset(file_path=source_dict['asset']['file_path'])
        
        source = DomainSource(
            id=decoded_source_id,
            asset=asset,
            full_text=source_dict.get('full_text', ''),
            title=source_dict.get('title', 'Untitled Source'),
        )
        
        # Generate title using AI
        try:
            from open_notebook.graphs.prompt import graph as prompt_graph
            from open_notebook.utils import surreal_clean
            
            # Determine content type and generate appropriate prompt
            if source.asset and source.asset.url:
                prompt = f"Based on this URL: {source.asset.url}, provide a concise title (max 10 words) that describes the main topic or content."
                input_text = source.asset.url
            elif source.asset and source.asset.file_path:
                filename = source.asset.file_path.split('/')[-1] if source.asset.file_path else "file"
                prompt = f"Based on this file: {filename}, provide a concise title (max 10 words) that describes the main topic or content."
                input_text = source.full_text[:500] if source.full_text else filename
            else:
                prompt = "Based on the content below, provide a concise title (max 10 words) that describes the main topic or agenda."
                input_text = source.full_text[:500] if source.full_text else "No content available"
            
            title_result = prompt_graph.invoke(dict(input_text=input_text, prompt=prompt))
            generated_title = surreal_clean(title_result["output"])
            
            # Update the source with the generated title
            if generated_title and generated_title != "Untitled Source":
                source.title = generated_title
                source.save()
                
                return {
                    "source_id": decoded_source_id,
                    "old_title": source_dict.get('title', ''),
                    "new_title": generated_title,
                    "success": True
                }
            else:
                return {
                    "source_id": decoded_source_id,
                    "old_title": source_dict.get('title', ''),
                    "new_title": source_dict.get('title', ''),
                    "success": False,
                    "error": "Failed to generate meaningful title"
                }
                
        except Exception as title_error:
            print(f"Error generating title: {title_error}")
            return {
                "source_id": decoded_source_id,
                "old_title": source_dict.get('title', ''),
                "new_title": source_dict.get('title', ''),
                "success": False,
                "error": str(title_error)
            }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating title for source '{decoded_source_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Internal server error generating title: {e}"
        )

@router.put("/api/v1/sources/by-title/{title}", response_model=SourceResponse)
async def update_source_by_title(
    title: str,
    data: dict = Body(...),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Updates a source by its title."""
    try:
        # Find the source by title
        query = f"SELECT id FROM {SOURCE_TABLE} WHERE title = $title"
        bindings = {"title": title}
        result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source with title \'{title}\' not found")
        
        # Get the source ID
        source_id = result[0].get('id')
        if hasattr(source_id, 'table_name') and hasattr(source_id, 'record_id'):
            source_id = f"{source_id.table_name}:{source_id.record_id}"
        else:
            source_id = str(source_id)
        
        # Update the source
        update_data = {k: v for k, v in data.items() if v is not None}
        if not update_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid fields to update")
        
        # Add updated timestamp
        update_data['updated'] = datetime.now()
        
        # Perform the update
        update_result = await db.update(source_id, update_data)
        
        if update_result:
            # Return the updated source
            updated_source = await db.query(f"SELECT * FROM {source_id}")
            if updated_source and len(updated_source) > 0:
                source_dict = dict(updated_source[0])
                source_dict = convert_record_id_to_string(source_dict)
                
                # Ensure all required fields are present and properly converted
                if 'id' in source_dict and hasattr(source_dict['id'], 'table_name'):
                    # Handle different RecordID structures
                    if hasattr(source_dict['id'], 'record_id'):
                        source_dict['id'] = f"{source_dict['id'].table_name}:{source_dict['id'].record_id}"
                    else:
                        source_dict['id'] = str(source_dict['id'])
                if 'type' not in source_dict:
                    source_dict['type'] = 'unknown'
                if 'status' not in source_dict:
                    source_dict['status'] = 'completed'
                if 'title' not in source_dict:
                    source_dict['title'] = 'Untitled'
                
                return SourceResponse(**source_dict)
        
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update source")
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error updating source with title \'{title}\': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error updating source: {e}")

@router.get("/notebooks/by-name/{notebook_name}", response_model=List[SourceSummary])
async def list_sources_by_notebook_name(
    notebook_name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Lists all sources in a notebook specified by name using a direct graph traversal."""
    try:
        # This query traverses from the notebook, back over the incoming 'reference' edge,
        # and then back to the source records, fetching them completely.
        query = """
            SELECT * FROM <-reference<-source
            WHERE id = (SELECT VALUE id FROM notebook WHERE name = $name LIMIT 1)
            ORDER BY created DESC;
        """
        sources_result = await db.query(query, {"name": notebook_name})

        # The result from this type of query is a list where the first element
        # is another list containing the actual source dictionaries.
        if not sources_result or not sources_result[0]:
            return []

        sources_list = sources_result[0]

        return [SourceSummary(**dict(s)) for s in sources_list]

    except Exception as e:
        print(f"Error listing sources for notebook {notebook_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

def safe_datetime(val):
    import builtins
    from datetime import datetime
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    if hasattr(val, 'timestamp'):
        ts = val.timestamp // 1_000_000_000
        return datetime.utcfromtimestamp(ts).isoformat()
    if isinstance(val, str) and 'DateTimeCompact' in val:
        import re
        match = re.search(r'timestamp=(\d+)', val)
        if match:
            ts = builtins.int(match.group(1)) // 1_000_000_000
            return datetime.utcfromtimestamp(ts).isoformat()
        return None
    if isinstance(val, int) and val > 1e12:
        ts = val // 1_000_000_000
        return datetime.utcfromtimestamp(ts).isoformat()
    return None

# --- Transformation Running Endpoint ---

class RunTransformationsRequest(BaseModel):
    transformation_ids: List[str]
    llm_id: Optional[str] = None

class TransformationResult(BaseModel):
    transformation_id: str
    transformation_name: str
    output: str
    llm_used: str
    success: bool
    error: Optional[str] = None

class RunTransformationsResponse(BaseModel):
    source_id: str
    results: List[TransformationResult]
    total_applied: int
    total_failed: int

@router.post("/api/v1/sources/by-title/{source_title}/run-transformations", response_model=RunTransformationsResponse)
async def run_transformations_on_source_by_title(
    source_title: str,
    transformation_names: str = Query(..., description="Comma-separated list of transformation names to apply"),
    llm_id: Optional[str] = Query(None, description="Optional LLM model ID to use"),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Run AI transformations on a specific source by its title.
    
    This endpoint applies the specified transformations to the source content
    and returns the results. The transformations are processed using the
    transformation graph and the results are stored as insights on the source.
    
    Available transformations: Analyze Paper, Key Insights, Dense Summary, 
    Reflection Questions, Table of Contents, Simple Summary
    """
    if not SOURCE_GRAPH_AVAILABLE:
        raise HTTPException(
            status_code=500, 
            detail=f"The 'content_core' or LLM dependency is missing and is required for transformation processing. Import error: {SOURCE_GRAPH_IMPORT_ERROR}"
        )

    try:
        # Get the source from the database by title
        query = f"SELECT * FROM {SOURCE_TABLE} WHERE title = $source_title"
        bindings = {"source_title": source_title}
        result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source with title '{source_title}' not found")
        
        source_dict = dict(result[0])
        source_dict = convert_record_id_to_string(source_dict)
        source_id = source_dict.get('id')
        
        # Ensure source_id is a string
        if hasattr(source_id, 'table_name') and hasattr(source_id, 'record_id'):
            source_id = f"{source_id.table_name}:{source_id.record_id}"
        else:
            source_id = str(source_id)
        
        # Create domain source object
        from open_notebook.domain.notebook import Source as DomainSource, Asset
        
        asset = None
        if source_dict.get('asset', {}).get('url'):
            asset = Asset(url=source_dict['asset']['url'])
        elif source_dict.get('asset', {}).get('file_path'):
            asset = Asset(file_path=source_dict['asset']['file_path'])
        
        source = DomainSource(
            id=source_id,
            asset=asset,
            full_text=source_dict.get('full_text', ''),
            title=source_dict.get('title', 'Untitled Source'),
        )
        
        # Parse transformation names from query parameter
        transformation_names_list = [name.strip() for name in transformation_names.split(",") if name.strip()]
        
        # Get the transformations by name
        transformations = []
        for transformation_name in transformation_names_list:
            transformation = None
            for t in Transformation.get_all():
                if t.name == transformation_name:
                    transformation = t
                    break
            
            if not transformation:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Transformation '{transformation_name}' not found. Available transformations: {[t.name for t in Transformation.get_all()]}"
                )
            transformations.append(transformation)
        
        # Import the transformation graph
        try:
            from open_notebook.graphs.transformation import graph as transform_graph
        except ImportError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to import transformation graph: {e}"
            )
        
        results = []
        total_applied = 0
        total_failed = 0
        
        # Run each transformation
        for transformation in transformations:
            try:
                # Prepare the input for the transformation graph
                transform_input = {
                    "input_text": source.full_text,
                    "transformation": transformation,
                    "source": source
                }
                
                # Configure the model if specified
                config = {}
                if llm_id:
                    config["configurable"] = {"model_id": llm_id}
                
                # Run the transformation
                transform_result = await transform_graph.ainvoke(transform_input, config)
                
                # Add the insight to the source
                source.add_insight(transformation.title, transform_result["output"])
                
                # Get the model used (default to transformation model if not specified)
                model_used = llm_id or "default_transformation_model"
                
                results.append(TransformationResult(
                    transformation_id=str(transformation.id),
                    transformation_name=transformation.name,
                    output=transform_result["output"],
                    llm_used=model_used,
                    success=True
                ))
                total_applied += 1
                
            except Exception as e:
                print(f"Error running transformation {transformation.name}: {e}")
                results.append(TransformationResult(
                    transformation_id=str(transformation.id),
                    transformation_name=transformation.name,
                    output="",
                    llm_used="",
                    success=False,
                    error=str(e)
                ))
                total_failed += 1
        
        # Save the source to persist the insights
        source.save()
        
        return RunTransformationsResponse(
            source_id=source_id,
            results=results,
            total_applied=total_applied,
            total_failed=total_failed
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error running transformations on source '{source_title}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Internal server error running transformations: {e}"
        )

@router.post("/api/v1/sources/{source_id}/run-transformations", response_model=RunTransformationsResponse)
async def run_transformations_on_source_by_id(
    source_id: str,
    transformation_names: str = Query(..., description="Comma-separated list of transformation names to apply"),
    llm_id: Optional[str] = Query(None, description="Optional LLM model ID to use"),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Run AI transformations on a specific source by its ID.
    
    This endpoint applies the specified transformations to the source content
    and returns the results. The transformations are processed using the
    transformation graph and the results are stored as insights on the source.
    
    Available transformations: Analyze Paper, Key Insights, Dense Summary, 
    Reflection Questions, Table of Contents, Simple Summary
    """
    if not SOURCE_GRAPH_AVAILABLE:
        raise HTTPException(
            status_code=500, 
            detail=f"The 'content_core' or LLM dependency is missing and is required for transformation processing. Import error: {SOURCE_GRAPH_IMPORT_ERROR}"
        )

    # URL decode the source_id to handle encoded colons
    import urllib.parse
    decoded_source_id = urllib.parse.unquote(source_id)

    try:
        # Get the source from the database by ID - use direct record access
        try:
            # Try direct record access first (more reliable)
            result = await db.query(f"SELECT * FROM {decoded_source_id}")
        except Exception:
            # Fallback to table query
            query = f"SELECT * FROM {SOURCE_TABLE} WHERE id = $source_id"
            bindings = {"source_id": decoded_source_id}
            result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source with ID '{decoded_source_id}' not found")
        
        source_dict = dict(result[0])
        source_dict = convert_record_id_to_string(source_dict)
        
        # Ensure all fields are properly converted to strings
        source_dict['id'] = str(source_dict.get('id', ''))
        source_dict['title'] = str(source_dict.get('title', ''))
        source_dict['type'] = str(source_dict.get('type', ''))
        source_dict['status'] = str(source_dict.get('status', ''))
        source_dict['notebook_id'] = str(source_dict.get('notebook_id', ''))
        
        # Create domain source object
        from open_notebook.domain.notebook import Source as DomainSource, Asset
        
        asset = None
        if source_dict.get('asset', {}).get('url'):
            asset = Asset(url=source_dict['asset']['url'])
        elif source_dict.get('asset', {}).get('file_path'):
            asset = Asset(file_path=source_dict['asset']['file_path'])
        
        source = DomainSource(
            id=source_id,
            asset=asset,
            full_text=source_dict.get('full_text', ''),
            title=source_dict.get('title', 'Untitled Source'),
        )
        
        # Parse transformation names from query parameter
        transformation_names_list = [name.strip() for name in transformation_names.split(",") if name.strip()]
        
        # Get the transformations by name
        transformations = []
        for transformation_name in transformation_names_list:
            transformation = None
            for t in Transformation.get_all():
                if t.name == transformation_name:
                    transformation = t
                    break
            
            if not transformation:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Transformation '{transformation_name}' not found. Available transformations: {[t.name for t in Transformation.get_all()]}"
                )
            transformations.append(transformation)
        
        # Import the transformation graph
        try:
            from open_notebook.graphs.transformation import graph as transform_graph
        except ImportError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to import transformation graph: {e}"
            )
        
        results = []
        total_applied = 0
        total_failed = 0
        
        # Run each transformation
        for transformation in transformations:
            try:
                # Prepare the input for the transformation graph
                transform_input = {
                    "input_text": source.full_text,
                    "transformation": transformation,
                    "source": source
                }
                
                # Configure the model if specified
                config = {}
                if llm_id:
                    config["configurable"] = {"model_id": llm_id}
                
                # Run the transformation
                transform_result = await transform_graph.ainvoke(transform_input, config)
                
                # Add the insight to the source
                source.add_insight(transformation.title, transform_result["output"])
                
                # Get the model used (default to transformation model if not specified)
                model_used = llm_id or "default_transformation_model"
                
                results.append(TransformationResult(
                    transformation_id=str(transformation.id),
                    transformation_name=transformation.name,
                    output=transform_result["output"],
                    llm_used=model_used,
                    success=True
                ))
                total_applied += 1
                
            except Exception as e:
                print(f"Error running transformation {transformation.name}: {e}")
                results.append(TransformationResult(
                    transformation_id=str(transformation.id),
                    transformation_name=transformation.name,
                    output="",
                    llm_used="",
                    success=False,
                    error=str(e)
                ))
                total_failed += 1
        
        # Save the source to persist the insights
        source.save()
        
        return RunTransformationsResponse(
            source_id=decoded_source_id,
            results=results,
            total_applied=total_applied,
            total_failed=total_failed
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error running transformations on source '{decoded_source_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Internal server error running transformations: {e}"
        )

@router.post("/api/v1/sources/{source_id}/insights/{insight_id}/save-as-note", response_model=Note, status_code=status.HTTP_201_CREATED)
async def save_insight_as_note(
    source_id: str,
    insight_id: str,
    notebook_id: str = Query(..., description="Notebook ID to save the note to"),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Save a source insight as a note in the specified notebook.
    This replicates the functionality from Streamlit's save_as_note method.
    """
    try:
        # URL decode the source_id to handle encoded colons
        import urllib.parse
        decoded_source_id = urllib.parse.unquote(source_id)
        decoded_insight_id = urllib.parse.unquote(insight_id)
        
        print(f"💾 Saving insight {decoded_insight_id} from source {decoded_source_id} as note in notebook {notebook_id}")
        
        # Get the source to get its title
        source_query = f"SELECT * FROM {decoded_source_id}"
        source_result = await db.query(source_query)
        
        if not source_result or len(source_result) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source with id {decoded_source_id} not found")
        
        source_dict = dict(source_result[0])
        source_dict = convert_record_id_to_string(source_dict)
        source_title = source_dict.get('title', 'Unknown Source')
        
        # Get the insight
        insight_query = f"SELECT * FROM {decoded_insight_id}"
        insight_result = await db.query(insight_query)
        
        if not insight_result or len(insight_result) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Insight with id {decoded_insight_id} not found")
        
        insight_dict = dict(insight_result[0])
        insight_dict = convert_record_id_to_string(insight_dict)
        
        insight_type = insight_dict.get('insight_type', 'Insight')
        insight_content = insight_dict.get('content', '')
        
        # Create note title following the same pattern as Streamlit
        note_title = f"{insight_type} from source {source_title}"
        
        # Create the note using the existing note creation logic
        note_data = {
            "title": note_title,
            "content": insight_content,
            "note_type": "human",
            "created": datetime.utcnow(),
            "updated": datetime.utcnow(),
            "embedding": []
        }
        
        # Create the note
        created_notes = await db.create("note", note_data)
        if not created_notes:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create note")
        
        created_note = created_notes[0] if isinstance(created_notes, list) else created_notes
        note_id = convert_record_id_to_string(created_note["id"])
        print(f"✅ Created note {note_id} with title: {note_title}")
        
        # Create artifact relationship to link note to notebook
        try:
            await link_note_to_notebook(db, note_id, notebook_id)
            print(f"✅ Linked note {note_id} to notebook {notebook_id}")
        except Exception as e:
            print(f"❌ Failed to link note to notebook: {str(e)}")
            # Don't fail the entire operation, but log the error
        
        # Create and update embedding if content is provided
        if insight_content:
            try:
                embedding = await create_note_embedding(db, note_id, insight_content)
                if embedding:
                    # Update the note with the embedding
                    await db.merge(note_id, {"embedding": embedding})
                    note_data["embedding"] = embedding
            except Exception as e:
                logger.warning(f"Failed to create embedding for note {note_id}: {str(e)}")
                # Continue even if embedding creation fails
        
        # Convert and return the created note
        converted_note = convert_record_id_to_string(created_note)
        response_data = {
            "id": str(converted_note.get("id")),
            "title": converted_note.get("title"),
            "content": converted_note.get("content"),
            "note_type": converted_note.get("note_type", "human"),
            "created": converted_note.get("created"),
            "updated": converted_note.get("updated"),
            "embedding": converted_note.get("embedding", [])
        }
        
        return Note(**response_data)
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error saving insight as note: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error saving insight as note: {e}")