import asyncio
import json
import uuid
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File
import redis.asyncio as redis
from typing import Dict, Any, Optional
import datetime
import os
from PIL import Image # For basic image validation
import io

# Assuming models are in a shared location or copied
# Adjust import path based on final structure
from ..models import MediaReference

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
SERVICE_NAME = "face-ingest"
EVENT_STREAM_KEY = "eem_event_stream"
OUTPUT_EVENT_TYPE = "request.face_rec.detection" # Event to trigger face detection
MEDIA_STORAGE_DIR = "/home/ubuntu/eagle_eye_matrix/storage/face_media" # Example storage path

# Ensure storage directory exists
os.makedirs(MEDIA_STORAGE_DIR, exist_ok=True)

# --- Redis Connection ---
async def get_redis_connection() -> redis.Redis:
    """Dependency to get an async Redis connection."""
    connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    try:
        yield connection
    finally:
        await connection.close()

# --- Helper Functions ---
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
        print(f"Published event: {event_type} (ID: {event['eventId']})")
    except Exception as e:
        print(f"Error publishing event {event_type}: {e}")

# --- FastAPI App ---
app = FastAPI(
    title="EEM Face Ingestion Service",
    description="Handles media uploads for facial recognition processing.",
    version="0.1.0"
)

@app.post("/ingest/face", response_model=MediaReference, status_code=status.HTTP_202_ACCEPTED)
async def ingest_media_for_face_rec(
    file: UploadFile = File(...),
    redis_conn: redis.Redis = Depends(get_redis_connection)
) -> MediaReference:
    """Accepts media upload, saves it, and triggers face detection."""
    media_id = str(uuid.uuid4())
    upload_timestamp = datetime.datetime.now(datetime.timezone.utc)
    file_extension = os.path.splitext(file.filename)[1].lower()
    storage_path = os.path.join(MEDIA_STORAGE_DIR, f"{media_id}{file_extension}")

    # Basic validation (e.g., check if it's an image)
    media_type = "unknown"
    if file.content_type.startswith("image/"):
        media_type = "image"
        try:
            # Try to open image to validate format
            contents = await file.read()
            await file.seek(0) # Reset file pointer after reading
            img = Image.open(io.BytesIO(contents))
            img.verify() # Verify image data
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid image file: {e}")
    elif file.content_type.startswith("video/"):
         media_type = "video"
         # Add video validation if needed
    else:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported media type. Only images and videos are supported.")

    # Save the file (async saving recommended for large files in production)
    try:
        with open(storage_path, "wb") as buffer:
            contents = await file.read()
            buffer.write(contents)
        print(f"Saved media {media_id} to {storage_path}")
    except Exception as e:
        print(f"Error saving file {media_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save uploaded media.")
    finally:
        await file.close()

    # Create media reference
    media_ref = MediaReference(
        media_id=media_id,
        storage_path=storage_path,
        media_type=media_type,
        upload_timestamp=upload_timestamp
    )

    # Publish event to trigger face detection
    await publish_event(
        redis_conn,
        event_type=OUTPUT_EVENT_TYPE,
        payload=media_ref.model_dump(mode="json"),
        correlation_id=media_id # Use media_id as correlation ID
    )

    return media_ref

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
# Example: uvicorn services.face_rec.src.face_ingest.main:app --reload --port 8020

