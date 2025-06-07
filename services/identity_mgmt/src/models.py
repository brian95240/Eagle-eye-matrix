from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
import datetime
import uuid

# --- Base Models (reused or adapted) ---

class SourceReference(BaseModel):
    """Reference to the source of a piece of information."""
    event_id: str
    service_name: str
    timestamp: datetime.datetime
    correlation_id: Optional[str] = None

class GeolocationEstimate(BaseModel):
    """Simplified Geolocation Estimate (assuming structure from geo_estimator)."""
    media_id: str
    estimated_lat: float
    estimated_lon: float
    confidence: float
    supporting_evidence: List[str]
    estimation_timestamp: datetime.datetime

class FaceIdentificationResult(BaseModel):
    """Simplified Face Identification Result (assuming structure from face_identifier)."""
    detection_id: str
    media_id: str
    potential_matches: List[Dict[str, Any]] # Simplified match structure
    identification_timestamp: datetime.datetime

# --- Identity Profile Models ---

class IdentityAttribute(BaseModel):
    """Represents a single piece of information linked to an identity."""
    attribute_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    attribute_type: str = Field(..., description="Type of attribute (e.g., name, address, face_detection, geo_location)")
    value: Union[str, float, int, bool, Dict[str, Any], List[Any]] # Flexible value type
    confidence: float = Field(..., description="Confidence score for this attribute.")
    source: SourceReference
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

class IdentityProfile(BaseModel):
    """Represents an aggregated profile for a potential identity."""
    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID for this aggregated profile.")
    attributes: List[IdentityAttribute] = Field(default_factory=list, description="List of attributes associated with this identity.")
    linked_profiles: List[str] = Field(default_factory=list, description="IDs of other profiles potentially linked to this one.")
    overall_confidence: float = Field(0.0, description="Overall confidence score for the aggregated profile.")
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

# --- Event Payloads for Identity Management ---

class IdentityProfileUpdatePayload(BaseModel):
    """Payload for events indicating an identity profile has been updated."""
    profile_id: str
    updated_attributes: List[IdentityAttribute] = Field(default_factory=list)
    change_description: str # e.g., "Added face match", "Linked new geolocation"

# --- Credential Verification Models (Placeholder) ---

class VerificationRequest(BaseModel):
    """Request to verify a specific credential or attribute."""
    profile_id: str
    attribute_id: str
    verification_method: str # e.g., "public_record_check", "cross_reference"

class VerificationResult(BaseModel):
    """Result of a verification attempt."""
    request_id: str # Link back to the VerificationRequest
    profile_id: str
    attribute_id: str
    is_verified: bool
    confidence: float
    verification_details: str
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

