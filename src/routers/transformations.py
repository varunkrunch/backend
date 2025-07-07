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
                ts = int(value.timestamp) // 1_000_000_000
                result[key] = datetime.fromtimestamp(ts)
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

@router.post("/run", response_model=TransformationRunResponse, operation_id="run_transformation")
async def run_transformation_endpoint(
    request: TransformationRunRequest,
    x_provider_api_key: Optional[str] = Header(None, description="API Key for the AI provider (if required by the selected model)")
):
    """Run a transformation on input text.
    
    This endpoint applies a transformation to the provided input text using the specified
    language model. If no model is specified, it uses the default transformation model.
    The transformation will automatically include any default instructions configured in the system.
    
    If a source_id is provided, the transformation result will be added as an insight to that source.
    """
    try:
        # Get the transformation
        if ":" not in request.transformation_id:
            request.transformation_id = f"transformation:{request.transformation_id}"
            
        transformation = Transformation.get(request.transformation_id)
        if not transformation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transformation {request.transformation_id} not found"
            )
        
        # Get the model
        llm_id = request.llm_id
        if not llm_id:
            # Use default transformation model
            model = model_manager.get_default_model("transformation")
            if not model:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No default transformation model configured"
                )
            llm_id = model.id
        
        # Get source if provided
        source = None
        if request.source_id:
            if ":" not in request.source_id:
                request.source_id = f"source:{request.source_id}"
            source = Source.get(request.source_id)
            if not source:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Source {request.source_id} not found"
                )
        
        # Run the transformation using the graph
        result = transformation_graph.invoke(
            {
                "input_text": request.input_text,
                "transformation": transformation,
                "source": source
            },
            config={"configurable": {"model_id": llm_id}}
        )
        
        return TransformationRunResponse(
            output=result["output"],
            llm_used=llm_id,
            transformation_name=transformation.name
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error running transformation: {str(e)}"
        )

@router.post("/sources/{source_id}/apply", response_model=TransformationRunResponse, operation_id="apply_transformation_to_source")
async def apply_transformation_to_source(
    source_id: str,
    request: TransformationRunRequest,
    x_provider_api_key: Optional[str] = Header(None, description="API Key for the AI provider (if required by the selected model)")
):
    """Apply a transformation to a source and store the result as an insight."""
    try:
        # Get the source
        if ":" not in source_id:
            source_id = f"source:{source_id}"
        source = Source.get(source_id)
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source {source_id} not found"
            )
        
        # Get the transformation
        if ":" not in request.transformation_id:
            request.transformation_id = f"transformation:{request.transformation_id}"
        transformation = Transformation.get(request.transformation_id)
        if not transformation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transformation {request.transformation_id} not found"
            )
        
        # Get the model
        llm_id = request.llm_id
        if not llm_id:
            model = model_manager.get_default_model("transformation")
            if not model:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No default transformation model configured"
                )
            llm_id = model.id
        
        # Run the transformation using the graph
        result = transformation_graph.invoke(
            {
                "input_text": source.full_text,
                "transformation": transformation,
                "source": source
            },
            config={"configurable": {"model_id": llm_id}}
        )
        
        return TransformationRunResponse(
            output=result["output"],
            llm_used=llm_id,
            transformation_name=transformation.name
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error applying transformation to source: {str(e)}"
        ) 