# Note Creation API Guide

This guide covers the note creation functionality in the Open Notebook FastAPI backend, including proper endpoints, frontend integration, and troubleshooting.

## Overview

The note creation system provides multiple endpoints for creating notes with different levels of validation and error handling:

1. **Robust Endpoint** (`/api/v1/notes/create`) - Production-ready with comprehensive validation
2. **Test Endpoint** (`/api/v1/notes/test-create`) - Detailed debugging information
3. **Legacy Endpoint** (`/api/v1/notes`) - Original endpoint (fixed)

## Endpoints

### 1. Robust Note Creation Endpoint

**URL:** `POST /api/v1/notes/create`

**Description:** Production-ready endpoint with comprehensive validation and error handling.

**Parameters:**
- `notebook_name` (query parameter, optional): Name of the notebook to associate the note with
- `note_data` (JSON body): Note creation data

**Request Body:**
```json
{
  "title": "My Note Title",
  "content": "This is the note content",
  "note_type": "human"
}
```

**Response:**
```json
{
  "id": "note:abc123",
  "title": "My Note Title",
  "content": "This is the note content",
  "note_type": "human",
  "created": "2024-01-01T12:00:00",
  "updated": "2024-01-01T12:00:00",
  "embedding": []
}
```

**Features:**
- ✅ Input validation
- ✅ Automatic title generation if not provided
- ✅ Embedding creation (if model available)
- ✅ Notebook linking with verification
- ✅ Comprehensive error handling
- ✅ Detailed logging

### 2. Test Note Creation Endpoint

**URL:** `POST /api/v1/notes/test-create`

**Description:** Debug endpoint that provides detailed information about each step of the note creation process.

**Response:**
```json
{
  "success": true,
  "steps": [
    "1. Input validation",
    "✓ Input validation passed",
    "2. Data preparation",
    "✓ Data prepared: {...}",
    "3. Database creation",
    "✓ Note created with ID: note:abc123",
    "4. Embedding creation",
    "✓ Embedding created for note note:abc123",
    "5. Notebook linking",
    "✓ Found notebook ID: notebook:xyz789",
    "✓ Linked note note:abc123 to notebook notebook:xyz789",
    "✓ Relationship verified: [...]",
    "6. Note verification",
    "✓ Note retrieved successfully: {...}",
    "7. Response preparation",
    "✓ Response prepared successfully"
  ],
  "note_id": "note:abc123",
  "notebook_id": "notebook:xyz789",
  "errors": [],
  "warnings": [],
  "final_response": {...}
}
```

### 3. Legacy Note Creation Endpoint

**URL:** `POST /api/v1/notes`

**Description:** Original endpoint (now fixed with proper indentation and error handling).

## Frontend Integration

### Updated Frontend Code

The frontend has been updated to use the robust endpoint:

```typescript
const handleCreateNote = async () => {
  if (!selectedNotebook || !newNote.content?.trim()) return;
  
  setAddingNote(true);
  try {
    // Use the new robust endpoint
    const response = await fetch(`${API_BASE}/notes/create?notebook_name=${encodeURIComponent(selectedNotebook.name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newNote)
    });
    
    if (response.ok) {
      const createdNote = await response.json();
      setNotes(prev => [createdNote, ...prev]);
      setAddNoteDialogOpen(false);
      setNewNote({ title: '', content: '', note_type: 'human' });
      setSnackbar({
        open: true,
        message: 'Note created successfully',
        severity: 'success'
      });
    } else {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to create note');
    }
  } catch (error) {
    console.error('Error creating note:', error);
    setSnackbar({
      open: true,
      message: error instanceof Error ? error.message : 'Failed to create note',
      severity: 'error'
    });
  } finally {
    setAddingNote(false);
  }
};
```

## Testing

### Running the Test Script

1. Start the FastAPI server:
```bash
cd fastapi_backend
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

2. Run the test script:
```bash
cd fastapi_backend
python test_note_endpoints.py
```

### Manual Testing with curl

```bash
# Test the robust endpoint
curl -X POST "http://localhost:8000/api/v1/notes/create?notebook_name=Big%20Data%20Analytics" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Note",
    "content": "This is a test note content",
    "note_type": "human"
  }'

# Test the debug endpoint
curl -X POST "http://localhost:8000/api/v1/notes/test-create?notebook_name=Big%20Data%20Analytics" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Debug Note",
    "content": "This is a debug note",
    "note_type": "human"
  }'

# List notes in a notebook
curl "http://localhost:8000/api/v1/notebooks/by-name/Big%20Data%20Analytics/notes"
```

## Error Handling

### Common Error Scenarios

1. **Empty Content**
   - **Error:** 400 Bad Request
   - **Message:** "Note content is required and cannot be empty"
   - **Solution:** Ensure content is provided and not empty

2. **Invalid Notebook**
   - **Error:** 404 Not Found
   - **Message:** "Notebook with name '...' not found"
   - **Solution:** Check notebook name spelling and ensure it exists

3. **Database Connection Issues**
   - **Error:** 500 Internal Server Error
   - **Message:** "Failed to create note in database"
   - **Solution:** Check database connection and SurrealDB status

4. **Embedding Model Issues**
   - **Warning:** Embedding creation fails
   - **Behavior:** Note is created without embedding
   - **Solution:** Check embedding model configuration

### Error Response Format

```json
{
  "detail": "Error message description"
}
```

## Database Schema

### Note Table Structure

```sql
-- Note table
CREATE note SCHEMAFULL;
DEFINE FIELD title ON note TYPE string;
DEFINE FIELD content ON note TYPE string;
DEFINE FIELD note_type ON note TYPE string;
DEFINE FIELD created ON note TYPE datetime;
DEFINE FIELD updated ON note TYPE datetime;
DEFINE FIELD embedding ON note TYPE array;
```

### Relationship Structure

```sql
-- Artifact relationship between notes and notebooks
DEFINE TABLE artifact SCHEMAFULL;
DEFINE FIELD out ON artifact TYPE record(notebook);
DEFINE FIELD in ON artifact TYPE record(note);
DEFINE FIELD created ON artifact TYPE datetime;
DEFINE FIELD updated ON artifact TYPE datetime;
```

## Troubleshooting

### Issue: "Failed to create note"

1. **Check database connection:**
   ```bash
   curl "http://localhost:8000/api/v1/test-db-query"
   ```

2. **Check server logs:**
   ```bash
   # Look for error messages in the FastAPI server output
   ```

3. **Test with debug endpoint:**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/notes/test-create?notebook_name=Big%20Data%20Analytics" \
     -H "Content-Type: application/json" \
     -d '{"title": "Test", "content": "Test content", "note_type": "human"}'
   ```

### Issue: "Notebook not found"

1. **List all notebooks:**
   ```bash
   curl "http://localhost:8000/api/v1/notebooks"
   ```

2. **Check notebook name spelling:**
   - Ensure exact case matching
   - Check for extra spaces
   - Verify the notebook exists

### Issue: Frontend integration problems

1. **Check API base URL:**
   - Ensure `API_BASE` is correctly set in frontend
   - Default: `http://localhost:8000/api/v1`

2. **Check CORS settings:**
   - Ensure FastAPI CORS middleware is configured
   - Check browser console for CORS errors

3. **Check network requests:**
   - Use browser developer tools to inspect network requests
   - Verify request/response format

## Best Practices

1. **Always validate input** on both frontend and backend
2. **Use the robust endpoint** for production applications
3. **Handle errors gracefully** in the frontend
4. **Test with the debug endpoint** when troubleshooting
5. **Monitor server logs** for detailed error information
6. **Use proper error messages** to help users understand issues

## Future Enhancements

1. **Batch note creation** for multiple notes
2. **Note templates** for common note types
3. **Rich text support** for note content
4. **Note versioning** for tracking changes
5. **Note sharing** between notebooks
6. **Advanced search** with filters and sorting

