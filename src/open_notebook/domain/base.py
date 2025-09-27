from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional, Type, TypeVar, cast

from loguru import logger
from pydantic import BaseModel, ValidationError, field_validator, model_validator

from ..database.repository import (
    repo_create,
    repo_delete,
    repo_query,
    repo_relate,
    repo_update,
    repo_upsert,
)
from ..exceptions import (
    DatabaseOperationError,
    InvalidInputError,
    NotFoundError,
)

T = TypeVar("T", bound="ObjectModel")


class ObjectModel(BaseModel):
    id: Optional[str] = None
    table_name: ClassVar[str] = ""
    created: Optional[datetime] = None
    updated: Optional[datetime] = None

    @classmethod
    def _convert_surreal_types(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert SurrealDB native types to Python types."""
        if not data:
            return {}
        
        converted = {}
        for key, value in data.items():
            try:
                if value is None:
                    converted[key] = None
                elif hasattr(value, 'table_name') and hasattr(value, 'record_id'):
                    # Convert any RecordID fields to strings
                    converted[key] = f"{value.table_name}:{value.record_id}"
                elif hasattr(value, 'timestamp'):
                    # Convert DateTimeCompact to datetime
                    ts = int(value.timestamp) // 1_000_000_000  # Convert nanoseconds to seconds
                    converted[key] = datetime.fromtimestamp(ts)
                elif isinstance(value, list):
                    # Handle lists recursively
                    converted[key] = [
                        cls._convert_surreal_types(item) if isinstance(item, dict)
                        else f"{item.table_name}:{item.record_id}" if hasattr(item, 'table_name') and hasattr(item, 'record_id')
                        else datetime.fromtimestamp(int(item.timestamp) // 1_000_000_000) if hasattr(item, 'timestamp')
                        else item
                        for item in value
                    ]
                elif isinstance(value, dict):
                    # Handle nested dictionaries recursively
                    converted[key] = cls._convert_surreal_types(value)
                else:
                    converted[key] = value
            except Exception as e:
                logger.warning(f"Error converting field {key}: {str(e)}. Using original value.")
                if hasattr(value, 'table_name') and hasattr(value, 'record_id'):
                    # Ensure RecordID fields are always converted even if other conversions fail
                    converted[key] = f"{value.table_name}:{value.record_id}"
                elif hasattr(value, 'timestamp'):
                    # Ensure timestamp is converted even if other conversions fail
                    try:
                        ts = int(value.timestamp) // 1_000_000_000
                        converted[key] = datetime.fromtimestamp(ts)
                    except:
                        converted[key] = value
                else:
                    converted[key] = value
        return converted

    @classmethod
    def get_all(cls: Type[T], order_by=None) -> List[T]:
        try:
            # If called from a specific subclass, use its table_name
            if cls.table_name:
                target_class = cls
                table_name = cls.table_name
            else:
                # This path is taken if called directly from ObjectModel
                raise InvalidInputError(
                    "get_all() must be called from a specific model class"
                )

            if order_by:
                order = f" ORDER BY {order_by}"
            else:
                order = ""

            result = repo_query(f"SELECT * FROM {table_name} {order}")
            objects = []
            for obj in result:
                try:
                    # Pre-process the ID field first
                    if 'id' in obj and hasattr(obj['id'], 'table_name') and hasattr(obj['id'], 'record_id'):
                        obj['id'] = f"{obj['id'].table_name}:{obj['id'].record_id}"
                    
                    # Convert SurrealDB types before creating the object
                    converted_obj = cls._convert_surreal_types(obj)
                    
                    # Create the object and append it to the list
                    instance = target_class(**converted_obj)
                    objects.append(instance)
                   
                except ValidationError as e:
                    logger.error(f"Validation error creating object from {obj}: {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"Error creating object: {str(e)}")
                    continue

            if not objects:
                logger.warning(f"No valid objects found in {table_name}")
            return objects
        except Exception as e:
            logger.error(f"Error fetching all {cls.table_name}: {str(e)}")
            logger.exception(e)
            raise DatabaseOperationError(e)

    @classmethod
    def get(cls: Type[T], id: str) -> T:
        if not id:
            raise InvalidInputError("ID cannot be empty")
        try:
            # Get the table name from the ID (everything before the first colon)
            table_name = id.split(":")[0] if ":" in id else id

            # If we're calling from a specific subclass and IDs match, use that class
            if cls.table_name and cls.table_name == table_name:
                target_class: Type[T] = cls
            else:
                # Otherwise, find the appropriate subclass based on table_name
                found_class = cls._get_class_by_table_name(table_name)
                if not found_class:
                    raise InvalidInputError(f"No class found for table {table_name}")
                target_class = cast(Type[T], found_class)

            result = repo_query(f"SELECT * FROM {id}")
            if result:
                # Convert SurrealDB types before creating the object
                converted_obj = cls._convert_surreal_types(result[0])
                
                # Double-check ID conversion
                if 'id' in result[0] and hasattr(result[0]['id'], 'table_name') and hasattr(result[0]['id'], 'record_id'):
                    converted_obj['id'] = f"{result[0]['id'].table_name}:{result[0]['id'].record_id}"
                
                return target_class(**converted_obj)
            else:
                raise NotFoundError(f"{table_name} with id {id} not found")
        except ValidationError as e:
            logger.error(f"Validation error creating object with id {id}: {str(e)}")
            raise NotFoundError(f"Invalid object data for id {id}: {str(e)}")
        except Exception as e:
            logger.error(f"Error fetching object with id {id}: {str(e)}")
            logger.exception(e)
            raise NotFoundError(f"Object with id {id} not found - {str(e)}")

    @classmethod
    def _get_class_by_table_name(cls, table_name: str) -> Optional[Type["ObjectModel"]]:
        """Find the appropriate subclass based on table_name."""

        def get_all_subclasses(c: Type["ObjectModel"]) -> List[Type["ObjectModel"]]:
            all_subclasses: List[Type["ObjectModel"]] = []
            for subclass in c.__subclasses__():
                all_subclasses.append(subclass)
                all_subclasses.extend(get_all_subclasses(subclass))
            return all_subclasses

        for subclass in get_all_subclasses(ObjectModel):
            if hasattr(subclass, "table_name") and subclass.table_name == table_name:
                return subclass
        return None

    def needs_embedding(self) -> bool:
        return False

    def get_embedding_content(self) -> Optional[str]:
        return None

    def save(self) -> None:
        from .models import model_manager

        try:
            self.model_validate(self.model_dump(), strict=True)
            data = self._prepare_save_data()
            data["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if self.needs_embedding():
                embedding_content = self.get_embedding_content()
                if embedding_content:
                    # Get the current embedding model (don't cache it globally)
                    current_embedding_model = model_manager.embedding_model
                    if not current_embedding_model:
                        logger.warning(
                            "No embedding model found. Content will not be searchable."
                        )
                    data["embedding"] = (
                        current_embedding_model.embed([embedding_content])[0]
                        if current_embedding_model
                        else []
                    )

            if self.id is None:
                data["created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                repo_result = repo_create(self.__class__.table_name, data)
            else:
                data["created"] = (
                    self.created.strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(self.created, datetime)
                    else self.created
                )
                logger.debug(f"Updating record with id {self.id}")
                repo_result = repo_update(self.id, data)

            # Update the current instance with the result
            result_data = repo_result[0]
            
            # Convert the entire result to handle RecordID objects
            converted_result = self._convert_surreal_types(result_data)
            
            for key, value in converted_result.items():
                if hasattr(self, key):
                    if isinstance(getattr(self, key), BaseModel):
                        object.__setattr__(self, key, type(getattr(self, key))(**value))
                    else:
                        object.__setattr__(self, key, value)

        except ValidationError as e:
            logger.error(f"Validation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Error saving record: {e}")
            raise

        except Exception as e:
            logger.error(f"Error saving {self.__class__.table_name}: {str(e)}")
            logger.exception(e)
            raise DatabaseOperationError(e)

    def _prepare_save_data(self) -> Dict[str, Any]:
        data = self.model_dump()
        return {key: value for key, value in data.items() if value is not None}

    def delete(self) -> bool:
        if self.id is None:
            raise InvalidInputError("Cannot delete object without an ID")
        try:
            logger.debug(f"Deleting record with id {self.id}")
            return repo_delete(self.id)
        except Exception as e:
            logger.error(
                f"Error deleting {self.__class__.table_name} with id {self.id}: {str(e)}"
            )
            raise DatabaseOperationError(
                f"Failed to delete {self.__class__.table_name}"
            )

    def relate(
        self, relationship: str, target_id: str, data: Optional[Dict] = {}
    ) -> Any:
        if not relationship or not target_id or not self.id:
            raise InvalidInputError("Relationship and target ID must be provided")
        try:
            return repo_relate(
                source=self.id, relationship=relationship, target=target_id, data=data
            )
        except Exception as e:
            logger.error(f"Error creating relationship: {str(e)}")
            logger.exception(e)
            raise DatabaseOperationError(e)

    @field_validator("created", "updated", mode="before")
    @classmethod
    def parse_datetime(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class RecordModel(BaseModel):
    record_id: ClassVar[str]
    auto_save: ClassVar[bool] = (
        False  # Default to False, can be overridden in subclasses
    )
    _instances: ClassVar[Dict[str, "RecordModel"]] = {}  # Store instances by record_id

    class Config:
        validate_assignment = True
        arbitrary_types_allowed = True
        extra = "allow"
        from_attributes = True
        defer_build = True

    def __new__(cls, **kwargs):
        # If an instance already exists for this record_id, return it
        if cls.record_id in cls._instances:
            instance = cls._instances[cls.record_id]
            # Update instance with any new kwargs if provided
            if kwargs:
                for key, value in kwargs.items():
                    setattr(instance, key, value)
            return instance

        # If no instance exists, create a new one
        instance = super().__new__(cls)
        cls._instances[cls.record_id] = instance
        return instance

    def __init__(self, **kwargs):
        # Only initialize if this is a new instance
        if not hasattr(self, "_initialized"):
            object.__setattr__(self, "__dict__", {})
            # Load data from DB first
            result = repo_query(f"SELECT * FROM {self.record_id};")

            # Initialize with DB data and any overrides
            init_data = {}
            if result and result[0]:
                init_data.update(result[0])

            # Override with any provided kwargs
            if kwargs:
                init_data.update(kwargs)

            # Initialize base model first
            super().__init__(**init_data)

            # Mark as initialized
            object.__setattr__(self, "_initialized", True)

    @classmethod
    def get_instance(cls) -> "RecordModel":
        """Get or create the singleton instance"""
        return cls()

    @model_validator(mode="after")
    def auto_save_validator(self):
        if self.__class__.auto_save:
            self.update()
        return self

    def update(self):
        # Get all non-ClassVar fields and their values
        data = {
            field_name: getattr(self, field_name)
            for field_name, field_info in self.model_fields.items()
            if not str(field_info.annotation).startswith("typing.ClassVar")
        }

        repo_upsert(self.record_id, data)

        result = repo_query(f"SELECT * FROM {self.record_id};")
        if result:
            for key, value in result[0].items():
                if hasattr(self, key):
                    object.__setattr__(
                        self, key, value
                    )  # Use object.__setattr__ to avoid triggering validation again

        return self

    @classmethod
    def clear_instance(cls):
        """Clear the singleton instance (useful for testing)"""
        if cls.record_id in cls._instances:
            del cls._instances[cls.record_id]

    def patch(self, model_dict: dict):
        """Update model attributes from dictionary and save"""
        for key, value in model_dict.items():
            setattr(self, key, value)
        self.update()