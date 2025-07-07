# /home/ubuntu/open_notebook_full_backend/fastapi_backend/src/routers/search.py

from fastapi import (
    APIRouter, Depends, HTTPException, status, Query, Header
)
from typing import List, Optional

from surrealdb import AsyncSurreal

from ..database import get_db_connection
# Import necessary models - add SearchResult later
from ..models import (
    StatusResponse
)

# Placeholder model (should be in models.py)
from pydantic import BaseModel
class SearchResult(BaseModel):
    id: str
    title: str
    type: str # e.g., "source", "note"
    relevance: Optional[float] = None # For text search
    similarity: Optional[float] = None # For vector search
    snippet: Optional[str] = None # Context snippet
    parent_id: Optional[str] = None # e.g., notebook_id

# Create a router for search endpoints
router = APIRouter(
    prefix="/api/v1/search",
    tags=["Search"],
)

SOURCE_TABLE = "source"
NOTE_TABLE = "note"

@router.get("/text", response_model=List[SearchResult])
async def text_search(
    query: str = Query(..., description="The search query string."),
    search_sources: bool = Query(True, description="Include sources in the search."),
    search_notes: bool = Query(True, description="Include notes in the search."),
    limit: int = Query(10, description="Maximum number of results to return."),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Performs keyword-based text search across sources and/or notes."""
    if not query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query parameter cannot be empty.")
    if not search_sources and not search_notes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one of search_sources or search_notes must be true.")

    # --- Placeholder Logic ---
    # ... (rest of the logic remains the same)

    print(f"Performing text search for: 	{query}	 (Sources: {search_sources}, Notes: {search_notes}, Limit: {limit})")

    # Example placeholder response
    results = []
    if search_sources:
        results.append(SearchResult(id="source:placeholder_txt1", title="Source Result 1", type="source", relevance=0.9, snippet="...found text search query..."))
    if search_notes:
        results.append(SearchResult(id="note:placeholder_txt2", title="Note Result 1", type="note", relevance=0.8, snippet="...notes also contained the query..."))

    return results[:limit]
    # --- End Placeholder Logic ---

@router.get("/vector", response_model=List[SearchResult])
async def vector_search(
    query: str = Query(..., description="The search query string."),
    search_sources: bool = Query(True, description="Include sources in the search."),
    search_notes: bool = Query(True, description="Include notes in the search."),
    limit: int = Query(10, description="Maximum number of results to return."),
    x_provider_api_key: Optional[str] = Header(None, description="API Key for the Embedding provider (if required)"),
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Performs semantic vector search across sources and/or notes."""
    if not query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query parameter cannot be empty.")
    if not search_sources and not search_notes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one of search_sources or search_notes must be true.")

    # --- Placeholder Logic ---
    # ... (rest of the logic remains the same)

    print(f"Performing vector search for: 	{query}	 (Sources: {search_sources}, Notes: {search_notes}, Limit: {limit})")
    api_key_provided_str = "Yes" if x_provider_api_key else "No"
    print(f"API Key provided in header: {api_key_provided_str}")

    # Example placeholder response
    results = []
    if search_sources:
        results.append(SearchResult(id="source:placeholder_vec1", title="Source Vector Result 1", type="source", similarity=0.95, snippet="...semantically similar source content..."))
    if search_notes:
        results.append(SearchResult(id="note:placeholder_vec2", title="Note Vector Result 1", type="note", similarity=0.92, snippet="...semantically similar note content..."))

    return results[:limit]
    # --- End Placeholder Logic ---

