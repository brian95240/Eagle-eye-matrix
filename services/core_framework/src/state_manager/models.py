from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import datetime

class ServiceStateEnum(str, Enum):
    """Enumeration for possible service states."""
    INITIALIZING = "Initializing"
    IDLE = "Idle"
    ACTIVE = "Active"
    PROCESSING = "Processing"
    ERROR = "Error"
    SHUTTING_DOWN = "ShuttingDown"
    UNKNOWN = "Unknown"

class TaskStateEnum(str, Enum):
    """Enumeration for possible task/workflow states."""
    PENDING = "Pending"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"

class DataProcessingStateEnum(str, Enum):
    """Enumeration for possible data processing states."""
    RECEIVED = "Received"
    QUEUED = "Queued"
    GEOLOCATION_PROCESSING = "GeolocationProcessing"
    FACEREC_PROCESSING = "FaceRecProcessing"
    RECORDS_PROCESSING = "RecordsProcessing"
    CORRELATING = "Correlating"
    ANALYSIS_COMPLETE = "AnalysisComplete"
    ERROR = "Error"

class EntityState(BaseModel):
    """Represents the state of a managed entity (service, task, data)."""
    entity_id: str = Field(..., description="Unique identifier of the entity")
    entity_type: str = Field(..., description="Type of the entity (e.g., 'service', 'task', 'data')")
    state: str = Field(..., description="Current state of the entity (e.g., 'Running', 'Idle', 'Completed')")
    last_updated: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="Timestamp of the last state update")
    details: Optional[Dict[str, Any]] = Field(None, description="Optional dictionary for additional state details")

    class Config:
        use_enum_values = True # Ensure enum values are used in serialization

