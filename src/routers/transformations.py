from fastapi import APIRouter, Depends, HTTPException, status, Body, Header
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from surrealdb import AsyncSurreal
from ..database import get_db_connection

from open_notebook.domain.transformation import Transformation, DefaultPrompts
from open_notebook.graphs.transformation import graph as transformation_graph
from open_notebook.domain.models import model_manager
from open_notebook.domain.notebook import Source

from ..models import (
    TransformationBase,
    TransformationCreate,
    TransformationUpdate,
    TransformationResponse,
    TransformationRunRequest,
    TransformationRunResponse,
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

 