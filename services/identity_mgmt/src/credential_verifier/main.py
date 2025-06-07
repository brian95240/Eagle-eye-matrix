import asyncio
import json
import uuid
from fastapi import FastAPI, HTTPException, Depends, status
import redis.asyncio as redis
from typing import Dict, Any, Optional, List
import datetime
import random
import httpx

# Assuming models are in a shared location or copied
# Adjust import path based on final structure
from ..models import VerificationRequest, VerificationResult, SourceReference

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
SERVICE_NAME = "credential-verifier"
EVENT_STREAM_KEY = "eem_event_stream"
CONSUMER_GROUP_NAME = "credential_verifier_group"
CONSUMER_NAME = "consumer_1"
INPUT_EVENT_TYPE = "request.identity.verification" # Event type to trigger verification
OUTPUT_EVENT_TYPE = "result.identity.verification"

ADAPTER_URLS = {
    "vital_records": "http://localhost:8040/query",
    "voting_records": "http://localhost:8041/query",
    "tax_records": "http://localhost:8042/query",
    "property_records": "http://localhost:8043/query",
}

# --- Redis Connection ---
async def get_redis_connection() -> redis.Redis:
    """Dependency to get an async Redis connection."""
    connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    try:
        yield connection
    finally:
        await connection.close()

# --- HTTP Client ---
# Using a single client instance can be more efficient
http_client = httpx.AsyncClient(timeout=10.0) # Adjust timeout as needed

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
        event_id_val = event["eventId"]
        print(f"Published event: {event_type} (ID: {event_id_val})")
    except Exception as e:
        print(f"Error publishing event {event_type}: {e}")

# --- Verification Logic ---
async def verify_credential(request: VerificationRequest) -> VerificationResult:
    """Verifies a credential by calling the appropriate adapter or using placeholder logic."""
    print(f"Performing verification for attribute {request.attribute_id} (Profile: {request.profile_id}) using method: {request.verification_method}")

    adapter_url = ADAPTER_URLS.get(request.verification_method)
    is_verified = False
    confidence = 0.0
    details = f"Verification method 	{request.verification_method}	 not supported or adapter unavailable."
    source_references = []

    if adapter_url:
        # Construct query payload based on request attributes
        # This is a simplified mapping; a real system would need more robust logic
        query_payload = {}
        if request.attribute_values:
            if request.verification_method == "vital_records":
                query_payload = {
                    "first_name": request.attribute_values.get("firstName"),
                    "last_name": request.attribute_values.get("lastName"),
                    "date_of_birth": request.attribute_values.get("dateOfBirth")
                }
            elif request.verification_method == "voting_records":
                query_payload = {
                    "first_name": request.attribute_values.get("firstName"),
                    "last_name": request.attribute_values.get("lastName"),
                    "date_of_birth": request.attribute_values.get("dateOfBirth"),
                    "address_street": request.attribute_values.get("addressStreet"),
                    "address_city": request.attribute_values.get("addressCity"),
                    "address_zip": request.attribute_values.get("addressZip")
                }
            elif request.verification_method == "tax_records":
                 query_payload = {
                    "first_name": request.attribute_values.get("firstName"),
                    "last_name": request.attribute_values.get("lastName"),
                    "date_of_birth": request.attribute_values.get("dateOfBirth"),
                    "ssn_last4": request.attribute_values.get("ssnLast4"),
                    "address_street": request.attribute_values.get("addressStreet")
                }
            elif request.verification_method == "property_records":
                 query_payload = {
                    "owner_first_name": request.attribute_values.get("firstName"),
                    "owner_last_name": request.attribute_values.get("lastName"),
                    "address_street": request.attribute_values.get("addressStreet"),
                    "address_city": request.attribute_values.get("addressCity"),
                    "address_zip": request.attribute_values.get("addressZip"),
                    "parcel_id": request.attribute_values.get("parcelId")
                }

        # Remove None values from payload
        query_payload = {k: v for k, v in query_payload.items() if v is not None}

        if not query_payload.get("last_name") and not query_payload.get("address_street") and not query_payload.get("parcel_id"):
             details = f"Insufficient information provided for {request.verification_method} query."
        else:
            try:
                print(f"Calling adapter: {adapter_url} with payload: {query_payload}")
                response = await http_client.post(adapter_url, json=query_payload)
                response.raise_for_status() # Raise exception for 4xx/5xx errors
                adapter_result = response.json()
                print(f"Adapter response: {adapter_result}")

                # Placeholder logic to determine verification based on results
                if adapter_result.get("results"):
                    is_verified = True # Simple check: if any results found, consider verified
                    confidence = 0.85 # Assign arbitrary confidence for placeholder
                    details = f"Found {len(adapter_result['results'])} potential match(es) via {request.verification_method} adapter."
                    # Add source reference
                    source_references.append(SourceReference(
                        source_name=adapter_result.get("source", request.verification_method),
                        reference_details=json.dumps(adapter_result.get("results")) # Store raw results for now
                    ))
                else:
                    is_verified = False
                    confidence = 0.5 # Confidence slightly higher if adapter responded but found nothing
                    details = f"No matches found via {request.verification_method} adapter."

            except httpx.RequestError as e:
                print(f"Error calling adapter {adapter_url}: {e}")
                details = f"Error connecting to {request.verification_method} adapter."
                confidence = 0.1
            except Exception as e:
                print(f"Error processing adapter response from {adapter_url}: {e}")
                details = f"Error processing response from {request.verification_method} adapter."
                confidence = 0.1
    else:
        # Fallback to original placeholder logic for non-adapter methods
        print(f"Using placeholder logic for method: {request.verification_method}")
        await asyncio.sleep(random.uniform(0.5, 2.0))
        is_verified = random.choice([True, False])
        confidence = random.uniform(0.6, 0.9) if is_verified else random.uniform(0.1, 0.4)
        details = f"Simulated placeholder verification via {request.verification_method}. Outcome: {'Verified' if is_verified else 'Not Verified'}."

    result = VerificationResult(
        request_id=request.attribute_id,
        profile_id=request.profile_id,
        attribute_id=request.attribute_id,
        is_verified=is_verified,
        confidence=confidence,
        verification_details=details,
        source_references=source_references
    )
    print(f"Verification complete for attribute {request.attribute_id}. Verified: {is_verified}, Confidence: {confidence:.2f}")
    return result

# --- Event Processing Logic ---
async def process_event(event_id: str, event_data: Dict[str, Any], redis_conn: redis.Redis):
    """Processes an incoming verification request event."""
    event_type = event_data.get("eventType")
    payload = event_data.get("payload", {})
    correlation_id = event_data.get("correlationId", event_id)

    if event_type != INPUT_EVENT_TYPE:
        # print(f"Warning: Received unexpected event type {event_type}. Skipping.")
        return

    try:
        verification_request = VerificationRequest(**payload)
    except Exception as e:
        print(f"Error parsing VerificationRequest from event payload: {e}")
        return

    print(f"Processing verification request for attribute: {verification_request.attribute_id}")
    try:
        # Use the updated verification logic
        verification_result = await verify_credential(verification_request)
        # Publish the verification result event
        await publish_event(
            redis_conn,
            event_type=OUTPUT_EVENT_TYPE,
            payload=verification_result.model_dump(mode="json"),
            correlation_id=correlation_id
        )
    except Exception as e:
        print(f"Error during credential verification for attribute {verification_request.attribute_id}: {e}")
        # Optionally publish an error event
        # await publish_event(redis_conn, "result.identity.verification.error", {...}, correlation_id)

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
    print("Starting event listener for credential verification requests...")
    while True:
        try:
            response = await redis_conn.xreadgroup(
                CONSUMER_GROUP_NAME,
                CONSUMER_NAME,
                {EVENT_STREAM_KEY: last_processed_id},
                count=1,
                block=5000 # Block for 5 seconds
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
                            if event_type_value == INPUT_EVENT_TYPE:
                                await process_event(message_id, event_payload_dict, redis_conn)
                            else:
                                # Silently skip non-relevant events
                                # print(f"Skipping event of type: {event_type_value}")
                                pass
                            await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)
                            # print(f"Acknowledged message {message_id}")
                        else:
                            print(f"Warning: Message {message_id} missing 	 event_data	 field.")
                            await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)

                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON for message {message_id}: {e}")
                        await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)
                    except Exception as e:
                        print(f"Error processing message {message_id}: {e}")
                        # Acknowledge even if processing fails to avoid reprocessing loop in this basic setup
                        await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)

        except redis.RedisError as e:
            print(f"Redis error during event listening: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Unexpected error in event listener: {e}. Restarting loop in 5s...")
            await asyncio.sleep(5)

# --- FastAPI App ---
app = FastAPI(
    title="EEM Credential Verifier Service",
    description="Verifies identity attributes by calling adapters or using placeholders.",
    version="0.2.0" # Version updated
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
    # Check adapter health (optional, could add complexity)
    # vital_status = "unknown"
    # try:
    #     async with httpx.AsyncClient(timeout=2.0) as client:
    #         resp = await client.get(ADAPTER_URLS["vital_records"].replace("/query", "/health"))
    #         vital_status = "ok" if resp.status_code == 200 else "error"
    # except Exception:
    #     vital_status = "error"

    return {"status": "ok", "redis_status": redis_status}

# --- Main execution (for running with uvicorn) ---
# Example: uvicorn services.identity_mgmt.src.credential_verifier.main:app --reload --port 8031

