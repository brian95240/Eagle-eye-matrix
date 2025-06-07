import redis.asyncio as redis
import json
from fastapi import FastAPI, HTTPException, Depends, status
from typing import List, Dict, Any, Optional
import datetime

from .models import EntityState, ServiceStateEnum, TaskStateEnum, DataProcessingStateEnum

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

# --- Redis Connection ---
async def get_redis_connection() -> redis.Redis:
    """Dependency to get an async Redis connection."""
    connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    try:
        yield connection
    finally:
        await connection.close()

# --- FastAPI App ---
app = FastAPI(
    title="EEM State Management Service",
    description="Manages and tracks the state of entities within the Eagle Eye Matrix system.",
    version="0.1.0"
)

# --- Helper Functions ---
def _generate_redis_key(entity_type: str, entity_id: str) -> str:
    """Generates a consistent Redis key for an entity."""
    return f"eem_state:{entity_type}:{entity_id}"

# --- API Endpoints ---
@app.post("/state/{entity_type}/{entity_id}", status_code=status.HTTP_200_OK, response_model=EntityState)
async def update_entity_state(
    entity_type: str,
    entity_id: str,
    state_update: EntityState,
    redis_conn: redis.Redis = Depends(get_redis_connection)
) -> EntityState:
    """Update the state of a specific entity.

    - **entity_type**: The type of the entity (e.g., 'service', 'task', 'data').
    - **entity_id**: The unique identifier of the entity.
    - **state_update**: The new state information for the entity.
    """
    if state_update.entity_type != entity_type or state_update.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Entity type or ID in path does not match payload."
        )

    redis_key = _generate_redis_key(entity_type, entity_id)
    # Ensure last_updated is current
    state_update.last_updated = datetime.datetime.now(datetime.timezone.utc)

    try:
        # Store the entire state model as a JSON string
        await redis_conn.set(redis_key, state_update.model_dump_json())
        # Optionally, publish a state change event here (to be implemented later)
        # await publish_event("entity.state.changed", state_update.model_dump())
        return state_update
    except Exception as e:
        # Basic error handling, consider more specific logging/error types
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update state in Redis: {e}"
        )

@app.get("/state/{entity_type}/{entity_id}", response_model=EntityState)
async def get_entity_state(
    entity_type: str,
    entity_id: str,
    redis_conn: redis.Redis = Depends(get_redis_connection)
) -> EntityState:
    """Retrieve the current state of a specific entity.

    - **entity_type**: The type of the entity.
    - **entity_id**: The unique identifier of the entity.
    """
    redis_key = _generate_redis_key(entity_type, entity_id)
    state_json = await redis_conn.get(redis_key)

    if not state_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"State for entity {entity_type}:{entity_id} not found."
        )

    try:
        state_data = json.loads(state_json)
        return EntityState(**state_data)
    except json.JSONDecodeError:
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decode state data from Redis."
        )
    except Exception as e: # Catch potential Pydantic validation errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing stored state data: {e}"
        )

@app.get("/state/{entity_type}", response_model=List[EntityState])
async def query_entity_states(
    entity_type: str,
    state: Optional[str] = None, # Example filter: ?state=Running
    redis_conn: redis.Redis = Depends(get_redis_connection)
) -> List[EntityState]:
    """Query states for entities of a specific type, optionally filtering by state.

    - **entity_type**: The type of entities to query.
    - **state**: (Optional) Filter entities by a specific state.
    """
    pattern = f"eem_state:{entity_type}:*"
    keys = await redis_conn.keys(pattern)

    if not keys:
        return []

    states = []
    raw_states = await redis_conn.mget(keys)

    for state_json in raw_states:
        if state_json:
            try:
                state_data = json.loads(state_json)
                entity_state = EntityState(**state_data)
                # Apply state filter if provided
                if state is None or entity_state.state == state:
                    states.append(entity_state)
            except (json.JSONDecodeError, Exception) as e:
                # Log error but continue processing other keys
                print(f"Error processing state data for a key matching {pattern}: {e}")
                # Consider adding more robust error reporting

    return states

# --- Health Check ---
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
# Example: uvicorn services.core_framework.src.state_manager.main:app --reload --port 8001

