import asyncio
import json
import yaml
from fastapi import FastAPI, HTTPException, Depends, status
import redis.asyncio as redis
from typing import List, Dict, Any, Optional

from .models import TriggerRule, RuleCondition, RuleAction
# Assuming shared event schema definitions exist
# from shared.src.eem_event_schemas.events import BaseEvent # Adjust import path as needed

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
RULES_FILE_PATH = "/home/ubuntu/eagle_eye_matrix/services/core_framework/src/trigger_engine/rules.yaml" # Example path
EVENT_STREAM_KEY = "eem_event_stream" # Redis stream key for events
CONSUMER_GROUP_NAME = "trigger_engine_group"
CONSUMER_NAME = "consumer_1"

# --- Globals / State ---
rules_registry: Dict[str, TriggerRule] = {}

# --- Redis Connection ---
async def get_redis_connection() -> redis.Redis:
    """Dependency to get an async Redis connection."""
    connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    try:
        yield connection
    finally:
        await connection.close()

# --- Rule Loading ---
def load_rules_from_yaml(file_path: str) -> Dict[str, TriggerRule]:
    """Loads trigger rules from a YAML file."""
    loaded_rules = {}
    try:
        with open(file_path, 'r') as f:
            raw_rules = yaml.safe_load(f)
            if not isinstance(raw_rules, list):
                print(f"Error: Rules file {file_path} should contain a list of rules.")
                return {}
            for rule_data in raw_rules:
                try:
                    rule = TriggerRule(**rule_data)
                    if rule.enabled:
                        loaded_rules[rule.rule_id] = rule
                    else:
                        print(f"Info: Rule 	{rule.rule_id}	 is disabled, skipping.")
                except Exception as e:
                    print(f"Error parsing rule: {rule_data.get('rule_id', 'unknown')}. Error: {e}")
    except FileNotFoundError:
        print(f"Warning: Rules file not found at {file_path}. No rules loaded.")
    except yaml.YAMLError as e:
        print(f"Error loading YAML from {file_path}: {e}")
    print(f"Loaded {len(loaded_rules)} enabled rules.")
    return loaded_rules

# --- Event Processing Logic ---
async def evaluate_condition(condition: RuleCondition, event_payload: Dict[str, Any]) -> bool:
    """Evaluates a single rule condition against the event payload."""
    # Basic dot notation access for nested fields
    try:
        field_parts = condition.field.split(".")
        value = event_payload
        for part in field_parts:
            if isinstance(value, dict):
                value = value.get(part)
                if value is None and condition.operator not in ["exists", "not_exists"]:
                    return False # Field path doesn	 exist fully
            else:
                 # Cannot traverse further if not a dict
                 if condition.operator not in ["exists", "not_exists"]:
                     return False
                 value = None # Treat as non-existent for exists/not_exists

        # Evaluate based on operator
        op = condition.operator
        target_value = condition.value

        if op == "exists":
            return value is not None
        if op == "not_exists":
            return value is None
        if value is None: # Cannot evaluate other operators if value is None
            return False

        if op == "==":
            return value == target_value
        elif op == "!=":
            return value != target_value
        elif op == ">":
            return isinstance(value, (int, float)) and isinstance(target_value, (int, float)) and value > target_value
        elif op == "<":
            return isinstance(value, (int, float)) and isinstance(target_value, (int, float)) and value < target_value
        elif op == ">=":
            return isinstance(value, (int, float)) and isinstance(target_value, (int, float)) and value >= target_value
        elif op == "<=":
            return isinstance(value, (int, float)) and isinstance(target_value, (int, float)) and value <= target_value
        elif op == "in":
            return isinstance(target_value, list) and value in target_value
        elif op == "not_in":
            return isinstance(target_value, list) and value not in target_value
        else:
            print(f"Warning: Unsupported operator 	{op}	")
            return False

    except Exception as e:
        print(f"Error evaluating condition {condition}: {e}")
        return False

async def execute_action(action: RuleAction, original_event: Dict[str, Any], redis_conn: redis.Redis):
    """Executes a rule action."""
    if action.action_type == "publish_event" and action.target_event_type:
        new_event_payload = original_event.get("payload", {}).copy()
        if action.payload_override:
            new_event_payload.update(action.payload_override)

        # Construct the new event structure (assuming a standard format)
        new_event = {
            # "eventId": generate_uuid(), # Need a UUID generator
            "eventType": action.target_event_type,
            "sourceService": "trigger-engine",
            # "timestamp": datetime.utcnow().isoformat(),
            "correlationId": original_event.get("correlationId", original_event.get("eventId")), # Propagate correlation ID
            "payload": new_event_payload
        }
        try:
            await redis_conn.xadd(EVENT_STREAM_KEY, {"event_data": json.dumps(new_event)})
            print(f"Action executed: Published event 	{action.target_event_type}	")
        except Exception as e:
            print(f"Error publishing event {action.target_event_type}: {e}")
    else:
        print(f"Warning: Unsupported action type 	{action.action_type}	 or missing target_event_type")

async def process_event(event_id: str, event_data: Dict[str, Any], redis_conn: redis.Redis):
    """Processes a single event against loaded rules."""
    event_type = event_data.get("eventType")
    event_payload = event_data.get("payload", {})
    if not event_type:
        print(f"Warning: Event {event_id} missing eventType.")
        return

    print(f"Processing event {event_id} of type {event_type}")

    for rule_id, rule in rules_registry.items():
        if event_type in rule.trigger_event_types:
            print(f"Rule {rule_id} triggered by event type {event_type}. Evaluating conditions...")
            all_conditions_met = True
            for condition in rule.conditions:
                condition_met = await evaluate_condition(condition, event_payload)
                if not condition_met:
                    all_conditions_met = False
                    print(f"Condition not met for rule {rule_id}: {condition}")
                    break # No need to check further conditions for this rule

            if all_conditions_met:
                print(f"All conditions met for rule {rule_id}. Executing actions...")
                for action in rule.actions:
                    await execute_action(action, event_data, redis_conn)
            else:
                print(f"Conditions not met for rule {rule_id}.")

async def event_listener(redis_conn: redis.Redis):
    """Listens to the Redis stream for new events and processes them."""
    try:
        # Ensure the consumer group exists
        await redis_conn.xgroup_create(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, id=	0	, mkstream=True)
        print(f"Consumer group 	{CONSUMER_GROUP_NAME}	 ensured on stream 	{EVENT_STREAM_KEY}	")
    except redis.ResponseError as e:
        if "BUSYGROUP Consumer Group name already exists" in str(e):
            print(f"Consumer group 	{CONSUMER_GROUP_NAME}	 already exists.")
        else:
            print(f"Error creating/checking consumer group: {e}")
            return # Cannot proceed without consumer group

    last_processed_id = ">	" # Start reading new messages
    print("Starting event listener...")
    while True:
        try:
            # Read from the stream using the consumer group
            response = await redis_conn.xreadgroup(
                CONSUMER_GROUP_NAME,
                CONSUMER_NAME,
                {EVENT_STREAM_KEY: last_processed_id},
                count=10, # Process up to 10 messages at a time
                block=5000 # Block for 5 seconds waiting for messages
            )

            if not response:
                # print("No new messages, continuing...")
                continue

            for stream, messages in response:
                for message_id, message_data in messages:
                    print(f"Received message {message_id}")
                    try:
                        event_payload_json = message_data.get("event_data")
                        if event_payload_json:
                            event_payload_dict = json.loads(event_payload_json)
                            await process_event(message_id, event_payload_dict, redis_conn)
                            # Acknowledge the message after successful processing
                            await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)
                            print(f"Acknowledged message {message_id}")
                        else:
                            print(f"Warning: Message {message_id} missing 	 event_data	 field.")
                            # Acknowledge potentially malformed message to avoid reprocessing loop
                            await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)

                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON for message {message_id}: {e}")
                        # Acknowledge malformed message
                        await redis_conn.xack(EVENT_STREAM_KEY, CONSUMER_GROUP_NAME, message_id)
                    except Exception as e:
                        print(f"Error processing message {message_id}: {e}")
                        # Do not acknowledge, might retry later or need manual intervention

        except redis.RedisError as e:
            print(f"Redis error during event listening: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Unexpected error in event listener: {e}. Restarting loop in 5s...")
            await asyncio.sleep(5)

# --- FastAPI App ---
app = FastAPI(
    title="EEM Trigger Evaluation Engine",
    description="Listens to events and triggers actions based on configurable rules.",
    version="0.1.0"
)

@app.on_event("startup")
async def startup_event():
    """Load rules and start the event listener on startup."""
    global rules_registry
    rules_registry = load_rules_from_yaml(RULES_FILE_PATH)
    # Start the event listener in the background
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    asyncio.create_task(event_listener(redis_conn))

@app.get("/rules", response_model=List[TriggerRule])
async def get_loaded_rules() -> List[TriggerRule]:
    """Returns the list of currently loaded and enabled rules."""
    return list(rules_registry.values())

@app.post("/rules/reload", status_code=status.HTTP_200_OK)
async def reload_rules() -> Dict[str, Any]:
    """Reloads rules from the configuration file."""
    global rules_registry
    new_rules = load_rules_from_yaml(RULES_FILE_PATH)
    rules_registry = new_rules
    return {"message": f"Reloaded {len(rules_registry)} enabled rules."}

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
# Example: uvicorn services.core_framework.src.trigger_engine.main:app --reload --port 8002

