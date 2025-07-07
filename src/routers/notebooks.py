from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from datetime import datetime

from surrealdb import AsyncSurreal

from ..database import get_db_connection
from ..models import (
    Notebook, NotebookCreate, NotebookUpdate, NotebookSummary, StatusResponse, NoteResponse, NotebookWithNotesResponse, SourceSummary
)

# Create a router for notebook-related endpoints
router = APIRouter(
    prefix="/api/v1/notebooks",
    tags=["Notebooks"],
)

# Define the table name for notebooks in SurrealDB
NOTEBOOK_TABLE = "notebook"

def convert_record_id_to_string(data):
    """Convert SurrealDB RecordID objects to strings in the response data."""
    if isinstance(data, dict):
        return {k: convert_record_id_to_string(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_record_id_to_string(item) for item in data]
    elif hasattr(data, 'table_name') and hasattr(data, 'record_id'):
        # This is a RecordID object
        return f"{data.table_name}:{data.record_id}"
    elif isinstance(data, str):
        return data
    elif data is None:
        return data
    else:
        # For any other type, try to convert to string
        return str(data)

@router.post("", response_model=Notebook, status_code=status.HTTP_201_CREATED)
async def create_notebook(
    notebook_data: NotebookCreate,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Creates a new notebook in the database."""
    try:
        # Check if notebook with same name already exists
        query = f"SELECT * FROM {NOTEBOOK_TABLE} WHERE name = $name"
        bindings = {"name": notebook_data.name}
        existing = await db.query(query, bindings)
        if existing and len(existing) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Notebook with name '{notebook_data.name}' already exists"
            )

        # Add timestamps manually if not handled by SurrealDB automatically
        data_to_create = notebook_data.model_dump()
        data_to_create["created"] = datetime.utcnow()
        data_to_create["updated"] = datetime.utcnow()
        data_to_create["archived"] = False

        created_notebooks = await db.create(NOTEBOOK_TABLE, data_to_create)

        if created_notebooks and isinstance(created_notebooks, list) and len(created_notebooks) > 0:
            return convert_record_id_to_string(created_notebooks[0])
        elif created_notebooks: # Handle potential single object return
             return convert_record_id_to_string(created_notebooks)
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create notebook in DB or empty response")
    except Exception as e:
        print(f"Error creating notebook: {e}") # Log the error
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error during notebook creation: {e}")

@router.get("", response_model=List[NotebookSummary])
async def list_notebooks(
    archived: Optional[str] = Query(None, description="Filter by archived status: true, false, or all"),
    sort_by: Optional[str] = Query("updated", description="Field to sort by"),
    order: Optional[str] = Query("desc", description="Sort order: asc or desc"),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Lists all notebooks, with optional filtering and sorting."""
    try:
        query = f"SELECT * FROM {NOTEBOOK_TABLE}"
        where_clauses = []
        
        if archived and archived.lower() != "all":
            is_archived = archived.lower() == "true"
            where_clauses.append(f"archived = {str(is_archived).lower()}")
        
        if where_clauses:
            query = f"SELECT * FROM {NOTEBOOK_TABLE} WHERE " + " AND ".join(where_clauses)

        # Basic validation for sort fields to prevent injection
        allowed_sort_fields = ["name", "created", "updated", "archived"]
        if sort_by not in allowed_sort_fields:
            sort_by = "updated" # Default sort field
        
        allowed_order = ["asc", "desc"]
        if order.lower() not in allowed_order:
            order = "desc" # Default order

        query += f" ORDER BY {sort_by} {order.upper()}"

        result = await db.query(query)
        print(f"Query result: {result}")
        # SurrealDB query returns a list of dicts, but 'id' may be a RecordID object
        notebooks = []
        for nb in (result if result is not None else []):
            nb = dict(nb)
            if hasattr(nb.get('id', None), 'table_name') and hasattr(nb.get('id', None), 'record_id'):
                nb['id'] = f"{nb['id'].table_name}:{nb['id'].record_id}"
            elif nb.get('id', None) is not None:
                nb['id'] = str(nb['id'])
            notebooks.append(nb)
        return convert_record_id_to_string(notebooks)

    except Exception as e:
        print(f"Error listing notebooks: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error listing notebooks: {e}")

@router.get("/by-name/{name}", response_model=NotebookWithNotesResponse)
async def get_notebook_by_name(
    name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Gets details of a specific notebook by its name, including notes and sources."""
    try:
        query = f"SELECT * FROM {NOTEBOOK_TABLE} WHERE name = $name"
        bindings = {"name": name}
        result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail=f"Notebook with name '{name}' not found")
            
        notebook = dict(result[0])
        notebook_id = notebook['id']
        if hasattr(notebook_id, 'table_name') and hasattr(notebook_id, 'record_id'):
            notebook_id = f"{notebook_id.table_name}:{notebook_id.record_id}"
        else:
            notebook_id = str(notebook_id)

        # Fetch notes for this notebook
        notes_query = f"""
            SELECT id, title, content, created, updated, note_type, metadata, embedding
            FROM note
            WHERE notebook_id = $nb_id
            ORDER BY updated DESC
        """
        notes_result = await db.query(notes_query, {"nb_id": notebook_id})
        notes = []
        for note in notes_result or []:
            note_dict = dict(note)
            # Convert note id to string if it's a RecordID
            if hasattr(note_dict.get('id', None), 'table_name') and hasattr(note_dict.get('id', None), 'record_id'):
                note_dict['id'] = f"{note_dict['id'].table_name}:{note_dict['id'].record_id}"
            elif note_dict.get('id', None) is not None:
                note_dict['id'] = str(note_dict['id'])
            notes.append(NoteResponse(
                id=str(note_dict.get("id", "")),
                title=str(note_dict.get("title", "")),
                content=str(note_dict.get("content", "")),
                created=note_dict.get("created"),
                updated=note_dict.get("updated"),
                note_type=str(note_dict.get("note_type", "human")),
                metadata=note_dict.get("metadata", {}),
                embedding=note_dict.get("embedding", [])
            ))

        # Fetch sources for this notebook using the reference relation
        sources_query = f"""
            SELECT id, title, type, status, created, updated, metadata
            FROM (
                SELECT in as source FROM reference WHERE out = $nb_id
                FETCH source
            )
            ORDER BY created DESC
        """
        sources_result = await db.query(sources_query, {"nb_id": notebook_id})
        sources = []
        for source in sources_result or []:
            source_dict = dict(source)
            # Convert source id to string if it's a RecordID
            if hasattr(source_dict.get('id', None), 'table_name') and hasattr(source_dict.get('id', None), 'record_id'):
                source_dict['id'] = f"{source_dict['id'].table_name}:{source_dict['id'].record_id}"
            elif source_dict.get('id', None) is not None:
                source_dict['id'] = str(source_dict['id'])
            
            # Handle title from metadata if not directly present
            if not source_dict.get('title'):
                source_dict['title'] = source_dict.get('metadata', {}).get('title', 'Untitled Source')
            
            sources.append(SourceSummary(
                id=str(source_dict.get("id", "")),
                title=str(source_dict.get("title", "")),
                type=str(source_dict.get("type", "")),
                status=str(source_dict.get("status", "")),
                created=source_dict.get("created"),
                updated=source_dict.get("updated"),
                metadata=source_dict.get("metadata", {})
            ))

        # Create the response with string IDs
        return NotebookWithNotesResponse(
            id=str(notebook_id),  # Ensure ID is string
            name=notebook["name"],
            description=notebook["description"],
            created=notebook["created"],
            updated=notebook["updated"],
            archived=notebook["archived"],
            metadata=notebook.get("metadata", {}),
            notes=notes,
            sources=sources,
            chat_sessions=[]  # Add chat sessions if needed
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error getting notebook by name {name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting notebook: {e}")

@router.get("/{notebook_id}", response_model=NotebookWithNotesResponse)
async def get_notebook(
    notebook_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Gets details of a specific notebook by its ID, including notes and sources."""
    # Accept both 'id' and 'notebook:id' formats
    if ":" not in notebook_id:
        notebook_id = f"notebook:{notebook_id}"
    try:
        result = await db.select(notebook_id)
        if isinstance(result, list):
            if result:
                notebook = dict(result[0])
            else:
                raise HTTPException(status_code=404, detail=f"Notebook with id {notebook_id} not found")
        elif result:
            notebook = dict(result)
        else:
            raise HTTPException(status_code=404, detail=f"Notebook with id {notebook_id} not found")

        # Fetch notes for this notebook
        notes_query = f"""
            SELECT id, title, content, created, updated, note_type, metadata, embedding
            FROM note
            WHERE notebook_id = $nb_id
            ORDER BY updated DESC
        """
        notes_result = await db.query(notes_query, {"nb_id": notebook_id})
        notes = [
            NoteResponse(
                id=str(note.get("id", "")),
                title=str(note.get("title", "")),
                content=str(note.get("content", "")),
                created=note.get("created"),
                updated=note.get("updated"),
                note_type=str(note.get("note_type", "human")),
                metadata=note.get("metadata", {}),
                embedding=note.get("embedding", [])
            )
            for note in notes_result or []
        ]

        # Fetch sources for this notebook using the reference relation
        sources_query = f"""
            SELECT id, title, type, status, created, updated, metadata
            FROM (
                SELECT in as source FROM reference WHERE out = $nb_id
                FETCH source
            )
            ORDER BY created DESC
        """
        sources_result = await db.query(sources_query, {"nb_id": notebook_id})
        sources = []
        for source in sources_result or []:
            source_dict = dict(source)
            # Convert source id to string if it's a RecordID
            if hasattr(source_dict.get('id', None), 'table_name') and hasattr(source_dict.get('id', None), 'record_id'):
                source_dict['id'] = f"{source_dict['id'].table_name}:{source_dict['id'].record_id}"
            elif source_dict.get('id', None) is not None:
                source_dict['id'] = str(source_dict['id'])
            
            # Handle title from metadata if not directly present
            if not source_dict.get('title'):
                source_dict['title'] = source_dict.get('metadata', {}).get('title', 'Untitled Source')
            
            sources.append(SourceSummary(
                id=str(source_dict.get("id", "")),
                title=str(source_dict.get("title", "")),
                type=str(source_dict.get("type", "")),
                status=str(source_dict.get("status", "")),
                created=source_dict.get("created"),
                updated=source_dict.get("updated"),
                metadata=source_dict.get("metadata", {})
            ))

        return NotebookWithNotesResponse(
            name=notebook["name"],
            description=notebook["description"],
            id=notebook["id"],
            created=notebook["created"],
            updated=notebook["updated"],
            archived=notebook["archived"],
            metadata=notebook.get("metadata", {}),
            notes=notes,
            sources=sources,
            chat_sessions=[]
        )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error getting notebook {notebook_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting notebook: {e}")

@router.patch("/by-name/{name}", response_model=Notebook)
async def update_notebook_by_name(
    name: str,
    notebook_update: NotebookUpdate,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Updates a notebook by its name."""
    try:
        # First, get the notebook by name
        query = f"SELECT * FROM {NOTEBOOK_TABLE} WHERE name = $name"
        bindings = {"name": name}
        result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail=f"Notebook with name '{name}' not found")
            
        notebook = dict(result[0])
        notebook_id = notebook['id']
        if hasattr(notebook_id, 'table_name') and hasattr(notebook_id, 'record_id'):
            notebook_id = f"{notebook_id.table_name}:{notebook_id.record_id}"
        else:
            notebook_id = str(notebook_id)

        # Prepare update data
        update_data = notebook_update.model_dump(exclude_unset=True)
        update_data["updated"] = datetime.utcnow()

        # Update the notebook
        updated_notebook = await db.merge(notebook_id, update_data)
        
        print(f"Updated notebook response: {updated_notebook}")
        print(f"Type of updated_notebook: {type(updated_notebook)}")
        
        if updated_notebook:
            # Ensure we're working with a dict
            if not isinstance(updated_notebook, dict):
                updated_notebook = dict(updated_notebook)
            
            # Convert RecordID to string
            if hasattr(updated_notebook.get('id'), 'table_name') and hasattr(updated_notebook.get('id'), 'record_id'):
                updated_notebook['id'] = f"{updated_notebook['id'].table_name}:{updated_notebook['id'].record_id}"
            
            # Manually construct the Notebook response
            return Notebook(
                id=str(updated_notebook.get('id', '')),
                name=updated_notebook.get('name', ''),
                description=updated_notebook.get('description'),
                created=updated_notebook.get('created'),
                updated=updated_notebook.get('updated'),
                archived=updated_notebook.get('archived', False),
                metadata=updated_notebook.get('metadata', {}),
                sources=[],
                notes=[],
                chat_sessions=[]
            )
        else:
            raise HTTPException(status_code=404, detail="Notebook not found or update failed")
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        print(f"Error updating notebook by name: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error updating notebook: {e}")

@router.patch("/{notebook_id}", response_model=Notebook)
async def update_notebook(
    notebook_id: str,
    notebook_update: NotebookUpdate,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Updates a notebook by its ID."""
    if ":" not in notebook_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notebook ID format.")
    
    try:
        # Prepare update data
        update_data = notebook_update.model_dump(exclude_unset=True)
        update_data["updated"] = datetime.utcnow()

        # Update the notebook
        updated_notebook = await db.merge(notebook_id, update_data)
        
        if updated_notebook:
            # Ensure we're working with a dict
            if not isinstance(updated_notebook, dict):
                updated_notebook = dict(updated_notebook)
            
            # Convert RecordID to string
            if hasattr(updated_notebook.get('id'), 'table_name') and hasattr(updated_notebook.get('id'), 'record_id'):
                updated_notebook['id'] = f"{updated_notebook['id'].table_name}:{updated_notebook['id'].record_id}"
            
            # Manually construct the Notebook response
            return Notebook(
                id=str(updated_notebook.get('id', '')),
                name=updated_notebook.get('name', ''),
                description=updated_notebook.get('description'),
                created=updated_notebook.get('created'),
                updated=updated_notebook.get('updated'),
                archived=updated_notebook.get('archived', False),
                metadata=updated_notebook.get('metadata', {}),
                sources=[],
                notes=[],
                chat_sessions=[]
            )
        else:
            raise HTTPException(status_code=404, detail="Notebook not found or update failed")
            
    except Exception as e:
        print(f"Error updating notebook: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error updating notebook: {e}")

@router.post("/by-name/{name}/archive", response_model=Notebook)
async def archive_notebook_by_name(
    name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Archives a notebook by its name."""
    try:
        # First, get the notebook by name
        query = f"SELECT * FROM {NOTEBOOK_TABLE} WHERE name = $name"
        bindings = {"name": name}
        result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail=f"Notebook with name '{name}' not found")
            
        notebook = dict(result[0])
        notebook_id = notebook['id']
        if hasattr(notebook_id, 'table_name') and hasattr(notebook_id, 'record_id'):
            notebook_id = f"{notebook_id.table_name}:{notebook_id.record_id}"
        else:
            notebook_id = str(notebook_id)

        # Archive the notebook
        update_data = {"archived": True, "updated": datetime.utcnow()}
        updated_notebook = await db.merge(notebook_id, update_data)
        
        if updated_notebook:
            return convert_record_id_to_string(updated_notebook)
        else:
            raise HTTPException(status_code=404, detail="Notebook not found or archive failed")
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        print(f"Error archiving notebook by name: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error archiving notebook: {e}")

@router.post("/{notebook_id}/archive", response_model=Notebook)
async def archive_notebook(
    notebook_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Archives a notebook by its ID."""
    if ":" not in notebook_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notebook ID format.")
    
    try:
        # Archive the notebook
        update_data = {"archived": True, "updated": datetime.utcnow()}
        updated_notebook = await db.merge(notebook_id, update_data)
        
        if updated_notebook:
            return convert_record_id_to_string(updated_notebook)
        else:
            raise HTTPException(status_code=404, detail="Notebook not found or archive failed")
            
    except Exception as e:
        print(f"Error archiving notebook: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error archiving notebook: {e}")

@router.delete("/by-name/{name}/archive", response_model=Notebook)
async def unarchive_notebook_by_name(
    name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Unarchives a notebook by its name."""
    try:
        # First, get the notebook by name
        query = f"SELECT * FROM {NOTEBOOK_TABLE} WHERE name = $name"
        bindings = {"name": name}
        result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail=f"Notebook with name '{name}' not found")
            
        notebook = dict(result[0])
        notebook_id = notebook['id']
        if hasattr(notebook_id, 'table_name') and hasattr(notebook_id, 'record_id'):
            notebook_id = f"{notebook_id.table_name}:{notebook_id.record_id}"
        else:
            notebook_id = str(notebook_id)

        # Unarchive the notebook
        update_data = {"archived": False, "updated": datetime.utcnow()}
        updated_notebook = await db.merge(notebook_id, update_data)
        
        if updated_notebook:
            return convert_record_id_to_string(updated_notebook)
        else:
            raise HTTPException(status_code=404, detail="Notebook not found or unarchive failed")
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        print(f"Error unarchiving notebook by name: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error unarchiving notebook: {e}")

@router.delete("/{notebook_id}/archive", response_model=Notebook)
async def unarchive_notebook(
    notebook_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Unarchives a notebook by its ID."""
    if ":" not in notebook_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notebook ID format.")
    
    try:
        # Unarchive the notebook
        update_data = {"archived": False, "updated": datetime.utcnow()}
        updated_notebook = await db.merge(notebook_id, update_data)
        
        if updated_notebook:
            return convert_record_id_to_string(updated_notebook)
        else:
            raise HTTPException(status_code=404, detail="Notebook not found or unarchive failed")
            
    except Exception as e:
        print(f"Error unarchiving notebook: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error unarchiving notebook: {e}")

@router.delete("/by-name/{name}", response_model=StatusResponse)
async def delete_notebook_by_name(
    name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Deletes a notebook by its name."""
    try:
        # First, get the notebook by name
        query = f"SELECT * FROM {NOTEBOOK_TABLE} WHERE name = $name"
        bindings = {"name": name}
        result = await db.query(query, bindings)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail=f"Notebook with name '{name}' not found")
            
        notebook = dict(result[0])
        notebook_id = notebook['id']
        if hasattr(notebook_id, 'table_name') and hasattr(notebook_id, 'record_id'):
            notebook_id = f"{notebook_id.table_name}:{notebook_id.record_id}"
        else:
            notebook_id = str(notebook_id)

        # Delete the notebook
        deleted_notebook = await db.delete(notebook_id)
        
        if deleted_notebook:
            return StatusResponse(status="success", message=f"Notebook '{name}' deleted successfully")
        else:
            raise HTTPException(status_code=404, detail="Notebook not found or delete failed")
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        print(f"Error deleting notebook by name: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error deleting notebook: {e}")

@router.delete("/{notebook_id}", response_model=StatusResponse)
async def delete_notebook(
    notebook_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Deletes a notebook by its ID."""
    if ":" not in notebook_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notebook ID format.")
    
    try:
        # Delete the notebook
        deleted_notebook = await db.delete(notebook_id)
        
        if deleted_notebook:
            return StatusResponse(status="success", message=f"Notebook {notebook_id} deleted successfully")
        else:
            raise HTTPException(status_code=404, detail="Notebook not found or delete failed")
            
    except Exception as e:
        print(f"Error deleting notebook: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error deleting notebook: {e}")

# Placeholder for Note endpoints (will be in a separate router or added here)
# POST /notebooks/{notebook_id}/notes
# GET /notebooks/{notebook_id}/notes
# GET /notes/{note_id}
# PATCH /notes/{note_id}
# DELETE /notes/{note_id}
