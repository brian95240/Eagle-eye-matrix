import asyncio
import json
import uuid
from fastapi import FastAPI, HTTPException, Depends, status
import redis.asyncio as redis
from typing import Dict, Any, Optional, List
import datetime
import os
import random # For placeholder logic

# Assuming models are in a shared location or copied
# Adjust import path based on final structure
from ..models import CVAnalysisResult, DetectedObject, IngestedMedia

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
SERVICE_NAME = "geo-cv-analyzer"
EVENT_STREAM_KEY = "eem_event_stream"
CONSUMER_GROUP_NAME = "geo_cv_analyzer_group"
CONSUMER_NAME = "consumer_1"
INPUT_EVENT_TYPE = "analysis.geolocation.cv.requested" # Or listen directly to data.image.ingested if preferred
OUTPUT_EVENT_TYPE = "analysis.geolocation.cv.completed"

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

# --- Placeholder CV Analysis Logic ---
async def perform_cv_analysis(media_data: IngestedMedia) -> CVAnalysisResult:
    """Placeholder function for CV analysis.

    In a real implementation, this would load the image from media_data.local_path
    and use libraries like OpenCV, TensorFlow, PyTorch, etc., to detect objects.
    """
    print(f"Performing placeholder CV analysis for media: {media_data.media_id}")
    await asyncio.sleep(random.uniform(1, 5)) # Simulate processing time

    detected_objects = []
    # Simulate detecting some objects
    if random.random() > 0.3: # 70% chance of detecting something
        num_objects = random.randint(1, 5)
        possible_objects = ["building", "tree", "road_sign", "vehicle", "person", "landmark_feature"]
        for _ in range(num_objects):
            detected_objects.append(
                DetectedObject(
                    object_type=random.choice(possible_objects),
                    confidence=random.uniform(0.6, 0.99),
                    bounding_box=[random.uniform(0, 0.8), random.uniform(0, 0.8), random.uniform(0.2, 1), random.uniform(0.2, 1)] # Placeholder coords
                    # features = [...] # Placeholder for feature vectors
                )
            )

    result = CVAnalysisResult(
        media_id=media_data.media_id,
        detected_objects=detected_objects
    )
    print(f"Placeholder CV analysis complete for media: {media_data.media_id}. Found {len(detected_objects)} objects.")
    return result

# --- Event Processing Logic ---
async def process_event(event_id: str, event_data: Dict[str, Any], redis_conn: redis.Redis):
    """Processes an incoming analysis request event."""
    event_type = event_data.get("eventType")
    payload = event_data.get("payload", {})
    correlation_id = event_data.get("correlationId", event_id)

    if event_type != INPUT_EVENT_TYPE:
        print(f"Warning: Received unexpected event type {event_type}. Skipping.")
        return

    try:
        # Assuming the payload contains the IngestedMedia data
        # In a real scenario, might just contain media_id and need to fetch details
        media_info = IngestedMedia(**payload)
    except Exception as e:
        print(f"Error parsing IngestedMedia from event payload: {e}")
        return

    print(f"Processing CV analysis request for media: {media_info.media_id}")
    try:
        analysis_result = await perform_cv_analysis(media_info)
        # Publish the result event
        await publish_event(
            redis_conn,
            event_type=OUTPUT_EVENT_TYPE,
            payload=analysis_result.model_dump(mode="json"),
            correlation_id=correlation_id
        )
    except Exception as e:
        print(f"Error during CV analysis for {media_info.media_id}: {e}")
        # Optionally publish an error event
        # await publish_event(redis_conn, "analysis.geolocation.cv.error", {"media_id": media_info.media_id, "error": str(e)}, correlation_id)

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
    print("Starting event listener for CV analysis requests...")
    while True:
        try:
            response = await redis_conn.xreadgroup(
                CONSUMER_GROUP_NAME,
                CONSUMER_NAME,
                {EVENT_STREAM_KEY: last_processed_id},
                count=1, # Process one message at a time for simplicity
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
                            # Check if it's the type we care about before processing
                            if event_payload_dict.get("eventType") == INPUT_EVENT_TYPE:
                                await process_event(message_id, event_payload_dict, redis_conn)
                            else:
                                print(f"Skipping event of type: {event_payload_dict.get('eventType')}")
                            # Acknowledge the message regardless of type if successfully read
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
                        # Consider not acknowledging on processing errors for potential retry

        except redis.RedisError as e:
            print(f"Redis error during event listening: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Unexpected error in event listener: {e}. Restarting loop in 5s...")
            await asyncio.sleep(5)

# --- FastAPI App ---
app = FastAPI(
    title="EEM Geolocation CV Analyzer Service",
    description="Performs CV analysis on media for geolocation clues.",
    version="0.1.0"
)

@app.on_event("startup")
async def startup_event():
    """Start the event listener in the background."""
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    asyncio.create_task(event_listener(redis_conn))

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
# Example: uvicorn services.geo_pipeline.src.geo_cv_analyzer.main:app --reload --port 8011

