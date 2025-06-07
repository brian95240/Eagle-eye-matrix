import asyncio
import json
import uuid
from fastapi import FastAPI, HTTPException, Depends, status
import redis.asyncio as redis
from typing import Dict, Any, Optional, List
import datetime
from collections import defaultdict
import os

# Assuming models are in a shared location or copied
# Adjust import path based on final structure
from ..models import IdentityProfile, IdentityAttribute, SourceReference, FaceIdentificationResult, GeolocationEstimate, IdentityProfileUpdatePayload

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
SERVICE_NAME = "identity-aggregator"
EVENT_STREAM_KEY = "eem_event_stream"
CONSUMER_GROUP_NAME = "identity_aggregator_group"
CONSUMER_NAME = "consumer_1"
INPUT_EVENT_TYPES = [
    "result.face_rec.identified",
    "result.geo.estimated" # Add other relevant event types here
]
OUTPUT_EVENT_TYPE = "profile.identity.updated"

# --- Practice Mode Check ---
PRACTICE_MODE = os.environ.get("EEM_PRACTICE_MODE", "false").lower() == "true"
if PRACTICE_MODE:
    print("INFO: Identity Aggregator running in PRACTICE MODE (Global Setting)")

# --- In-Memory Profile Database ---
# Simple dictionary to store aggregated identity profiles
# Key: profile_id, Value: IdentityProfile
profile_db: Dict[str, IdentityProfile] = {}
# Separate DB for practice mode
practice_profile_db: Dict[str, IdentityProfile] = {}

# Helper mapping: known_identity_id -> profile_id (Separate for practice/real)
known_id_to_profile_id: Dict[str, str] = {}
practice_known_id_to_profile_id: Dict[str, str] = {}

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

# --- Aggregation Logic ---
def create_source_reference(event_data: Dict[str, Any]) -> SourceReference:
    """Creates a SourceReference from event metadata."""
    return SourceReference(
        event_id=event_data.get("eventId", "unknown"),
        service_name=event_data.get("sourceService", "unknown"),
        timestamp=datetime.datetime.fromisoformat(event_data.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())),
        correlation_id=event_data.get("correlationId")
    )

async def update_profile_with_face_id(result: FaceIdentificationResult, source: SourceReference, redis_conn: redis.Redis, practice_mode: bool):
    """Updates or creates profiles based on face identification results, aware of practice mode."""
    updated_profiles: Dict[str, List[IdentityAttribute]] = defaultdict(list)
    current_profile_db = practice_profile_db if practice_mode else profile_db
    current_known_id_map = practice_known_id_to_profile_id if practice_mode else known_id_to_profile_id
    db_label = "practice" if practice_mode else "real"

    # Find the best match (if any)
    best_match = None
    if result.potential_matches:
        # Ensure potential_matches is a list of dicts if coming from JSON
        matches = result.potential_matches
        if isinstance(matches, list) and all(isinstance(m, dict) for m in matches):
            matched = [m for m in matches if m.get("is_match")]
            if matched:
                best_match = min(matched, key=lambda x: x.get("match_score", float("inf")))
        else:
             print(f"Warning: potential_matches format unexpected: {type(matches)}. Expected list of dicts.")

    if best_match:
        known_identity_id = best_match.get("known_identity_id")
        match_score = best_match.get("match_score", float("inf"))
        confidence = 1.0 - match_score # Convert distance to confidence (simple example)

        if known_identity_id is None:
            print(f"Warning: Best match found but missing known_identity_id. Skipping profile update.")
            return

        # Check if this known_identity_id is already linked to a profile in the correct DB
        profile_id = current_known_id_map.get(known_identity_id)

        if profile_id and profile_id in current_profile_db:
            # Update existing profile
            profile = current_profile_db[profile_id]
            print(f"Updating existing {db_label} profile {profile_id} for known ID {known_identity_id}")
        else:
            # Create a new profile for this known_identity_id in the correct DB
            profile = IdentityProfile()
            profile_id = profile.profile_id
            current_profile_db[profile_id] = profile
            current_known_id_map[known_identity_id] = profile_id
            print(f"Created new {db_label} profile {profile_id} for known ID {known_identity_id}")

        # Add face identification attribute
        attribute = IdentityAttribute(
            attribute_type="face_identification",
            value={
                "detection_id": result.detection_id,
                "media_id": result.media_id,
                "matched_known_identity_id": known_identity_id,
                "match_score": match_score
            },
            confidence=confidence,
            source=source
        )
        profile.attributes.append(attribute)
        profile.updated_at = datetime.datetime.now(datetime.timezone.utc)
        updated_profiles[profile_id].append(attribute)

    else:
        # No confident match
        print(f"No confident match found for detection {result.detection_id} in {db_label} DB. Not creating/updating profile based on this event alone.")

    # Publish update events for affected profiles
    for pid, attrs in updated_profiles.items():
        update_payload = IdentityProfileUpdatePayload(
            profile_id=pid,
            updated_attributes=attrs,
            change_description=f"Added face identification result for detection {result.detection_id}"
        )
        # Propagate practice mode status in the update event
        await publish_event(redis_conn, OUTPUT_EVENT_TYPE, update_payload.model_dump(mode="json"), source.correlation_id, practice_mode=practice_mode)

async def update_profile_with_geo_estimate(result: GeolocationEstimate, source: SourceReference, redis_conn: redis.Redis, practice_mode: bool):
    """Updates profiles based on geolocation estimates (Placeholder logic), aware of practice mode."""
    # Placeholder: Link geo estimate to an identity profile based on media_id or other context.
    # This logic needs refinement based on how geo events relate to identities.
    db_label = "practice" if practice_mode else "real"
    print(f"Received geo estimate for media {result.media_id} ({db_label} mode). Aggregation logic TBD.")
    # Example: Find profile ID linked to media_id (requires maintaining such links)
    # profile_id = find_profile_by_media_id(result.media_id, practice_mode)
    # if profile_id:
    #     current_profile_db = practice_profile_db if practice_mode else profile_db
    #     profile = current_profile_db[profile_id]
    #     attribute = IdentityAttribute(
    #         attribute_type="estimated_location",
    #         value=result.model_dump(mode="json"),
    #         confidence=result.confidence,
    #         source=source
    #     )
    #     profile.attributes.append(attribute)
    #     profile.updated_at = datetime.datetime.now(datetime.timezone.utc)
    #     update_payload = IdentityProfileUpdatePayload(...)
    #     await publish_event(redis_conn, OUTPUT_EVENT_TYPE, update_payload.model_dump(mode="json"), source.correlation_id, practice_mode=practice_mode)

# --- Event Processing Logic ---
async def process_event(event_id: str, event_data: Dict[str, Any], redis_conn: redis.Redis):
    """Processes an incoming event for identity aggregation."""
    event_type = event_data.get("eventType")
    payload = event_data.get("payload", {})
    source = create_source_reference(event_data)
    # Determine practice mode: from event or global setting
    event_practice_mode = event_data.get("practiceMode", False)
    current_practice_mode = PRACTICE_MODE or event_practice_mode

    if event_type not in INPUT_EVENT_TYPES:
        print(f"Warning: Received unexpected event type {event_type}. Skipping.")
        return

    print(f"Processing event {event_type} (ID: {event_id}, PracticeMode: {current_practice_mode})")

    try:
        if event_type == "result.face_rec.identified":
            face_id_result = FaceIdentificationResult(**payload)
            await update_profile_with_face_id(face_id_result, source, redis_conn, current_practice_mode)
        elif event_type == "result.geo.estimated":
            geo_estimate_result = GeolocationEstimate(**payload)
            await update_profile_with_geo_estimate(geo_estimate_result, source, redis_conn, current_practice_mode)
        # Add handlers for other event types here
        else:
            print(f"No handler defined for event type: {event_type}")

    except Exception as e:
        print(f"Error processing event {event_id} ({event_type}): {e}")
        # Optionally publish an error event

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
    print("Starting event listener for identity aggregation...")
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
                            event_type_value = event_payload_dict.get("eventType")
                            if event_type_value in INPUT_EVENT_TYPES:
                                await process_event(message_id, event_payload_dict, redis_conn)
                            else:
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
    title="EEM Identity Aggregator Service",
    description="Aggregates information into identity profiles based on events. Supports Practice Mode.",
    version="0.1.1"
)

@app.on_event("startup")
async def startup_event():
    """Start the event listener in the background."""
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    asyncio.create_task(event_listener(redis_conn))

@app.get("/profiles", response_model=List[IdentityProfile])
async def get_all_profiles(practice: bool = False) -> List[IdentityProfile]:
    """Retrieves all aggregated identity profiles from the specified database."""
    current_profile_db = practice_profile_db if practice else profile_db
    return list(current_profile_db.values())

@app.get("/profiles/{profile_id}", response_model=IdentityProfile)
async def get_profile(profile_id: str, practice: bool = False) -> IdentityProfile:
    """Retrieves a specific identity profile from the specified database."""
    current_profile_db = practice_profile_db if practice else profile_db
    profile = current_profile_db.get(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Profile not found in {'practice' if practice else 'real'} DB")
    return profile

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check(redis_conn: redis.Redis = Depends(get_redis_connection)) -> Dict[str, Any]:
    """Basic health check endpoint."""
    try:
        await redis_conn.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"
    return {
        "status": "ok",
        "redis_status": redis_status,
        "practice_mode_global": PRACTICE_MODE,
        "real_profiles_count": len(profile_db),
        "practice_profiles_count": len(practice_profile_db)
    }

# --- Main execution (for running with uvicorn) ---
# Example: EEM_PRACTICE_MODE=true uvicorn services.identity_mgmt.src.identity_aggregator.main:app --reload --port 8030

