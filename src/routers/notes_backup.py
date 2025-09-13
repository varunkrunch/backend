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
    prefix="/api/v1",
    tags=["Notes"],
)

# Define the table name for notes in SurrealDB
NOTE_TABLE = "note"
NOTEBOOK_TABLE = "notebook" # Needed for context checks
ARTIFACT_TABLE = "artifact"  # Relation table between notes and notebooks

def convert_record_id_to_string(data):
    """Convert SurrealDB RecordID objects to strings in the response data."""
    try:
        if data is None:
            return None
        elif isinstance(data, dict):
            return {k: convert_record_id_to_string(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [convert_record_id_to_string(item) for item in data]
        elif hasattr(data, 'table_name') and hasattr(data, 'record_id'):
            return f"{data.table_name}:{data.record_id}"
        elif hasattr(data, '__dict__'):
            # Handle objects that might have RecordID attributes
            return {k: convert_record_id_to_string(v) for k, v in data.__dict__.items()}
        elif isinstance(data, str) and data.startswith("{'table_name':"):
            # Handle string representation of RecordID dict
            import ast
            try:
                id_dict = ast.literal_eval(data)
                return f"{id_dict['table_name']}:{id_dict['id']}"
            except:
                return data
        else:
            return data
    except Exception as e:
        logger.error(f"Error converting RecordID: {e}, data type: {type(data)}")
        # Return a safe fallback
        if hasattr(data, 'table_name') and hasattr(data, 'record_id'):
            return f"{data.table_name}:{data.record_id}"
        return str(data) if data is not None else None

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
        # Create the relationship using proper SurrealDB relation syntax
        query = f"""
        RELATE {note_id}->artifact->{notebook_id} SET 
            created = time::now(),
            updated = time::now();
        """
        logger.debug(f"Executing relation query: {query}")
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

        # Note: notebook_id is now included in the initial creation data above

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

@router.post("/notebooks/by-name/{notebook_name}/notes", response_model=Note, status_code=status.HTTP_201_CREATED)
async def create_note_in_notebook(
    notebook_name: str,
    note_data: NoteCreate,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Creates a new note in a specific notebook by name."""
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

        # Find notebook by name and link the note
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
        
        # Verify the note was actually created by trying to retrieve it
        try:
            verify_note = await db.select(str(converted_note.get("id")))
            logger.info(f"Note verification result: {verify_note}")
        except Exception as e:
            logger.error(f"Note verification failed: {e}")
        
        return Note(**response_data)

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error creating note in notebook {notebook_name}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error during note creation: {e}")

@router.get("/notebooks/by-name/{notebook_name}/notes", response_model=List[NoteSummary])
async def list_notes_by_notebook_name(
    notebook_name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Lists all notes in a notebook specified by name. Uses the same logic as Streamlit."""
    try:
        logger.info(f"🔍 === STARTING NOTEBOOK NOTES QUERY ===")
        logger.info(f"🔍 Notebook name: '{notebook_name}'")
        
        # First fetch notebook id by name
        notebook_query = """
        SELECT * FROM notebook 
        WHERE string::lowercase(name) = string::lowercase($name)
        LIMIT 1;
        """
        logger.info(f"🔍 Looking for notebook with name: '{notebook_name}'")
        notebook_res = await db.query(notebook_query, {"name": notebook_name})
        logger.info(f"🔍 Notebook query result: {notebook_res}")
        
        if not notebook_res or not notebook_res[0]:
            logger.error(f"❌ Notebook '{notebook_name}' not found")
            raise HTTPException(status_code=404, detail=f"Notebook '{notebook_name}' not found")
        
        notebook = notebook_res[0]
        raw_notebook_id = notebook['id']  # Keep the raw SurrealDB ID object
        
        # Also create string version for logging
        if hasattr(raw_notebook_id, 'table_name') and hasattr(raw_notebook_id, 'record_id'):
            notebook_id_str = f"{raw_notebook_id.table_name}:{raw_notebook_id.record_id}"
        else:
            notebook_id_str = str(raw_notebook_id)

        logger.info(f"📓 Found notebook raw ID: {raw_notebook_id} (string: {notebook_id_str})")

        # Query notes directly using notebook_id field
        notes_query = f"""
        SELECT id, title, content, created, updated, note_type, metadata, embedding
        FROM note
        WHERE notebook_id = $notebook_id
        ORDER BY updated DESC;
        """
        
        logger.info(f"🔗 Querying notes for notebook using direct notebook_id: {notes_query}")
        notes_res = await db.query(notes_query, {"notebook_id": notebook_id_str})
        logger.info(f"📝 Query result: {notes_res}")
        
        notes_converted = []
        
        if notes_res:
            logger.info(f"📝 Processing {len(notes_res)} notes from direct query")
            for note_data in notes_res:
                try:
                    logger.debug(f"Processing note_data: {note_data}")
                    note = convert_record_id_to_string(note_data)
                    logger.debug(f"Converted note: {note}")
                    
                    # Ensure all fields are properly converted
                    note_id = str(note.get("id", "")) if note.get("id") else ""
                    note_title = note.get("title", "") if note.get("title") else ""
                    note_type = note.get("note_type", "human") if note.get("note_type") else "human"
                    note_created = note.get("created")
                    note_updated = note.get("updated")
                    
                    notes_converted.append(NoteSummary(
                        id=note_id,
                        title=note_title,
                        note_type=note_type,
                        created=note_created,
                        updated=note_updated
                    ))
                    logger.debug(f"Added note to list: {note_title}")
                except Exception as e:
                    logger.error(f"Error processing note_data: {e}")
                    logger.error(f"note_data: {note_data}")
                    continue
        else:
            logger.info("📝 No notes found for this notebook")
        
        logger.info(f"✅ Returning {len(notes_converted)} notes for notebook '{notebook_name}'")
        logger.info(f"📝 Notes: {[note.title for note in notes_converted]}")
        return notes_converted

    except HTTPException as http_exc:
        logger.error(f"❌ HTTP Exception: {http_exc}")
        raise http_exc
    except Exception as e:
        logger.error(f"❌ Error listing notes for notebook {notebook_name}: {str(e)}")
        logger.error(f"❌ Exception type: {type(e)}")
        logger.error(f"❌ Exception details: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error listing notes: {e}")

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

# Add a simple endpoint to list all notes (for verification)
@router.get("/notes/all", response_model=List[NoteSummary])
async def list_all_notes(
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    List all notes in the database.
    Useful for verifying note creation and debugging.
    """
    try:
        # Get all notes
        all_notes_query = "SELECT * FROM note ORDER BY updated DESC;"
        all_notes = await db.query(all_notes_query)
        
        if not all_notes:
            return []
        
        notes_converted = []
        for note in all_notes:
            note_dict = convert_record_id_to_string(note)
            # Properly convert the ID to table:id format
            note_id = convert_record_id_to_string(note_dict.get("id", ""))
            
            notes_converted.append(NoteSummary(
                id=str(note_id),
                title=note_dict.get("title", ""),
                note_type=note_dict.get("note_type", "human"),
                created=note_dict.get("created"),
                updated=note_dict.get("updated")
            ))
        
        logger.info(f"Found {len(notes_converted)} notes in database")
        return notes_converted
        
    except Exception as e:
        logger.error(f"Error listing all notes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Internal server error: {str(e)}"
        )

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

@router.get("/notes/by-title/{note_title}", response_model=Note)
async def get_note_by_title(
    note_title: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Gets details of a specific note by its title. Uses improved matching to handle whitespace issues."""
    try:
        logger.info(f"🔍 Searching for note with title: '{note_title}'")
        
        # First try exact match (case-insensitive)
        find_query = """
        SELECT * FROM note 
        WHERE string::lowercase(title) = string::lowercase($title)
        LIMIT 1;
        """
        
        note_res = await db.query(find_query, {"title": note_title})
        logger.info(f"📝 Exact match result: {note_res}")
        
        # If not found, try trimmed match (handle whitespace issues)
        if not note_res or not note_res[0]:
            logger.info(f"🔄 Exact match failed, trying trimmed match...")
            trimmed_query = """
            SELECT * FROM note 
            WHERE string::lowercase(string::trim(title)) = string::lowercase(string::trim($title))
            LIMIT 1;
            """
            
            note_res = await db.query(trimmed_query, {"title": note_title})
            logger.info(f"📝 Trimmed match result: {note_res}")
        
        # If still not found, try contains match (more flexible)
        if not note_res or not note_res[0]:
            logger.info(f"🔄 Trimmed match failed, trying contains match...")
            contains_query = """
            SELECT * FROM note 
            WHERE string::lowercase(title) CONTAINS string::lowercase($title)
            OR string::lowercase(string::trim(title)) CONTAINS string::lowercase(string::trim($title))
            LIMIT 1;
            """
            
            note_res = await db.query(contains_query, {"title": note_title})
            logger.info(f"📝 Contains match result: {note_res}")
        
        if not note_res or not note_res[0]:
            # Let's check what notes exist in the database
            all_notes_query = "SELECT title FROM note;"
            all_notes = await db.query(all_notes_query)
            available_titles = [note.get('title', 'Unknown') for note in (all_notes or [])]
            
            logger.warning(f"❌ Note with title '{note_title}' not found")
            logger.info(f"📋 Available note titles: {available_titles}")
            
            # Try to find similar titles
            similar_titles = []
            search_term = note_title.lower().strip()
            for title in available_titles:
                if title and search_term in title.lower().strip():
                    similar_titles.append(title)
            
            error_detail = f"Note with title '{note_title}' not found."
            if similar_titles:
                error_detail += f" Similar titles found: {similar_titles}"
            else:
                error_detail += f" Available titles: {available_titles}"
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=error_detail
            )
        
        # Get the first matching note
        note_data = note_res[0]
        logger.info(f"✅ Found note: {note_data}")
        
        # Convert the note data
        converted_note = convert_record_id_to_string(note_data)
        
        # Create response object
        response_data = {
            "id": str(converted_note.get("id", "")),
            "title": converted_note.get("title", ""),
            "content": converted_note.get("content", ""),
            "note_type": converted_note.get("note_type", "human"),
            "created": converted_note.get("created"),
            "updated": converted_note.get("updated"),
            "embedding": converted_note.get("embedding", [])
        }
        
        logger.info(f"✅ Returning note: {response_data}")
        return Note(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting note with title '{note_title}': {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Internal server error: {str(e)}"
        )

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
        logger.info(f"🗑️ Attempting to delete note with title: '{note_title}'")
        
        # First try exact match
        find_query = """
        SELECT * FROM note 
        WHERE title = $title 
        LIMIT 1;
        """
        note_res = await db.query(find_query, {"title": note_title})
        
        # If not found, try case-insensitive search
        if not note_res or not note_res[0]:
            logger.info(f"🔄 Exact match failed, trying case-insensitive search...")
            alt_query = """
            SELECT * FROM note 
            WHERE string::lowercase(title) = string::lowercase($title)
            LIMIT 1;
            """
            note_res = await db.query(alt_query, {"title": note_title})
            
            # If still not found, try trimmed search
            if not note_res or not note_res[0]:
                logger.info(f"🔄 Case-insensitive search failed, trying trimmed search...")
                trimmed_query = """
                SELECT * FROM note 
                WHERE string::lowercase(string::trim(title)) = string::lowercase(string::trim($title))
                LIMIT 1;
                """
                note_res = await db.query(trimmed_query, {"title": note_title})
        
        if not note_res or not note_res[0]:
            # Let's check what notes exist
            all_notes_query = "SELECT title FROM note;"
            all_notes = await db.query(all_notes_query)
            available_titles = [note.get('title', 'Unknown') for note in (all_notes or [])]
            
            logger.error(f"❌ Note with title '{note_title}' not found")
            logger.info(f"📋 Available note titles: {available_titles}")
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Note with title '{note_title}' not found. Available titles: {available_titles}"
            )
        
        note = note_res[0]
        raw_note_id = note['id']
        
        # Convert to proper format for deletion (same as regular delete endpoint)
        if hasattr(raw_note_id, 'table_name') and hasattr(raw_note_id, 'record_id'):
            note_id = f"{raw_note_id.table_name}:{raw_note_id.record_id}"
        else:
            note_id = str(raw_note_id)
            
        logger.info(f"✅ Found note with ID: {note_id}")
        
        # First, delete any artifact relationships for this note
        try:
            # Find and delete artifacts that reference this note
            artifacts_query = "SELECT * FROM artifact WHERE in = $note_id;"
            artifacts = await db.query(artifacts_query, {"note_id": raw_note_id})
            
            if artifacts:
                logger.info(f"🗑️ Found {len(artifacts)} artifacts to delete for note {note_id}")
                for artifact in artifacts:
                    artifact_id = artifact.get('id')
                    if hasattr(artifact_id, 'table_name') and hasattr(artifact_id, 'record_id'):
                        artifact_id_str = f"{artifact_id.table_name}:{artifact_id.record_id}"
                    else:
                        artifact_id_str = str(artifact_id)
                    
                    logger.info(f"🗑️ Deleting artifact: {artifact_id_str}")
                    await db.delete(artifact_id_str)
            else:
                logger.info(f"ℹ️ No artifacts found for note {note_id}")
        except Exception as e:
            logger.warning(f"⚠️ Error deleting artifacts for note {note_id}: {e}")
        
        # Delete the note using the existing functionality
        await db.delete(note_id)
        logger.info(f"✅ Successfully deleted note: {note_id}")
        
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



# Add a guaranteed note creation endpoint that ensures proper linking and retrieval
@router.post("/notes/guaranteed", response_model=Note, status_code=status.HTTP_201_CREATED)
async def create_note_guaranteed(
    note_data: NoteCreate,
    notebook_name: Optional[str] = None,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Guaranteed note creation with proper notebook linking.
    Uses the same logic as Streamlit's note creation.
    """
    logger.info(f"Creating guaranteed note: {note_data.model_dump()}")
    
    try:
        # Validate input
        if not note_data.content or not note_data.content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Note content is required"
            )
        
        # Prepare note data
        data_to_create = note_data.model_dump()
        data_to_create["created"] = datetime.utcnow()
        data_to_create["updated"] = datetime.utcnow()
        data_to_create["embedding"] = []
        
        if not data_to_create.get("note_type"):
            data_to_create["note_type"] = "human"
        
        # Clean up title to prevent whitespace issues
        if data_to_create.get("title"):
            data_to_create["title"] = data_to_create["title"].strip()
        
        if not data_to_create.get("title"):
            data_to_create["title"] = f"Note {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        
        logger.info(f"Creating note with data: {data_to_create}")
        
        # Create the note (same as Streamlit's note.save())
        created_notes = await db.create(NOTE_TABLE, data_to_create)
        if not created_notes:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Failed to create note"
            )
        
        created_note = created_notes[0] if isinstance(created_notes, list) else created_notes
        
        # Ensure note_id is properly converted to string
        raw_note_id = created_note["id"]
        logger.info(f"Raw note ID: {raw_note_id}, type: {type(raw_note_id)}")
        
        if hasattr(raw_note_id, 'table_name') and hasattr(raw_note_id, 'record_id'):
            note_id = f"{raw_note_id.table_name}:{raw_note_id.record_id}"
        else:
            note_id = str(raw_note_id)
        
        logger.info(f"Created note with ID: {note_id}")
        
        # Link to notebook if specified (same as Streamlit's note.add_to_notebook())
        if notebook_name:
            try:
                # Find notebook
                notebook_query = """
                SELECT * FROM notebook 
                WHERE string::lowercase(name) = string::lowercase($name)
                LIMIT 1;
                """
                notebook_res = await db.query(notebook_query, {"name": notebook_name})
                
                if not notebook_res or not notebook_res[0]:
                    logger.error(f"Notebook '{notebook_name}' not found")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Notebook '{notebook_name}' not found"
                    )
                
                notebook = notebook_res[0]
                raw_notebook_id = notebook['id']
                logger.info(f"Raw notebook ID: {raw_notebook_id}, type: {type(raw_notebook_id)}")
                
                if hasattr(raw_notebook_id, 'table_name') and hasattr(raw_notebook_id, 'record_id'):
                    notebook_id = f"{raw_notebook_id.table_name}:{raw_notebook_id.record_id}"
                else:
                    notebook_id = str(raw_notebook_id)
                
                logger.info(f"📓 Found notebook ID: {notebook_id}")
                logger.info(f"🔗 Linking note {note_id} to notebook {notebook_id}")
                
                # Create the relationship using the same logic as Streamlit's note.add_to_notebook()
                # This calls self.relate("artifact", notebook_id) which uses repo_relate
                relate_query = f"RELATE {note_id}->artifact->{notebook_id} SET created = time::now(), updated = time::now();"
                logger.info(f"Executing RELATE query: {relate_query}")
                await db.query(relate_query)
                
                logger.info(f"✅ Successfully linked note to notebook")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"❌ Error linking note to notebook: {e}")
                logger.error(f"Note ID: {note_id}, Notebook name: {notebook_name}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to link note to notebook: {str(e)}"
                )
        else:
            logger.warning("⚠️ No notebook specified - note will not be linked to any notebook")
        
        # Prepare response
        converted_note = convert_record_id_to_string(created_note)
        
        # Ensure ID is properly converted to string
        response_id = converted_note.get("id")
        if hasattr(response_id, 'table_name') and hasattr(response_id, 'record_id'):
            response_id = f"{response_id.table_name}:{response_id.record_id}"
        else:
            response_id = str(response_id) if response_id else ""
        
        response_data = {
            "id": response_id,
            "title": converted_note.get("title", ""),
            "content": converted_note.get("content", ""),
            "note_type": converted_note.get("note_type", "human"),
            "created": converted_note.get("created"),
            "updated": converted_note.get("updated"),
            "embedding": converted_note.get("embedding", [])
        }
        
        logger.info(f"Returning guaranteed note: {response_data}")
        return Note(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in create_note_guaranteed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Internal server error: {str(e)}"
        )

# Add a comprehensive debug endpoint to check database state
@router.get("/debug/notes", response_model=dict)
async def debug_notes(
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Debug endpoint to check the state of notes and artifacts in the database."""
    try:
        # Get all notes
        all_notes_query = "SELECT * FROM note;"
        all_notes = await db.query(all_notes_query)
        
        # Get all artifacts
        all_artifacts_query = "SELECT * FROM artifact;"
        all_artifacts = await db.query(all_artifacts_query)
        
        # Get all notebooks
        all_notebooks_query = "SELECT * FROM notebook;"
        all_notebooks = await db.query(all_notebooks_query)
        
        # Convert to readable format
        notes_converted = []
        if all_notes:
            for note in all_notes:
                note_dict = convert_record_id_to_string(note)
                notes_converted.append({
                    "id": str(note_dict.get("id", "")),
                    "title": note_dict.get("title", ""),
                    "content": note_dict.get("content", "")[:100] + "..." if note_dict.get("content") else "",
                    "note_type": note_dict.get("note_type", "human"),
                    "created": note_dict.get("created"),
                    "updated": note_dict.get("updated")
                })
        
        artifacts_converted = []
        if all_artifacts:
            for artifact in all_artifacts:
                artifact_dict = convert_record_id_to_string(artifact)
                artifacts_converted.append({
                    "id": str(artifact_dict.get("id", "")),
                    "out": str(artifact_dict.get("out", "")),  # notebook
                    "in": str(artifact_dict.get("in", "")),    # note
                    "created": artifact_dict.get("created"),
                    "updated": artifact_dict.get("updated")
                })
        
        notebooks_converted = []
        if all_notebooks:
            for notebook in all_notebooks:
                notebook_dict = convert_record_id_to_string(notebook)
                notebooks_converted.append({
                    "id": str(notebook_dict.get("id", "")),
                    "name": notebook_dict.get("name", ""),
                    "description": notebook_dict.get("description", ""),
                    "created": notebook_dict.get("created"),
                    "updated": notebook_dict.get("updated")
                })
        
        return {
            "total_notes": len(notes_converted),
            "total_artifacts": len(artifacts_converted),
            "total_notebooks": len(notebooks_converted),
            "notes": notes_converted,
            "artifacts": artifacts_converted,
            "notebooks": notebooks_converted,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in debug_notes: {str(e)}")
        return {
            "error": str(e),
            "total_notes": 0,
            "total_artifacts": 0,
            "total_notebooks": 0,
            "notes": [],
            "artifacts": [],
            "notebooks": [],
            "timestamp": datetime.utcnow().isoformat()
        }

# Add a specific debug endpoint for notebook notes
@router.get("/debug/notebook/{notebook_name}/notes", response_model=dict)
async def debug_notebook_notes(
    notebook_name: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Debug endpoint to check what's happening with notes for a specific notebook.
    This will help identify why the main endpoint returns empty results.
    """
    try:
        logger.info(f"🔍 === DEBUGGING NOTEBOOK: {notebook_name} ===")
        
        # Step 1: Find the notebook
        notebook_query = """
        SELECT * FROM notebook 
        WHERE string::lowercase(name) = string::lowercase($name)
        LIMIT 1;
        """
        logger.info(f"🔍 Step 1: Looking for notebook with name: '{notebook_name}'")
        notebook_res = await db.query(notebook_query, {"name": notebook_name})
        logger.info(f"🔍 Notebook query result: {notebook_res}")
        
        if not notebook_res or not notebook_res[0]:
            return {
                "error": f"Notebook '{notebook_name}' not found",
                "notebook_found": False,
                "notebook_id": None,
                "artifacts": [],
                "notes": [],
                "debug_info": {
                    "notebook_query": notebook_query,
                    "notebook_query_params": {"name": notebook_name}
                }
            }
        
        notebook = notebook_res[0]
        notebook_id = notebook['id']
        if hasattr(notebook_id, 'table_name') and hasattr(notebook_id, 'record_id'):
            notebook_id = f"{notebook_id.table_name}:{notebook_id.record_id}"
        else:
            notebook_id = str(notebook_id)
        
        logger.info(f"🔍 Step 2: Found notebook ID: {notebook_id}")
        
        # Step 2: Check all artifacts for this notebook
        artifacts_query = "SELECT * FROM artifact WHERE out = $notebook_id;"
        logger.info(f"🔍 Step 3: Checking artifacts for notebook ID: {notebook_id}")
        artifacts_res = await db.query(artifacts_query, {"notebook_id": notebook_id})
        logger.info(f"🔍 Artifacts query result: {artifacts_res}")
        
        # If no artifacts found, try with raw notebook ID
        if not artifacts_res:
            logger.info("🔄 No artifacts found with converted ID, trying with raw notebook ID...")
            raw_notebook_id = str(notebook['id'])
            logger.info(f"🔍 Step 3b: Checking artifacts for raw notebook ID: {raw_notebook_id}")
            artifacts_res = await db.query(artifacts_query, {"notebook_id": raw_notebook_id})
            logger.info(f"🔍 Artifacts query result with raw ID: {artifacts_res}")
        
        # If still no artifacts found, try with the string representation format
        if not artifacts_res:
            logger.info("🔄 No artifacts found with raw ID, trying with string representation...")
            # Create the string representation format that matches the database
            try:
                # Try to parse the raw notebook ID as a dict string
                if hasattr(notebook['id'], 'table_name') and hasattr(notebook['id'], 'record_id'):
                    dict_str = f"{{'table_name': '{notebook['id'].table_name}', 'id': '{notebook['id'].record_id}'}}"
                else:
                    # If it's already a string, try to extract the ID part
                    raw_id_str = str(notebook['id'])
                    if ':' in raw_id_str:
                        table_name, record_id = raw_id_str.split(':', 1)
                        dict_str = f"{{'table_name': '{table_name}', 'id': '{record_id}'}}"
                    else:
                        dict_str = raw_id_str
                
                logger.info(f"🔍 Step 3c: Checking artifacts for dict string format: {dict_str}")
                artifacts_res = await db.query(artifacts_query, {"notebook_id": dict_str})
                logger.info(f"🔍 Artifacts query result with dict string: {artifacts_res}")
            except Exception as e:
                logger.error(f"Error creating dict string format for debug: {e}")
        
        # If still no artifacts found, try with string contains matching
        if not artifacts_res:
            logger.info("🔄 No artifacts found with dict string, trying with string contains matching...")
            # Extract the record ID from the notebook ID
            record_id = None
            if hasattr(notebook['id'], 'record_id'):
                record_id = notebook['id'].record_id
            else:
                raw_id_str = str(notebook['id'])
                if ':' in raw_id_str:
                    record_id = raw_id_str.split(':', 1)[1]
                elif "'id': '" in raw_id_str:
                    # Extract from dict string format
                    import re
                    match = re.search(r"'id': '([^']+)'", raw_id_str)
                    if match:
                        record_id = match.group(1)
            
            if record_id:
                logger.info(f"🔍 Step 3d: Checking artifacts for record ID: {record_id}")
                # Use string contains to match the record ID within the dict string
                artifacts_query_contains = "SELECT * FROM artifact WHERE string::contains(out, $record_id);"
                artifacts_res = await db.query(artifacts_query_contains, {"record_id": record_id})
                logger.info(f"🔍 Artifacts query result with string contains: {artifacts_res}")
        
        artifacts_info = []
        if artifacts_res:
            for artifact in artifacts_res:
                # Handle both dict and string formats
                if isinstance(artifact, dict):
                    artifact_dict = convert_record_id_to_string(artifact)
                else:
                    artifact_dict = {"id": str(artifact), "in": "", "out": "", "created": None, "updated": None}
                
                artifacts_info.append({
                    "artifact_id": str(artifact_dict.get("id", "")),
                    "note_id": str(artifact_dict.get("in", "")),
                    "notebook_id": str(artifact_dict.get("out", "")),
                    "created": artifact_dict.get("created"),
                    "updated": artifact_dict.get("updated")
                })
        
        # Step 3: Try to fetch notes using the artifacts
        notes_info = []
        if artifacts_res:
            logger.info(f"🔍 Step 4: Fetching notes from {len(artifacts_res)} artifacts")
            for artifact in artifacts_res:
                try:
                    # Handle both dict and string formats
                    if isinstance(artifact, dict):
                        note_id = artifact.get("in")
                    else:
                        note_id = None
                    
                    if note_id:
                        note_id_str = str(note_id)
                        logger.info(f"🔍 Fetching note: {note_id_str}")
                        note_data = await db.select(note_id_str)
                        if note_data:
                            note_dict = convert_record_id_to_string(note_data)
                            notes_info.append({
                                "id": str(note_dict.get("id", "")),
                                "title": note_dict.get("title", ""),
                                "note_type": note_dict.get("note_type", "human"),
                                "created": note_dict.get("created"),
                                "updated": note_dict.get("updated")
                            })
                            logger.info(f"🔍 Successfully fetched note: {note_dict.get('title', '')}")
                        else:
                            logger.warning(f"🔍 Note data is None for ID: {note_id_str}")
                except Exception as e:
                    logger.error(f"🔍 Error processing artifact: {e}")
                    logger.error(f"🔍 Artifact: {artifact}")
        
        # Step 4: Check all notes in database
        all_notes_query = "SELECT * FROM note;"
        logger.info(f"🔍 Step 5: Checking all notes in database")
        all_notes = await db.query(all_notes_query)
        logger.info(f"🔍 Total notes in database: {len(all_notes) if all_notes else 0}")
        
        all_notes_info = []
        if all_notes:
            for note in all_notes:
                note_dict = convert_record_id_to_string(note)
                all_notes_info.append({
                    "id": str(note_dict.get("id", "")),
                    "title": note_dict.get("title", ""),
                    "note_type": note_dict.get("note_type", "human")
                })
        
        return {
            "notebook_found": True,
            "notebook_id": notebook_id,
            "notebook_name": notebook_name,
            "artifacts_count": len(artifacts_info),
            "artifacts": artifacts_info,
            "notes_found": len(notes_info),
            "notes": notes_info,
            "total_notes_in_db": len(all_notes_info),
            "all_notes": all_notes_info,
            "debug_info": {
                "notebook_query": notebook_query,
                "artifacts_query": artifacts_query,
                "all_notes_query": all_notes_query
            }
        }
        
    except Exception as e:
        logger.error(f"Error in debug_notebook_notes: {str(e)}")
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "notebook_name": notebook_name
        }

# Simple test endpoint to verify server is working
@router.get("/test", response_model=dict)
async def test_endpoint():
    """Simple test endpoint to verify the server is working."""
    return {
        "status": "success",
        "message": "Notes router is working!",
        "timestamp": datetime.utcnow().isoformat()
    }

# Test endpoint with database connection
@router.get("/test-db", response_model=dict)
async def test_db_connection(db: AsyncSurreal = Depends(get_db_connection)):
    """Test endpoint to verify database connection is working."""
    try:
        # Test a simple query
        result = await db.query("SELECT * FROM notebook LIMIT 1;")
        return {
            "status": "success",
            "message": "Database connection is working!",
            "notebooks_found": len(result) if result else 0,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Database connection failed: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }

# Test endpoint to directly query artifacts
@router.get("/test-artifacts", response_model=dict)
async def test_artifacts(db: AsyncSurreal = Depends(get_db_connection)):
    """Test endpoint to directly query artifacts and see their format."""
    try:
        # Get all artifacts
        artifacts_result = await db.query("SELECT * FROM artifact;")
        
        # Get all notebooks
        notebooks_result = await db.query("SELECT * FROM notebook;")
        
        artifacts_info = []
        if artifacts_result:
            for artifact in artifacts_result:
                artifact_dict = convert_record_id_to_string(artifact)
                artifacts_info.append({
                    "id": str(artifact_dict.get("id", "")),
                    "out": str(artifact_dict.get("out", "")),
                    "in": str(artifact_dict.get("in", "")),
                    "out_type": type(artifact_dict.get("out")).__name__,
                    "in_type": type(artifact_dict.get("in")).__name__
                })
        
        notebooks_info = []
        if notebooks_result:
            for notebook in notebooks_result:
                notebook_dict = convert_record_id_to_string(notebook)
                notebooks_info.append({
                    "id": str(notebook_dict.get("id", "")),
                    "name": notebook_dict.get("name", ""),
                    "id_type": type(notebook_dict.get("id")).__name__
                })
        
        return {
            "artifacts": artifacts_info,
            "notebooks": notebooks_info,
            "total_artifacts": len(artifacts_info),
            "total_notebooks": len(notebooks_info)
        }
    except Exception as e:
        return {
            "error": str(e),
            "artifacts": [],
            "notebooks": [],
            "total_artifacts": 0,
            "total_notebooks": 0
        }

# Add an endpoint to fix duplicate artifact relationships
@router.post("/notes/fix-duplicates", response_model=StatusResponse)
async def fix_duplicate_artifacts(
    db: AsyncSurreal = Depends(get_db_connection)
):
    """
    Fix duplicate artifact relationships by keeping only the most recent one for each note.
    This ensures each note is only linked to one notebook.
    """
    try:
        logger.info("🔧 Starting duplicate artifact cleanup...")
        
        # Get all artifacts
        all_artifacts_query = "SELECT * FROM artifact;"
        all_artifacts = await db.query(all_artifacts_query)
        
        if not all_artifacts:
            logger.info("✅ No artifacts found - nothing to clean up")
            return StatusResponse(status="success", message="No artifacts found - nothing to clean up")
        
        # Group artifacts by note ID (in field)
        note_to_artifacts = {}
        for artifact in all_artifacts:
            artifact_dict = convert_record_id_to_string(artifact)
            note_id = artifact_dict.get("in")
            if note_id:
                if note_id not in note_to_artifacts:
                    note_to_artifacts[note_id] = []
                note_to_artifacts[note_id].append(artifact_dict)
        
        # Find notes with multiple artifacts
        duplicates_found = 0
        for note_id, artifacts in note_to_artifacts.items():
            if len(artifacts) > 1:
                duplicates_found += 1
                logger.warning(f"🔍 Note {note_id} has {len(artifacts)} artifacts: {[a.get('id') for a in artifacts]}")
                
                # Keep only the most recent artifact (by updated timestamp)
                artifacts.sort(key=lambda x: x.get('updated', ''), reverse=True)
                artifact_to_keep = artifacts[0]
                artifacts_to_delete = artifacts[1:]
                
                # Delete the older artifacts
                for artifact in artifacts_to_delete:
                    artifact_id = artifact.get('id')
                    if artifact_id:
                        logger.info(f"🗑️ Deleting duplicate artifact {artifact_id} for note {note_id}")
                        await db.delete(artifact_id)
        
        logger.info(f"✅ Cleanup completed. Found {duplicates_found} notes with duplicate artifacts")
        return StatusResponse(
            status="success", 
            message=f"Cleanup completed. Found and fixed {duplicates_found} notes with duplicate artifacts"
        )
        
    except Exception as e:
        logger.error(f"Error fixing duplicate artifacts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Internal server error: {str(e)}"
        )