import asyncio
import json
import uuid
from fastapi import FastAPI, HTTPException, Depends, status
import redis.asyncio as redis
from typing import Dict, Any, Optional, List
import datetime
import os
import random # For placeholder logic
import httpx # For calling other services (like geo_knowledge)

# Assuming models are in a shared location or copied
# Adjust import path based on final structure
from ..models import GeolocationEstimate, CVAnalysisResult, GeoKnowledgeEntry

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
SERVICE_NAME = "geo-estimator"
EVENT_STREAM_KEY = "eem_event_stream"
CONSUMER_GROUP_NAME = "geo_estimator_group"
CONSUMER_NAME = "consumer_1"
INPUT_EVENT_TYPE = "analysis.geolocation.cv.completed"
OUTPUT_EVENT_TYPE = "result.geolocation.estimated"
GEO_KNOWLEDGE_SERVICE_URL = "http://localhost:8012" # URL of the knowledge base service

# --- Redis Connection ---
async def get_redis_connection() -> redis.Redis:
    """Dependency to get an async Redis connection."""
    connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    try:
        yield connection
    finally:
        await connection.close()

# --- HTTP Client for Service Calls ---
# Use a single client instance for better performance
http_client = httpx.AsyncClient()

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

# --- Placeholder Estimation Logic ---
async def estimate_geolocation(cv_result: CVAnalysisResult) -> GeolocationEstimate:
    """Placeholder function for geolocation estimation.

    In a real implementation, this would:
    1. Query the geo_knowledge service based on cv_result.detected_objects.
    2. Use geometric reasoning, probability models, etc., to fuse evidence.
    3. Potentially use metadata from the original IngestedMedia (if available).
    """
    print(f"Performing placeholder geolocation estimation for media: {cv_result.media_id}")
    await asyncio.sleep(random.uniform(0.5, 2)) # Simulate processing time

    confidence = 0.0
    lat, lon = 0.0, 0.0
    method = "PLACEHOLDER"
    supporting_evidence = []

    # Simulate querying knowledge base for detected landmarks
    landmark_found = None
    for obj in cv_result.detected_objects:
        if "landmark" in obj.object_type and obj.confidence > 0.7:
            try:
                # Simulate API call to geo_knowledge service
                # response = await http_client.get(f"{GEO_KNOWLEDGE_SERVICE_URL}/knowledge", params={"name": obj.object_type, "entry_type": "landmark"})
                # response.raise_for_status()
                # potential_matches = response.json()
                # if potential_matches:
                #     landmark_found = potential_matches[0] # Take the first match for simplicity
                #     break

                # --- Placeholder Simulation --- 
                if obj.object_type == "landmark_feature" and random.random() > 0.5:
                     # Simulate finding Eiffel Tower or Statue of Liberty based on example data
                     if random.random() > 0.5:
                         landmark_found = {"entry_id": "landmark_001", "name": "Eiffel Tower", "latitude": 48.8584, "longitude": 2.2945}
                     else:
                         landmark_found = {"entry_id": "landmark_002", "name": "Statue of Liberty", "latitude": 40.6892, "longitude": -74.0445}
                     break
                # --- End Placeholder Simulation --- 

            except Exception as e:
                print(f"Error querying knowledge base (simulated): {e}")

    if landmark_found:
        lat = landmark_found["latitude"]
        lon = landmark_found["longitude"]
        confidence = random.uniform(0.6, 0.9) # Higher confidence if landmark found
        method = "CV_LANDMARK_MATCH (SIMULATED)"
        supporting_evidence.append(f"Matched landmark: {landmark_found['name']}")
    elif cv_result.detected_objects: # Some objects detected, but no landmark match
        lat = random.uniform(-90, 90)
        lon = random.uniform(-180, 180)
        confidence = random.uniform(0.1, 0.4)
        method = "CV_OBJECT_CONTEXT (SIMULATED)"
        supporting_evidence = [f"Detected {len(cv_result.detected_objects)} objects"] 
    else: # No objects detected
        lat = random.uniform(-90, 90)
        lon = random.uniform(-180, 180)
        confidence = random.uniform(0.01, 0.1)
        method = "DEFAULT_GUESS (SIMULATED)"
        supporting_evidence = ["No significant CV features detected"]


    estimate = GeolocationEstimate(
        media_id=cv_result.media_id,
        latitude=lat,
        longitude=lon,
        confidence=confidence,
        radius_meters=random.uniform(50, 5000) / confidence if confidence > 0 else 50000, # Example radius based on confidence
        method=method,
        supporting_evidence=supporting_evidence
    )
    print(f"Placeholder estimation complete for media: {cv_result.media_id}. Estimate: Lat={lat:.4f}, Lon={lon:.4f}, Conf={confidence:.2f}")
    return estimate

# --- Event Processing Logic ---
async def process_event(event_id: str, event_data: Dict[str, Any], redis_conn: redis.Redis):
    """Processes an incoming CV analysis result event."""
    event_type = event_data.get("eventType")
    payload = event_data.get("payload", {})
    correlation_id = event_data.get("correlationId", event_id)

    if event_type != INPUT_EVENT_TYPE:
        print(f"Warning: Received unexpected event type {event_type}. Skipping.")
        return

    try:
        cv_result = CVAnalysisResult(**payload)
    except Exception as e:
        print(f"Error parsing CVAnalysisResult from event payload: {e}")
        return

    print(f"Processing geolocation estimation request for media: {cv_result.media_id}")
    try:
        geo_estimate = await estimate_geolocation(cv_result)
        # Publish the result event
        await publish_event(
            redis_conn,
            event_type=OUTPUT_EVENT_TYPE,
            payload=geo_estimate.model_dump(mode="json"),
            correlation_id=correlation_id
        )
    except Exception as e:
        print(f"Error during geolocation estimation for {cv_result.media_id}: {e}")
        # Optionally publish an error event
        # await publish_event(redis_conn, "result.geolocation.error", {"media_id": cv_result.media_id, "error": str(e)}, correlation_id)

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
    print("Starting event listener for geolocation estimation requests...")
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

        except redis.RedisError as e:
            print(f"Redis error during event listening: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Unexpected error in event listener: {e}. Restarting loop in 5s...")
            await asyncio.sleep(5)

# --- FastAPI App ---
app = FastAPI(
    title="EEM Geolocation Estimator Service",
    description="Estimates geolocation based on CV analysis and knowledge base lookups.",
    version="0.1.0"
)

@app.on_event("startup")
async def startup_event():
    """Start the event listener in the background."""
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    asyncio.create_task(event_listener(redis_conn))

@app.on_event("shutdown")
async def shutdown_event():
    """Close the HTTP client on shutdown."""
    await http_client.aclose()

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check(redis_conn: redis.Redis = Depends(get_redis_connection)) -> Dict[str, str]:
    """Basic health check endpoint."""
    try:
        await redis_conn.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"
    # Could add a check to the knowledge base service here too
    return {"status": "ok", "redis_status": redis_status}

# --- Main execution (for running with uvicorn) ---
# Example: uvicorn services.geo_pipeline.src.geo_estimator.main:app --reload --port 8013

