from fastapi import APIRouter, Depends, HTTPException, status, Body, Header
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from surrealdb import AsyncSurreal
from ..database import get_db_connection

from ..open_notebook.domain.transformation import Transformation, DefaultPrompts
from ..open_notebook.graphs.transformation import graph as transformation_graph
from ..open_notebook.domain.models import model_manager
from ..open_notebook.domain.notebook import Source

from ..models import (
    TransformationBase,
    TransformationCreate,
    TransformationUpdate,
    TransformationResponse,
    TransformationRunRequest,
    TransformationRunResponse,
    StatusResponse,
)

# Create router for transformation-related endpoints
router = APIRouter(
    prefix="/api/v1/transformations",
    tags=["Transformations"],
    responses={404: {"description": "Not found"}}
)

def convert_surreal_record(record: dict) -> dict:
    """Convert SurrealDB record types to standard Python types."""
    if isinstance(record, dict):
        result = {}
        for key, value in record.items():
            if hasattr(value, 'table_name') and hasattr(value, 'record_id'):
                result[key] = f"{value.table_name}:{value.record_id}"
            elif hasattr(value, 'timestamp'):
                try:
                    if callable(value.timestamp):
                        ts = int(value.timestamp()) // 1_000_000_000
                    else:
                        ts = int(value.timestamp) // 1_000_000_000
                    result[key] = datetime.fromtimestamp(ts)
                except (TypeError, ValueError):
                    result[key] = str(value)
            else:
                result[key] = convert_surreal_record(value)
        return result
    elif isinstance(record, list):
        return [convert_surreal_record(item) for item in record]
    return record

@router.get("/default", response_model=Optional[TransformationResponse], operation_id="get_default_transformation")
async def get_default_transformation(db: AsyncSurreal = Depends(get_db_connection)):
    """Get the currently set default transformation."""
    try:
        # Find transformation with apply_default = true
        query = "SELECT * FROM transformation WHERE apply_default = true LIMIT 1"
        result = await db.query(query)
        
        if result and len(result) > 0:
            transformation_data = convert_surreal_record(result[0])
            return TransformationResponse(**transformation_data)
        else:
            return None
    except Exception as e:
        print(f"Error getting default transformation: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting default transformation: {e}")

@router.post("/{transformation_id}/set-default", response_model=StatusResponse, operation_id="set_default_transformation")
async def set_default_transformation(
    transformation_id: str,
    db: AsyncSurreal = Depends(get_db_connection)
):
    """Set a transformation as the default transformation."""
    try:
        print(f"DEBUG: Setting transformation {transformation_id} as default")
        
        # Use the synchronous database connection that we know works
        from ..open_notebook.database.repository import repo_query
        
        # First, unset any existing default transformation
        unset_query = "UPDATE transformation SET apply_default = false WHERE apply_default = true"
        print(f"DEBUG: Executing unset query: {unset_query}")
        unset_result = repo_query(unset_query)
        print(f"DEBUG: Unset result: {unset_result}")
        
        # Set the specified transformation as default
        set_query = f"UPDATE {transformation_id} SET apply_default = true"
        print(f"DEBUG: Executing set query: {set_query}")
        result = repo_query(set_query)
        print(f"DEBUG: Set result: {result}")
        
        if result:
            print(f"DEBUG: Successfully set transformation {transformation_id} as default")
            return StatusResponse(status="success", message=f"Transformation {transformation_id} set as default")
        else:
            print(f"DEBUG: No result returned for transformation {transformation_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Transformation {transformation_id} not found")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error setting default transformation: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error setting default transformation: {e}")

@router.post("/unset-default", response_model=StatusResponse, operation_id="unset_default_transformation")
async def unset_default_transformation(db: AsyncSurreal = Depends(get_db_connection)):
    """Unset the current default transformation."""
    try:
        # Unset any existing default transformation
        query = "UPDATE transformation SET apply_default = false WHERE apply_default = true"
        result = await db.query(query)
        
        return StatusResponse(status="success", message="Default transformation unset successfully")
    except Exception as e:
        print(f"Error unsetting default transformation: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error unsetting default transformation: {e}")

@router.get("", response_model=List[TransformationResponse], operation_id="list_transformations")
async def list_transformations(
    sort_by: Optional[str] = "name",
    order: Optional[str] = "asc"
):
    """List all transformations, optionally sorted."""
    try:
        # Query all transformations
        transformations = Transformation.get_all()
        
        # Convert to response format
        result = []
        for t in transformations:
            data = convert_surreal_record(t.model_dump())
            result.append(TransformationResponse(**data))
            
        # Sort if requested
        if sort_by:
            reverse = order.lower() == "desc"
            result.sort(key=lambda x: getattr(x, sort_by), reverse=reverse)
            
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing transformations: {str(e)}"
        )

@router.post("", response_model=TransformationResponse, status_code=status.HTTP_201_CREATED, operation_id="create_transformation")
async def create_transformation(
    transformation: TransformationCreate
):
    """Create a new transformation."""
    try:
        # Create using domain model
        new_transformation = Transformation(**transformation.model_dump())
        new_transformation.save()
        return convert_surreal_record(new_transformation.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating transformation: {str(e)}"
        )

@router.get("/{transformation_id}", response_model=TransformationResponse, operation_id="get_transformation")
async def get_transformation(
    transformation_id: str
):
    """Get a specific transformation by ID."""
    try:
        if ":" not in transformation_id:
            transformation_id = f"transformation:{transformation_id}"
        
        transformation = Transformation.get(transformation_id)
        if not transformation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transformation {transformation_id} not found"
            )
        return convert_surreal_record(transformation.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching transformation: {str(e)}"
        )

@router.patch("/{transformation_id}", response_model=TransformationResponse, operation_id="update_transformation")
async def update_transformation(
    transformation_id: str,
    transformation: TransformationUpdate
):
    """Update a specific transformation."""
    try:
        if ":" not in transformation_id:
            transformation_id = f"transformation:{transformation_id}"
        
        # Get existing transformation
        existing = Transformation.get(transformation_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transformation {transformation_id} not found"
            )
        
        # Update fields
        update_data = transformation.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(existing, key, value)
        
        # Save changes
        existing.save()
        return convert_surreal_record(existing.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating transformation: {str(e)}"
        )

@router.delete("/{transformation_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="delete_transformation")
async def delete_transformation(
    transformation_id: str
):
    """Delete a specific transformation."""
    try:
        if ":" not in transformation_id:
            transformation_id = f"transformation:{transformation_id}"
        
        transformation = Transformation.get(transformation_id)
        if not transformation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transformation {transformation_id} not found"
            )
        transformation.delete()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting transformation: {str(e)}"
        )

 