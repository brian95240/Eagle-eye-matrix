from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import datetime

# --- Input/Ingestion Models ---

class IngestedMedia(BaseModel):
    """Represents media data ingested for geolocation."""
    media_id: str = Field(..., description="Unique identifier for the media item")
    media_type: str = Field(..., description="Type of media (e.g., image, video)")
    source_url: Optional[str] = Field(None, description="Original URL if available")
    local_path: str = Field(..., description="Path to the media file in storage")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extracted metadata (EXIF, etc.)")
    ingestion_timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)

# --- CV Analysis Models ---

class DetectedObject(BaseModel):
    """Represents an object detected in the media."""
    object_type: str = Field(..., description="Type of object (e.g., landmark, sign, vehicle)")
    confidence: float = Field(..., description="Detection confidence score")
    bounding_box: List[float] = Field(..., description="Coordinates of the bounding box [xmin, ymin, xmax, ymax]")
    features: Optional[List[float]] = Field(None, description="Extracted feature vector for the object")

class CVAnalysisResult(BaseModel):
    """Results from the Computer Vision analysis stage."""
    media_id: str = Field(..., description="Identifier of the analyzed media")
    detected_objects: List[DetectedObject] = Field(default_factory=list)
    analysis_timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)

# --- Knowledge Base Models ---

class GeoKnowledgeEntry(BaseModel):
    """Represents an entry in the geospatial knowledge base."""
    entry_id: str = Field(..., description="Unique identifier for the knowledge entry")
    entry_type: str = Field(..., description="Type of entry (e.g., landmark, region, address)")
    name: Optional[str] = Field(None, description="Name of the place/object")
    latitude: float = Field(..., description="Latitude coordinate")
    longitude: float = Field(..., description="Longitude coordinate")
    # Could add geometry (e.g., GeoJSON polygon), feature vectors, etc.
    metadata: Dict[str, Any] = Field(default_factory=dict)

# --- Estimation Models ---

class GeolocationEstimate(BaseModel):
    """Represents the final estimated geolocation."""
    media_id: str = Field(..., description="Identifier of the media being geolocated")
    latitude: float = Field(..., description="Estimated latitude")
    longitude: float = Field(..., description="Estimated longitude")
    confidence: float = Field(..., description="Confidence score of the estimation")
    radius_meters: Optional[float] = Field(None, description="Estimated uncertainty radius in meters")
    method: str = Field(..., description="Method used for estimation (e.g., CV_MATCH, METADATA, FUSION)")
    supporting_evidence: List[str] = Field(default_factory=list, description="IDs or descriptions of evidence used")
    estimation_timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)

