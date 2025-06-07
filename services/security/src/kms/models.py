from pydantic import BaseModel, Field
from typing import Optional, List
import datetime

class ApiKey(BaseModel):
    """Represents an API key with its metadata."""
    key_id: str = Field(..., description="Unique identifier for the key")
    key_value: str = Field(..., description="The actual API key string (masked in most responses)")
    service_name: str = Field(..., description="The service this key is associated with")
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now, description="Timestamp when the key was created")
    expires_at: Optional[datetime.datetime] = Field(None, description="Timestamp when the key expires (if applicable)")
    is_active: bool = Field(True, description="Whether the key is currently active")
    last_used_at: Optional[datetime.datetime] = Field(None, description="Timestamp when the key was last used")
    metadata: Optional[dict] = Field(None, description="Optional metadata associated with the key")

class CreateKeyRequest(BaseModel):
    """Request model for creating a new API key."""
    service_name: str = Field(..., description="The service the key will be associated with")
    expires_in_days: Optional[int] = Field(None, description="Optional number of days until the key expires")
    metadata: Optional[dict] = Field(None, description="Optional metadata to associate with the key")

class CreateKeyResponse(BaseModel):
    """Response model after creating a new API key."""
    key_id: str
    key_value: str # The new key is returned only once upon creation
    service_name: str
    created_at: datetime.datetime
    expires_at: Optional[datetime.datetime]

class ValidateKeyRequest(BaseModel):
    """Request model for validating an API key."""
    key_value: str = Field(..., description="The API key to validate")

class ValidateKeyResponse(BaseModel):
    """Response model after validating an API key."""
    is_valid: bool
    key_id: Optional[str] = None
    service_name: Optional[str] = None
    reason: Optional[str] = None # Reason if not valid

class KeyInfoResponse(BaseModel):
    """Response model for retrieving key information (masked key value)."""
    key_id: str
    service_name: str
    created_at: datetime.datetime
    expires_at: Optional[datetime.datetime]
    is_active: bool
    last_used_at: Optional[datetime.datetime]
    metadata: Optional[dict]

