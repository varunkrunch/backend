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
    Source, SourceSummary, StatusResponse, TaskStatus, SourceResponse
)
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
        return SourceResponse(
            id=str(source.id),
            title=source.title or "",
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
        return SourceResponse(
            id=str(source.id),
            title=source.title or "",
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
            if source_dict.get('asset', {}).get('url', '').startswith('https://youtu.be'):
                source_type = "youtube"
            elif source_dict.get('asset', {}).get('url'):
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

    except Exception as e:
        logs.append(f"Error listing sources for notebook {name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error listing sources: {e}")
    finally:
        sys.stdout = sys.__stdout__  # Restore stdout correctly

@router.get("/api/v1/notebooks/{notebook_id}/sources", response_model=List[SourceSummary])
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
            if source_dict.get('asset', {}).get('url', '').startswith('https://youtu.be'):
                source_type = "youtube"
            elif source_dict.get('asset', {}).get('url'):
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

@router.get("/api/v1/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Gets full details of a specific source by its ID."""
    if ":" not in source_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source ID format.")
    try:
        # Query source with all fields including insights and embeddings
        query = f"""
            SELECT id, title, type, status, created, updated, metadata,
                   full_text, notebook_id, insights, embedded_chunks
            FROM {SOURCE_TABLE}
            WHERE id = $source_id
        """
        bindings = {"source_id": source_id}
        result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {source_id} not found")
            
        source_dict = dict(result[0])
        source_dict = convert_record_id_to_string(source_dict)
        
        # Handle title from metadata if not directly present
        if not source_dict.get('title'):
            source_dict['title'] = source_dict.get('metadata', {}).get('title', 'Untitled Source')
            
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
            insights=source_dict.get('insights', []),
            embedded_chunks=source_dict.get('embedded_chunks', 0)
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error getting source {source_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting source: {e}")

@router.delete("/api/v1/sources/{source_id}", response_model=StatusResponse)
async def delete_source(
    source_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Deletes a source. Note: Does not currently delete associated insights/embeddings."""
    if ":" not in source_id:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source ID format.")
    try:
        # Delete the source
        result = await db.delete(source_id)
        if result:
            return StatusResponse(status="success", message=f"Source {source_id} deleted successfully")
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {source_id} not found")
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