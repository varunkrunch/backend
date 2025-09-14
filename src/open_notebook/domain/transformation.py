from typing import ClassVar, Optional
from datetime import datetime

from pydantic import Field, ConfigDict

from .base import ObjectModel, RecordModel


class Transformation(ObjectModel):
    table_name: ClassVar[str] = "transformation"
    name: str
    title: str
    description: str
    prompt: str
    apply_default: bool

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True,
        validate_assignment=True,
        extra="allow",
        str_strip_whitespace=True,
        validate_default=True,
        protected_namespaces=()
    )


class DefaultPrompts(RecordModel):
    record_id: ClassVar[str] = "open_notebook:default_prompts"
    transformation_instructions: Optional[str] = Field(
        None, description="Instructions for executing a transformation"
    )
