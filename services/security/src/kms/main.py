import uuid
import secrets
import datetime
from fastapi import FastAPI, HTTPException, Depends, status
from typing import Dict, Optional, List

# Assuming models are in the same directory or adjust import path
from .models import (
    ApiKey, CreateKeyRequest, CreateKeyResponse,
    ValidateKeyRequest, ValidateKeyResponse, KeyInfoResponse
)

# --- In-Memory Key Store (Placeholder) ---
# In a real system, use a secure database or dedicated secrets manager
api_key_store: Dict[str, ApiKey] = {}

# --- Helper Functions ---
def generate_api_key(length: int = 32) -> str:
    """Generates a secure random API key."""
    # Example prefix: eemk_ (Eagle Eye Matrix Key)
    return f"eemk_{secrets.token_urlsafe(length)}"

# --- FastAPI App ---
app = FastAPI(
    title="EEM Key Management Service (KMS)",
    description="Manages API keys for Eagle Eye Matrix services (Placeholder Implementation).",
    version="0.1.0"
)

# --- API Endpoints ---
@app.post("/keys", response_model=CreateKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_key(request: CreateKeyRequest) -> CreateKeyResponse:
    """Creates a new API key for a specified service."""
    key_id = str(uuid.uuid4())
    key_value = generate_api_key()
    created_at = datetime.datetime.now(datetime.timezone.utc)
    expires_at = None
    if request.expires_in_days:
        expires_at = created_at + datetime.timedelta(days=request.expires_in_days)

    new_key = ApiKey(
        key_id=key_id,
        key_value=key_value,
        service_name=request.service_name,
        created_at=created_at,
        expires_at=expires_at,
        is_active=True,
        metadata=request.metadata
    )
    api_key_store[key_id] = new_key
    print(f"Created key {key_id} for service {request.service_name}")

    # Return the full key value only upon creation
    return CreateKeyResponse(
        key_id=new_key.key_id,
        key_value=new_key.key_value,
        service_name=new_key.service_name,
        created_at=new_key.created_at,
        expires_at=new_key.expires_at
    )

@app.post("/keys/validate", response_model=ValidateKeyResponse)
async def validate_key(request: ValidateKeyRequest) -> ValidateKeyResponse:
    """Validates an API key."""
    now = datetime.datetime.now(datetime.timezone.utc)
    for key_id, stored_key in api_key_store.items():
        if stored_key.key_value == request.key_value:
            if not stored_key.is_active:
                return ValidateKeyResponse(is_valid=False, reason="Key is inactive")
            if stored_key.expires_at and stored_key.expires_at < now:
                # Optionally deactivate expired keys here
                stored_key.is_active = False
                print(f"Key {key_id} expired and deactivated.")
                return ValidateKeyResponse(is_valid=False, reason="Key has expired")

            # Update last used time (optional)
            stored_key.last_used_at = now
            print(f"Validated key {key_id} for service {stored_key.service_name}")
            return ValidateKeyResponse(
                is_valid=True,
                key_id=stored_key.key_id,
                service_name=stored_key.service_name
            )

    return ValidateKeyResponse(is_valid=False, reason="Invalid key")

@app.get("/keys/{key_id}", response_model=KeyInfoResponse)
async def get_key_info(key_id: str) -> KeyInfoResponse:
    """Retrieves information about a specific key (key value is masked)."""
    stored_key = api_key_store.get(key_id)
    if not stored_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")

    # Return masked info
    return KeyInfoResponse(
        key_id=stored_key.key_id,
        service_name=stored_key.service_name,
        created_at=stored_key.created_at,
        expires_at=stored_key.expires_at,
        is_active=stored_key.is_active,
        last_used_at=stored_key.last_used_at,
        metadata=stored_key.metadata
    )

@app.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(key_id: str):
    """Revokes (deactivates) an API key."""
    stored_key = api_key_store.get(key_id)
    if not stored_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")

    if not stored_key.is_active:
        # Already inactive, treat as success (idempotent)
        return

    stored_key.is_active = False
    print(f"Revoked key {key_id} for service {stored_key.service_name}")
    return

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok"}

# --- Main execution (for running with uvicorn) ---
# Example: uvicorn services.security.src.kms.main:app --reload --port 8050

