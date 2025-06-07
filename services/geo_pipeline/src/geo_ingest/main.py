import asyncio
import json
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Form
import redis.asyncio as redis
from typing import Dict, Any, Optional
import datetime
import uuid
import os
from PIL import Image
from PIL.ExifTags import TAGS

# Assuming models are in a shared location or copied
# Adjust import path based on final structure
from ..models import IngestedMedia

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
SERVICE_NAME = "geo-ingest"
EVENT_STREAM_KEY = "eem_event_stream"
MEDIA_STORAGE_PATH = "/home/ubuntu/eagle_eye_matrix/media_storage" # Example storage path

# Ensure storage directory exists
os.makedirs(MEDIA_STORAGE_PATH, exist_ok=True)

# --- Redis Connection ---
async def get_redis_connection() -> redis.Redis:
    """Dependency to get an async Redis connection."""
    connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    try:
        yield connection
    finally:
        await connection.close()

# --- Helper Functions ---
def extract_exif_data(image_path: str) -> Dict[str, Any]:
    """Extracts EXIF data from an image file."""
    metadata = {}
    try:
        with Image.open(image_path) as img:
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, tag_id)
                    # Decode bytes if necessary
                    if isinstance(value, bytes):
                        try:
                            value = value.decode()
                        except UnicodeDecodeError:
                            value = repr(value) # Represent as string if decoding fails
                    metadata[str(tag_name)] = value
                # Check for GPSInfo specifically
                gps_info = metadata.get("GPSInfo")
                if gps_info:
                    metadata["has_gps"] = True
                else:
                    metadata["has_gps"] = False
            else:
                 metadata["has_gps"] = False
    except Exception as e:
        print(f"Error extracting EXIF data from {image_path}: {e}")
        metadata["has_gps"] = False # Assume no GPS if error
    return metadata

async def publish_event(redis_conn: redis.Redis, event_type: str, payload: Dict[str, Any], correlation_id: Optional[str] = None):
    """Publishes an event to the Redis stream."""
    event = {
        "eventId": str(uuid.uuid4()),
        "eventType": event_type,
        "sourceService": SERVICE_NAME,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "correlationId": correlation_id or str(uuid.uuid4()),
        "payload": payload
    }
    try:
        await redis_conn.xadd(EVENT_STREAM_KEY, {"event_data": json.dumps(event)})
        print(f"Published event: {event_type} (ID: {event[	eventId	]})")
    except Exception as e:
        print(f"Error publishing event {event_type}: {e}")

# --- FastAPI App ---
app = FastAPI(
    title="EEM Geolocation Ingestion Service",
    description="Ingests media files, extracts metadata, and triggers analysis.",
    version="0.1.0"
)

@app.post("/ingest/upload", response_model=IngestedMedia)
async def ingest_media_upload(
    file: UploadFile = File(...),
    source_url: Optional[str] = Form(None),
    # Add other form fields if needed (e.g., initial tags, priority)
    redis_conn: redis.Redis = Depends(get_redis_connection)
) -> IngestedMedia:
    """Ingests a media file uploaded via form-data."""
    media_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1].lower()
    # Basic validation for image types
    if file_extension not in [".jpg", ".jpeg", ".png", ".tiff", ".tif"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    local_path = os.path.join(MEDIA_STORAGE_PATH, f"{media_id}{file_extension}")

    try:
        # Save the uploaded file
        with open(local_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Extract metadata (basic EXIF for now)
        metadata = extract_exif_data(local_path)

        ingested_data = IngestedMedia(
            media_id=media_id,
            media_type="image", # Assuming image for now
            source_url=source_url,
            local_path=local_path,
            metadata=metadata
        )

        # Publish ingestion event
        await publish_event(
            redis_conn,
            event_type="data.image.ingested",
            payload=ingested_data.model_dump(mode="json") # Serialize properly for event
        )

        return ingested_data

    except Exception as e:
        # Clean up partially saved file if error occurs
        if os.path.exists(local_path):
            os.remove(local_path)
        print(f"Error during media ingestion: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest media: {e}"
        )
    finally:
        await file.close()

# Add endpoint for ingesting via URL if needed
# @app.post("/ingest/url", ...)

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check(redis_conn: redis.Redis = Depends(get_redis_connection)) -> Dict[str, str]:
    """Basic health check endpoint."""
    try:
        await redis_conn.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"
    return {"status": "ok", "redis_status": redis_status}

# --- Main execution (for running with uvicorn) ---
# Example: uvicorn services.geo_pipeline.src.geo_ingest.main:app --reload --port 8010

