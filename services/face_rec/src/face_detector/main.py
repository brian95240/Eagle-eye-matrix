import asyncio
import json
import uuid
from fastapi import FastAPI, HTTPException, Depends, status
import redis.asyncio as redis
from typing import Dict, Any, Optional, List
import datetime
import os
import random # For placeholder logic
from PIL import Image # To get image dimensions for placeholder
import io

# Assuming models are in a shared location or copied
# Adjust import path based on final structure
from ..models import MediaReference, FaceDetection, FaceDetectionResult, BoundingBox

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
SERVICE_NAME = "face-detector"
EVENT_STREAM_KEY = "eem_event_stream"
CONSUMER_GROUP_NAME = "face_detector_group"
CONSUMER_NAME = "consumer_1"
INPUT_EVENT_TYPE = "request.face_rec.detection"
OUTPUT_EVENT_TYPE = "result.face_rec.detected"

# --- Practice Mode Check ---
PRACTICE_MODE = os.environ.get("EEM_PRACTICE_MODE", "false").lower() == "true"
if PRACTICE_MODE:
    print("INFO: Face Detector running in PRACTICE MODE")

# --- Redis Connection ---
async def get_redis_connection() -> redis.Redis:
    """Dependency to get an async Redis connection."""
    connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    try:
        yield connection
    finally:
        await connection.close()

# --- Helper Functions ---
async def publish_event(redis_conn: redis.Redis, event_type: str, payload: Dict[str, Any], correlation_id: Optional[str] = None, practice_mode: bool = False):
    """Publishes an event to the Redis stream, including practice mode status."""
    event = {
        "eventId": str(uuid.uuid4()),
        "eventType": event_type,
        "sourceService": SERVICE_NAME,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "correlationId": correlation_id or str(uuid.uuid4()),
        "practiceMode": practice_mode, # Add practice mode flag to event
        "payload": payload
    }
    try:
        await redis_conn.xadd(EVENT_STREAM_KEY, {"event_data": json.dumps(event)})
        event_id_val = event["eventId"]
        print(f"Published event: {event_type} (ID: {event_id_val}, PracticeMode: {practice_mode})")
    except Exception as e:
        print(f"Error publishing event {event_type}: {e}")

# --- Placeholder Face Detection Logic ---
async def detect_faces_placeholder(media_ref: MediaReference, practice_mode: bool) -> FaceDetectionResult:
    """Placeholder function for face detection, aware of practice mode."""
    print(f"Performing placeholder face detection for media: {media_ref.media_id} (Practice Mode: {practice_mode})")
    await asyncio.sleep(random.uniform(0.5, 3)) # Simulate processing time

    detections = []
    num_faces = random.randint(0, 5) # Simulate detecting 0 to 5 faces

    img_width, img_height = 640, 480 # Default dimensions
    if media_ref.media_type == "image":
        try:
            # In practice mode, we might skip accessing the actual file
            if not practice_mode:
                with Image.open(media_ref.storage_path) as img:
                    img_width, img_height = img.size
            else:
                # Use default or slightly randomized dimensions for practice mode
                img_width = random.randint(600, 1200)
                img_height = random.randint(400, 900)
                print(f"Practice Mode: Using simulated dimensions {img_width}x{img_height}")
        except Exception as e:
            print(f"Warning: Could not open image {media_ref.storage_path} to get dimensions: {e}")

    for i in range(num_faces):
        # Generate random bounding box within image dimensions
        box_size = random.randint(min(img_width, img_height)//10, min(img_width, img_height)//3)
        left = random.randint(0, img_width - box_size)
        top = random.randint(0, img_height - box_size)
        right = left + box_size
        bottom = top + box_size

        # In practice mode, we could add synthetic attributes or modify confidence
        confidence = random.uniform(0.7, 0.99)
        if practice_mode:
            confidence = random.uniform(0.5, 0.8) # Lower confidence for synthetic data?

        detection = FaceDetection(
            detection_id=f"det-{media_ref.media_id}-{i}", # Add a unique ID per detection
            bounding_box=BoundingBox(top=top, right=right, bottom=bottom, left=left),
            confidence=confidence
            # Landmarks could be added here if simulated
        )
        detections.append(detection)

    result = FaceDetectionResult(
        media_id=media_ref.media_id,
        detections=detections
    )
    print(f"Placeholder detection complete for media: {media_ref.media_id}. Found {len(detections)} faces. (Practice Mode: {practice_mode})")
    return result

# --- Event Processing Logic ---
async def process_event(event_id: str, event_data: Dict[str, Any], redis_conn: redis.Redis):
    """Processes an incoming face detection request event."""
    event_type = event_data.get("eventType")
    payload = event_data.get("payload", {})
    correlation_id = event_data.get("correlationId", event_id)
    # Determine practice mode: from event or global setting
    event_practice_mode = event_data.get("practiceMode", False)
    current_practice_mode = PRACTICE_MODE or event_practice_mode

    if event_type != INPUT_EVENT_TYPE:
        print(f"Warning: Received unexpected event type {event_type}. Skipping.")
        return

    try:
        media_ref = MediaReference(**payload)
    except Exception as e:
        print(f"Error parsing MediaReference from event payload: {e}")
        return

    print(f"Processing face detection request for media: {media_ref.media_id} (Practice Mode: {current_practice_mode})")
    try:
        detection_result = await detect_faces_placeholder(media_ref, current_practice_mode)
        # Publish the result event, passing practice mode status
        await publish_event(
            redis_conn,
            event_type=OUTPUT_EVENT_TYPE,
            payload=detection_result.model_dump(mode="json"),
            correlation_id=correlation_id,
            practice_mode=current_practice_mode
        )
    except Exception as e:
        print(f"Error during face detection for {media_ref.media_id}: {e}")
        # Optionally publish an error event
        # await publish_event(redis_conn, "result.face_rec.error", {...}, correlation_id, practice_mode=current_practice_mode)

# --- Event Listener ---
async def event_listener(redis_conn: redis.Redis):
    """Listens to the Redis stream for new events and processes them."""
    try:
        await redis_conn.xgroup_create(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, id="0", mkstream=True)
        print(f"Consumer group 	{CONSUMER_GROUP_NAME}	 ensured on stream 	{EVENT_STREAM_KEY}	")
    except redis.ResponseError as e:
        if "BUSYGROUP Consumer Group name already exists" in str(e):
            print(f"Consumer group 	{CONSUMER_GROUP_NAME}	 already exists.")
        else:
            print(f"Error creating/checking consumer group: {e}")
            return

    last_processed_id = ">" # Start reading new messages for this consumer
    print("Starting event listener for face detection requests...")
    while True:
        try:
            response = await redis_conn.xreadgroup(
                CONSUMER_GROUP_NAME,
                CONSUMER_NAME,
                {EVENT_STREAM_KEY: last_processed_id},
                count=1,
                block=5000
            )

            if not response:
                continue

            for stream, messages in response:
                for message_id, message_data in messages:
                    print(f"Received message {message_id}")
                    try:
                        event_payload_json = message_data.get("event_data")
                        if event_payload_json:
                            event_payload_dict = json.loads(event_payload_json)
                            if event_payload_dict.get("eventType") == INPUT_EVENT_TYPE:
                                await process_event(message_id, event_payload_dict, redis_conn)
                            else:
                                event_type_value = event_payload_dict.get("eventType")
                                print(f"Skipping event of type: {event_type_value}")
                            await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)
                            print(f"Acknowledged message {message_id}")
                        else:
                            print(f"Warning: Message {message_id} missing 	 event_data	 field.")
                            await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)

                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON for message {message_id}: {e}")
                        await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)
                    except Exception as e:
                        print(f"Error processing message {message_id}: {e}")
                        await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)

        except redis.RedisError as e:
            print(f"Redis error during event listening: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Unexpected error in event listener: {e}. Restarting loop in 5s...")
            await asyncio.sleep(5)

# --- FastAPI App ---
app = FastAPI(
    title="EEM Face Detector Service",
    description="Detects faces in media based on events. Supports Practice Mode.",
    version="0.1.1"
)

@app.on_event("startup")
async def startup_event():
    """Start the event listener in the background."""
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    asyncio.create_task(event_listener(redis_conn))

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check(redis_conn: redis.Redis = Depends(get_redis_connection)) -> Dict[str, Any]:
    """Basic health check endpoint."""
    try:
        await redis_conn.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"
    return {"status": "ok", "redis_status": redis_status, "practice_mode": PRACTICE_MODE}

# --- Main execution (for running with uvicorn) ---
# Example: EEM_PRACTICE_MODE=true uvicorn services.face_rec.src.face_detector.main:app --reload --port 8021

