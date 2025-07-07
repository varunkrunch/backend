from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from surrealdb import AsyncSurreal
from loguru import logger

from ..database import get_db_connection
from ..models import (
    Note, NoteCreate, NoteUpdate, NoteSummary, StatusResponse
)
from open_notebook.domain.models import model_manager

# Create a router for note-related endpoints
# Notes are often accessed in the context of a notebook, but can also be managed directly by ID
router = APIRouter(
    tags=["Notes"],
)

# Define the table name for notes in SurrealDB
NOTE_TABLE = "note"
NOTEBOOK_TABLE = "notebook" # Needed for context checks
ARTIFACT_TABLE = "artifact"  # Relation table between notes and notebooks

def convert_record_id_to_string(data):
    """Convert SurrealDB RecordID objects to strings in the response data."""
    if isinstance(data, dict):
        return {k: convert_record_id_to_string(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_record_id_to_string(item) for item in data]
    elif hasattr(data, 'table_name') and hasattr(data, 'record_id'):
        return f"{data.table_name}:{data.record_id}"
    return data

async def create_note_embedding(db: AsyncSurreal, note_id: str, content: str):
    """Creates embedding vector for note content if embedding model is available."""
    try:
        if not model_manager.embedding_model:
            logger.warning("No embedding model found. Note will not be searchable.")
            return None
        
        embedding = model_manager.embedding_model.embed([content])[0]
        await db.merge(note_id, {"embedding": embedding})
        return embedding
    except Exception as e:
        logger.error(f"Error creating embedding for note {note_id}: {str(e)}")
        return None

async def link_note_to_notebook(db: AsyncSurreal, note_id: str, notebook_id: str):
    """Creates artifact relation between note and notebook."""
    try:
        # Create the relationship using proper SurrealDB syntax matching Streamlit's expectations
        query = f"""
        LET $note = {note_id};
        LET $notebook = {notebook_id};
        
        CREATE artifact CONTENT {{
            out: $notebook,
            in: $note,
            created: time::now(),
            updated: time::now()
        }};
        """
        logger.debug(f"Executing link query: {query}")
        await db.query(query)
    except Exception as e:
        logger.error(f"Error linking note {note_id} to notebook {notebook_id}: {str(e)}")
        raise

@router.post("/notes", response_model=Note, status_code=status.HTTP_201_CREATED)
async def create_note(
    note_data: NoteCreate,
    notebook_name: Optional[str] = None,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Creates a new note, optionally associating it with a notebook by name."""
    try:
        # Prepare note data
        data_to_create = note_data.model_dump()
        data_to_create["created"] = datetime.utcnow()
        data_to_create["updated"] = datetime.utcnow()
        data_to_create["embedding"] = []  # Initialize embedding as empty array
        
        # Set note type if not provided
        if "note_type" not in data_to_create or not data_to_create["note_type"]:
            data_to_create["note_type"] = "human"

        # Create the note first without embedding
        created_notes = await db.create(NOTE_TABLE, data_to_create)
        if not created_notes:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create note")
        
        created_note = created_notes[0] if isinstance(created_notes, list) else created_notes
        note_id = convert_record_id_to_string(created_note["id"])

        # Create and update embedding if content is provided
        embedding = None
        if data_to_create.get("content"):
            try:
                embedding = await create_note_embedding(db, note_id, data_to_create["content"])
                if embedding:
                    # Update the note with the embedding
                    await db.merge(note_id, {"embedding": embedding})
                    created_note["embedding"] = embedding
            except Exception as e:
                logger.warning(f"Failed to create embedding for note {note_id}: {str(e)}")
                # Continue even if embedding creation fails

        # Link note to notebook if notebook name is provided
        if notebook_name:
            # Find notebook by name
            notebook_query = """
            SELECT * FROM notebook 
            WHERE string::lowercase(name) = string::lowercase($name)
            LIMIT 1;
            """
            notebook_res = await db.query(notebook_query, {"name": notebook_name})
            
            if not notebook_res or not notebook_res[0]:
                raise HTTPException(status_code=404, detail=f"Notebook with name '{notebook_name}' not found")
            
            notebook = notebook_res[0]
            notebook_id = notebook['id']
            if hasattr(notebook_id, 'table_name') and hasattr(notebook_id, 'record_id'):
                notebook_id = f"{notebook_id.table_name}:{notebook_id.record_id}"
            else:
                notebook_id = str(notebook_id)
            
            # Create the relationship
            await link_note_to_notebook(db, note_id, notebook_id)

            # Verify the relationship was created
            verify_query = """
            SELECT * FROM artifact 
            WHERE out = $notebook_id 
            AND in = $note_id;
            """
            verify_result = await db.query(verify_query, {
                "notebook_id": notebook_id,
                "note_id": note_id
            })
            logger.info(f"Verification of relationship: {verify_result}")

        # Convert and return the created note
        converted_note = convert_record_id_to_string(created_note)
        response_data = {
            "id": str(converted_note.get("id")),
            "title": converted_note.get("title"),
            "content": converted_note.get("content"),
            "note_type": converted_note.get("note_type", "human"),
            "created": converted_note.get("created"),
            "updated": converted_note.get("updated"),
            "embedding": converted_note.get("embedding", [])  # Ensure embedding is always an array
        }
        
        return Note(**response_data)

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error creating note: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error during note creation: {e}")

@router.get("/notebooks/by-name/{notebook_name}/notes", response_model=None)  # Removing response model temporarily for debugging
async def list_notes_by_notebook_name(
    notebook_name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Lists all notes in a notebook specified by name using a direct graph traversal."""
    try:
        # First fetch notebook id by name
        notebook_query = """
        SELECT * FROM notebook 
        WHERE name = $name 
        LIMIT 1;
        """
        logger.info(f"🔍 Looking for notebook with name: {notebook_name}")
        notebook_res = await db.query(notebook_query, {"name": notebook_name})
        
        if not notebook_res or not notebook_res[0]:
            raise HTTPException(status_code=404, detail=f"Notebook '{notebook_name}' not found")
        
        notebook = notebook_res[0]
        notebook_id = notebook['id']
        if hasattr(notebook_id, 'table_name') and hasattr(notebook_id, 'record_id'):
            notebook_id = f"{notebook_id.table_name}:{notebook_id.record_id}"
        else:
            notebook_id = str(notebook_id)

        # Let's return all debug information
        debug_info = {
            "notebook_info": {
                "name": notebook_name,
                "id": notebook_id,
                "full_notebook_data": notebook
            }
        }

        # Check all notes
        all_notes_query = "SELECT * FROM note;"
        all_notes = await db.query(all_notes_query)
        debug_info["all_notes_in_db"] = all_notes

        # Check artifacts
        artifacts_query = "SELECT * FROM artifact WHERE in = $id;"
        artifacts = await db.query(artifacts_query, {"id": notebook_id})
        debug_info["artifacts"] = artifacts

        # Try graph traversal query
        notes_query = """
        SELECT 
            ->artifact->note.* as note
        FROM notebook 
        WHERE id = $id;
        """
        notes_res = await db.query(notes_query, {"id": notebook_id})
        debug_info["graph_traversal_query_result"] = notes_res
        
        # Try alternative query
        alt_query = """
        SELECT note.* as note
        FROM artifact, note
        WHERE artifact.in = $id
        AND artifact.out = note.id;
        """
        alt_res = await db.query(alt_query, {"id": notebook_id})
        debug_info["alternative_query_result"] = alt_res
        
        notes_raw_list = notes_res if notes_res else []
        notes_converted = [convert_record_id_to_string(note["note"]) for note in notes_raw_list if note.get("note")]
        notes_sorted = sorted(notes_converted, key=lambda x: x.get("updated", ""), reverse=True)
        
        debug_info["final_processing"] = {
            "raw_list": notes_raw_list,
            "converted": notes_converted,
            "sorted": notes_sorted
        }

        # Return all debug information instead of just the final notes
        return debug_info

    except Exception as e:
        logger.error(f"❌ Error listing notes for notebook {notebook_name}: {str(e)}")
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "status": "error"
        }

@router.get("/notes/search", response_model=List[NoteSummary])
async def search_notes(
    query: str,
    limit: int = 10,
    minimum_score: float = 0.2,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Search notes using vector similarity if embedding model is available, otherwise use text search."""
    try:
        if model_manager.embedding_model:
            # Vector search using embeddings
            query_embedding = model_manager.embedding_model.embed([query])[0]
            search_query = f"""
            SELECT *, 
                vector::similarity(embedding, $embedding) as score 
            FROM {NOTE_TABLE}
            WHERE vector::similarity(embedding, $embedding) > $min_score
            ORDER BY score DESC
            LIMIT $limit;
            """
            results = await db.query(
                search_query, 
                {
                    "embedding": query_embedding,
                    "min_score": minimum_score,
                    "limit": limit
                }
            )
        else:
            # Fallback to text search
            search_query = f"""
            SELECT *,
                search::score(content) as score
            FROM {NOTE_TABLE}
            WHERE search::contains(content, $query)
            ORDER BY score DESC
            LIMIT $limit;
            """
            results = await db.query(search_query, {"query": query, "limit": limit})

        if not results:
            return []

        notes_converted = [convert_record_id_to_string(note) for note in results]
        return [NoteSummary(**note) for note in notes_converted]
    except Exception as e:
        logger.error(f"Error searching notes: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error searching notes: {e}")

@router.get("/notes/{note_id}", response_model=Note)
async def get_note(
    note_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Gets details of a specific note by its ID."""
    if ":" not in note_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid note ID format. Expected table:id, got {note_id}")
    try:
        result = await db.select(note_id)
        # SurrealDB.select can return a list – grab the first item if so
        if isinstance(result, list):
            result = result[0] if result else None
        if result:
            return Note(**convert_record_id_to_string(result))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Note with id {note_id} not found")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error getting note {note_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting note: {e}")

@router.get("/notes/by-title/{note_title}", response_model=None)  # Temporarily remove response model for debugging
async def get_note_by_title(
    note_title: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Gets details of a specific note by its title."""
    try:
        # First try to get all notes and log them
        all_notes_query = "SELECT * FROM note;"
        all_notes = await db.query(all_notes_query)
        logger.info(f"All notes in database: {all_notes}")

        # Try a simpler query first
        find_query = """
        SELECT 
            ->artifact->notebook.name as notebook_name,
            id,
            title,
            content,
            note_type,
            created,
            updated,
            embedding
        FROM note 
        WHERE title = type::string($title);
        """
        logger.info(f"Searching for note with title: {note_title}")
        note_res = await db.query(find_query, {"title": note_title})
        logger.info(f"Query result: {note_res}")
        
        if not note_res or not note_res[0]:
            # Try an alternative query with CONTAINS
            alt_query = """
            SELECT 
                ->artifact->notebook.name as notebook_name,
                id,
                title,
                content,
                note_type,
                created,
                updated,
                embedding
            FROM note 
            WHERE string::lowercase(title) = string::lowercase($title);
            """
            note_res = await db.query(alt_query, {"title": note_title})
            logger.info(f"Alternative query result: {note_res}")
            
            if not note_res or not note_res[0]:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Note with title '{note_title}' not found")
        
        # Get the first matching note
        note_data = note_res[0]
        logger.info(f"Raw note data: {note_data}")
        
        # Convert the note data, ensuring proper ID conversion
        converted_note = convert_record_id_to_string(note_data)
        logger.info(f"Converted note data: {converted_note}")
        
        # Create a clean response object
        response = {
            "id": converted_note.get("id"),
            "title": converted_note.get("title"),
            "content": converted_note.get("content"),
            "note_type": converted_note.get("note_type", "human"),
            "created": converted_note.get("created"),
            "updated": converted_note.get("updated"),
            "embedding": converted_note.get("embedding"),
            "notebook_name": converted_note.get("notebook_name")
        }
        
        logger.info(f"Final response object: {response}")
        return response

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error getting note with title {note_title}: {str(e)}")
        error_response = {
            "error": str(e),
            "error_type": type(e).__name__,
            "note_title_searched": note_title,
            "status": "error"
        }
        return error_response

@router.patch("/notes/{note_id}", response_model=Note)
async def update_note(
    note_id: str,
    note_update: NoteUpdate,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Updates a note's title or content."""
    if ":" not in note_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid note ID format. Expected table:id, got {note_id}")

    update_data = note_update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update.")

    try:
        # Update timestamp
        update_data["updated"] = datetime.utcnow()

        # If content is being updated, update embedding
        if "content" in update_data:
            await create_note_embedding(db, note_id, update_data["content"])

        # Update the note
        updated_notes = await db.merge(note_id, update_data)
        if updated_notes:
            return convert_record_id_to_string(updated_notes)
        else:
            existing = await db.select(note_id)
            if not existing:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Note with id {note_id} not found for update")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update note or empty response")

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error updating note {note_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error updating note: {e}")

@router.delete("/notes/{note_id}", response_model=StatusResponse)
async def delete_note(
    note_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Deletes a note."""
    if ":" not in note_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid note ID format. Expected table:id, got {note_id}")
    try:
        # Check if note exists
        existing = await db.select(note_id)
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Note with id {note_id} not found for deletion")

        # Delete the note
        await db.delete(note_id)
        return StatusResponse(status="success", message=f"Note {note_id} deleted successfully.")

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error deleting note {note_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error deleting note: {e}")

@router.delete("/notes/by-title/{note_title}", response_model=StatusResponse)
async def delete_note_by_title(
    note_title: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Deletes a note by its title."""
    try:
        # First find the note with the given title
        find_query = """
        SELECT * FROM note 
        WHERE title = $title 
        LIMIT 1;
        """
        note_res = await db.query(find_query, {"title": note_title})
        
        if not note_res or not note_res[0]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Note with title '{note_title}' not found")
        
        note = note_res[0]
        note_id = convert_record_id_to_string(note['id'])
        
        # Delete the note using the existing functionality
        await db.delete(note_id)
        return StatusResponse(status="success", message=f"Note with title '{note_title}' deleted successfully.")

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error deleting note with title {note_title}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error deleting note: {e}")

@router.patch("/notes/by-title/{note_title}", response_model=Note)
async def update_note_by_title(
    note_title: str,
    note_update: NoteUpdate,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Updates a note's content by its title."""
    try:
        # First find the note with the given title
        find_query = """
        SELECT * FROM note 
        WHERE title = $title 
        LIMIT 1;
        """
        note_res = await db.query(find_query, {"title": note_title})
        
        if not note_res or not note_res[0]:
            # Try case-insensitive search
            alt_query = """
            SELECT * FROM note 
            WHERE string::lowercase(title) = string::lowercase($title)
            LIMIT 1;
            """
            note_res = await db.query(alt_query, {"title": note_title})
            if not note_res or not note_res[0]:
                raise HTTPException(status_code=404, detail=f"Note with title '{note_title}' not found")

        # Get the note ID and convert it to string format
        note = note_res[0]
        note_id = note['id']
        if hasattr(note_id, 'table_name') and hasattr(note_id, 'record_id'):
            note_id = f"{note_id.table_name}:{note_id.record_id}"
        else:
            note_id = str(note_id)

        # Prepare update data
        update_data = note_update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update.")

        # Update timestamp
        update_data["updated"] = datetime.utcnow()

        # If content is being updated, update embedding
        if "content" in update_data:
            await create_note_embedding(db, note_id, update_data["content"])

        # Update the note
        updated_note = await db.merge(note_id, update_data)
        if not updated_note:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update note")

        # Convert the updated note to proper format
        converted_note = convert_record_id_to_string(updated_note)
        
        # Create a properly formatted response
        response_data = {
            "id": str(converted_note.get("id")),  # Ensure ID is string
            "title": converted_note.get("title", note_title),  # Use original title if not updated
            "content": converted_note.get("content"),
            "note_type": converted_note.get("note_type", "human"),
            "created": converted_note.get("created"),
            "updated": converted_note.get("updated"),
            "embedding": converted_note.get("embedding")
        }
        
        return Note(**response_data)

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error updating note with title {note_title}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error updating note: {e}")