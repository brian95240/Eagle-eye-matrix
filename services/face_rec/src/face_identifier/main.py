import asyncio
import json
import uuid
from fastapi import FastAPI, HTTPException, Depends, status
import redis.asyncio as redis
from typing import Dict, Any, Optional, List
import datetime
import os
import random # For placeholder logic
import math # For Euclidean distance

# Assuming models are in a shared location or copied
# Adjust import path based on final structure
from ..models import FaceEncoding, KnownIdentity, IdentityMatch, FaceIdentificationResult

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
SERVICE_NAME = "face-identifier"
EVENT_STREAM_KEY = "eem_event_stream"
CONSUMER_GROUP_NAME = "face_identifier_group"
CONSUMER_NAME = "consumer_1"
INPUT_EVENT_TYPE = "result.face_rec.encoded"
OUTPUT_EVENT_TYPE = "result.face_rec.identified"
MATCH_THRESHOLD = 0.6 # Example threshold for Euclidean distance (lower is better)
PRACTICE_MATCH_THRESHOLD = 0.8 # Potentially looser threshold for practice mode

# --- Practice Mode Check ---
PRACTICE_MODE = os.environ.get("EEM_PRACTICE_MODE", "false").lower() == "true"
if PRACTICE_MODE:
    print("INFO: Face Identifier running in PRACTICE MODE")

# --- In-Memory Identity Database ---
# Simple dictionary to store known identities and their encodings
# Key: identity_id, Value: KnownIdentity (containing list of FaceEncoding)
identity_db: Dict[str, KnownIdentity] = {}
# Separate DB for practice mode to avoid polluting real data
practice_identity_db: Dict[str, KnownIdentity] = {}

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

def euclidean_distance(vec1: List[float], vec2: List[float]) -> float:
    """Calculates the Euclidean distance between two vectors."""
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must have the same dimension")
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(vec1, vec2)))

# --- Placeholder Face Identification Logic ---
async def identify_face_placeholder(incoming_encoding: FaceEncoding, practice_mode: bool) -> FaceIdentificationResult:
    """Placeholder function for identifying a face encoding, aware of practice mode."""
    print(f"Performing placeholder identification for encoding from detection: {incoming_encoding.detection_id} (Practice Mode: {practice_mode})")
    await asyncio.sleep(random.uniform(0.1, 0.5)) # Simulate comparison time

    potential_matches: List[IdentityMatch] = []
    current_db = practice_identity_db if practice_mode else identity_db
    current_threshold = PRACTICE_MATCH_THRESHOLD if practice_mode else MATCH_THRESHOLD

    if not current_db:
        print(f"Warning: Identity database ({'practice' if practice_mode else 'real'}) is empty. Cannot perform identification.")
    else:
        for identity_id, known_identity in current_db.items():
            best_match_score_for_identity = float("inf")
            for known_encoding in known_identity.associated_encodings:
                try:
                    # Compare only if dimensions match (basic check)
                    if len(incoming_encoding.encoding) == len(known_encoding.encoding):
                        distance = euclidean_distance(incoming_encoding.encoding, known_encoding.encoding)
                        best_match_score_for_identity = min(best_match_score_for_identity, distance)
                except ValueError as e:
                    print(f"Skipping comparison due to dimension mismatch or error: {e}")
                except Exception as e:
                    print(f"Error during comparison for identity {identity_id}: {e}")

            if best_match_score_for_identity != float("inf"):
                is_match = best_match_score_for_identity <= current_threshold
                potential_matches.append(
                    IdentityMatch(
                        known_identity_id=identity_id,
                        match_score=best_match_score_for_identity,
                        is_match=is_match
                    )
                )
                if is_match:
                    print(f"Potential match found: Detection {incoming_encoding.detection_id} matches Identity {identity_id} (Score: {best_match_score_for_identity:.4f}, Practice: {practice_mode})" )

    # Sort matches by score (lower is better for distance)
    potential_matches.sort(key=lambda x: x.match_score)

    result = FaceIdentificationResult(
        detection_id=incoming_encoding.detection_id,
        media_id=incoming_encoding.media_id,
        potential_matches=potential_matches
    )
    print(f"Placeholder identification complete for detection: {incoming_encoding.detection_id}. Found {len(potential_matches)} potential matches (Practice: {practice_mode}).")
    return result

# --- Event Processing Logic ---
async def process_event(event_id: str, event_data: Dict[str, Any], redis_conn: redis.Redis):
    """Processes an incoming face encoding result event."""
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
        face_encoding = FaceEncoding(**payload)
    except Exception as e:
        print(f"Error parsing FaceEncoding from event payload: {e}")
        return

    print(f"Processing face identification request for detection: {face_encoding.detection_id} (Practice Mode: {current_practice_mode})")
    try:
        identification_result = await identify_face_placeholder(face_encoding, current_practice_mode)
        # Publish the identification result event, passing practice mode status
        await publish_event(
            redis_conn,
            event_type=OUTPUT_EVENT_TYPE,
            payload=identification_result.model_dump(mode="json"),
            correlation_id=correlation_id,
            practice_mode=current_practice_mode
        )
    except Exception as e:
        print(f"Error during face identification for detection {face_encoding.detection_id}: {e}")
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
    print("Starting event listener for face identification requests...")
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
    title="EEM Face Identifier Service",
    description="Identifies faces by comparing embeddings against a known database. Supports Practice Mode.",
    version="0.1.1"
)

# --- API Endpoints for Managing Identities (Example) ---
# Modified to handle practice mode database
@app.post("/identities", response_model=KnownIdentity, status_code=status.HTTP_201_CREATED)
async def add_identity(identity: KnownIdentity, practice: bool = False) -> KnownIdentity:
    """Adds a new known identity to the appropriate database (real or practice)."""
    current_db = practice_identity_db if practice else identity_db
    if identity.identity_id in current_db:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Identity already exists in {'practice' if practice else 'real'} DB")
    identity.updated_at = datetime.datetime.now(datetime.timezone.utc)
    current_db[identity.identity_id] = identity
    print(f"Added identity: {identity.identity_id} ({identity.name}) to {'practice' if practice else 'real'} DB")
    return identity

@app.get("/identities/{identity_id}", response_model=KnownIdentity)
async def get_identity(identity_id: str, practice: bool = False) -> KnownIdentity:
    """Retrieves a known identity from the appropriate database."""
    current_db = practice_identity_db if practice else identity_db
    identity = current_db.get(identity_id)
    if not identity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Identity not found in {'practice' if practice else 'real'} DB")
    return identity

@app.post("/identities/{identity_id}/encodings", response_model=KnownIdentity)
async def add_encoding_to_identity(identity_id: str, encoding: FaceEncoding, practice: bool = False) -> KnownIdentity:
    """Adds a new face encoding to an existing identity in the appropriate database."""
    current_db = practice_identity_db if practice else identity_db
    identity = current_db.get(identity_id)
    if not identity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Identity not found in {'practice' if practice else 'real'} DB")
    # Simple check for duplicate encoding (based on detection_id)
    if any(e.detection_id == encoding.detection_id for e in identity.associated_encodings):
         print(f"Warning: Encoding for detection {encoding.detection_id} already exists for identity {identity_id}. Skipping add.")
         return identity

    identity.associated_encodings.append(encoding)
    identity.updated_at = datetime.datetime.now(datetime.timezone.utc)
    print(f"Added encoding from detection {encoding.detection_id} to identity {identity_id} in {'practice' if practice else 'real'} DB")
    return identity

# --- Pre-populate with some data (Optional Example) ---
@app.on_event("startup")
async def populate_initial_data():
    """Adds some example identities and encodings on startup to both DBs."""
    # Populate Real DB
    if not identity_db:
        print("Populating REAL identity database with example data...")
        id1 = str(uuid.uuid4())
        enc1a = [random.uniform(-1.0, 1.0) for _ in range(128)]
        enc1b = [random.uniform(-1.0, 1.0) for _ in range(128)]
        identity1 = KnownIdentity(identity_id=id1, name="Alice Real", associated_encodings=[
            FaceEncoding(detection_id=str(uuid.uuid4()), media_id="real_media_1", encoding=enc1a, model_name="placeholder_v1"),
            FaceEncoding(detection_id=str(uuid.uuid4()), media_id="real_media_2", encoding=enc1b, model_name="placeholder_v1")])
        identity_db[id1] = identity1
        id2 = str(uuid.uuid4())
        enc2a = [random.uniform(-1.0, 1.0) for _ in range(128)]
        identity2 = KnownIdentity(identity_id=id2, name="Bob Real", associated_encodings=[
            FaceEncoding(detection_id=str(uuid.uuid4()), media_id="real_media_3", encoding=enc2a, model_name="placeholder_v1")])
        identity_db[id2] = identity2
        print(f"Pre-populated REAL identity database with {len(identity_db)} identities.")

    # Populate Practice DB
    if not practice_identity_db:
        print("Populating PRACTICE identity database with example data...")
        pid1 = str(uuid.uuid4())
        penc1a = [random.uniform(-0.5, 0.5) for _ in range(128)] # Different range for practice
        penc1b = [random.uniform(-0.5, 0.5) for _ in range(128)]
        p_identity1 = KnownIdentity(identity_id=pid1, name="Charlie Practice", associated_encodings=[
            FaceEncoding(detection_id=str(uuid.uuid4()), media_id="practice_media_1", encoding=penc1a, model_name="placeholder_v1_practice"),
            FaceEncoding(detection_id=str(uuid.uuid4()), media_id="practice_media_2", encoding=penc1b, model_name="placeholder_v1_practice")])
        practice_identity_db[pid1] = p_identity1
        pid2 = str(uuid.uuid4())
        penc2a = [random.uniform(-0.5, 0.5) for _ in range(128)]
        p_identity2 = KnownIdentity(identity_id=pid2, name="Diana Practice", associated_encodings=[
            FaceEncoding(detection_id=str(uuid.uuid4()), media_id="practice_media_3", encoding=penc2a, model_name="placeholder_v1_practice")])
        practice_identity_db[pid2] = p_identity2
        print(f"Pre-populated PRACTICE identity database with {len(practice_identity_db)} identities.")

    # Start the event listener
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
    return {
        "status": "ok",
        "redis_status": redis_status,
        "practice_mode": PRACTICE_MODE,
        "real_identities_count": len(identity_db),
        "practice_identities_count": len(practice_identity_db)
    }

# --- Main execution (for running with uvicorn) ---
# Example: EEM_PRACTICE_MODE=true uvicorn services.face_rec.src.face_identifier.main:app --reload --port 8023

