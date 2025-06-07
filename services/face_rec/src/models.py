from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import datetime
import uuid

# --- Base Models ---

class MediaReference(BaseModel):
    """Reference to an ingested media file."""
    media_id: str = Field(..., description="Unique ID of the ingested media.")
    storage_path: str = Field(..., description="Path where the media is stored.")
    media_type: str = Field(..., description="Type of media (e.g., image, video).")
    upload_timestamp: datetime.datetime = Field(..., description="Timestamp when the media was uploaded.")

# --- Ingestion Models ---

class FaceIngestRequest(BaseModel):
    """Model for requesting facial recognition on an uploaded media file."""
    media_id: str = Field(..., description="Unique ID of the media to process.")
    # Add any specific parameters for ingestion if needed

# --- Detection Models ---

class BoundingBox(BaseModel):
    """Represents a bounding box around a detected face."""
    top: int
    right: int
    bottom: int
    left: int

class FaceDetection(BaseModel):
    """Details of a single detected face within media."""
    detection_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID for this specific detection.")
    bounding_box: BoundingBox
    confidence: Optional[float] = Field(None, description="Confidence score from the detector.")
    landmarks: Optional[Dict[str, List[tuple[int, int]]]] = Field(None, description="Facial landmarks (e.g., eyes, nose, mouth).")

class FaceDetectionResult(BaseModel):
    """Results from the face detection process for a given media item."""
    media_id: str
    detections: List[FaceDetection] = Field(default_factory=list)
    detection_timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

# --- Encoding/Embedding Models ---

class FaceEncoding(BaseModel):
    """Represents the numerical embedding (vector) of a detected face."""
    detection_id: str # Links back to the specific FaceDetection
    media_id: str
    encoding: List[float] # The actual face embedding vector
    model_name: str = Field(..., description="Name of the model used for encoding.")
    encoding_timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

# --- Identification/Matching Models ---

class IdentityMatch(BaseModel):
    """Represents a potential match between a detected face and a known identity."""
    known_identity_id: str
    match_score: float # Score indicating similarity (e.g., distance or probability)
    is_match: bool # Whether the score meets the threshold for a match

class FaceIdentificationResult(BaseModel):
    """Results of attempting to identify a detected face."""
    detection_id: str
    media_id: str
    potential_matches: List[IdentityMatch] = Field(default_factory=list)
    identification_timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

# --- Identity Database Models (Simplified) ---

class KnownIdentity(BaseModel):
    """Represents a known identity in the database."""
    identity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    associated_encodings: List[FaceEncoding] = Field(default_factory=list) # Store known encodings
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

