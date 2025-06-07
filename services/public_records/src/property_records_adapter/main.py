from fastapi import FastAPI, HTTPException, Depends, Header, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import datetime
import httpx
import os

# --- Configuration ---
SERVICE_NAME = "property_records_adapter"
KMS_URL = os.getenv("KMS_URL", "http://localhost:8050") # Get KMS URL from env or default

app = FastAPI(
    title="EEM Property Records Adapter (Placeholder)",
    description="Simulates access to property ownership records. Requires API Key.",
    version="0.1.1" # Incremented version
)

# --- Placeholder Data ---
placeholder_data = {
    "123_main_st_anytown": {
        "address": "123 Main St, Anytown, USA, 12345",
        "parcel_id": "ANY-001-002-003",
        "owner_names": ["John Michael Doe", "Alice Grace Williams"],
        "purchase_date": "2018-03-15",
        "purchase_price": 350000,
        "assessed_value": 380000,
        "property_type": "Single Family Residential"
    },
    "456_oak_ave_otherville": {
        "address": "456 Oak Ave, Otherville, USA, 67890",
        "parcel_id": "OTH-004-005-006",
        "owner_names": ["Jane Anne Smith", "Richard Doe"], # Richard Doe might be linked via marriage
        "purchase_date": "2005-09-01",
        "purchase_price": 250000,
        "assessed_value": 310000,
        "property_type": "Single Family Residential"
    },
     "789_pine_ln_anytown": {
        "address": "789 Pine Ln, Anytown, USA, 12346",
        "parcel_id": "ANY-007-008-009",
        "owner_names": ["John Michael Doe"], # Example: Second property
        "purchase_date": "2022-11-20",
        "purchase_price": 150000,
        "assessed_value": 165000,
        "property_type": "Condominium"
    }
}

# --- Request/Response Models ---
class PropertyQuery(BaseModel):
    owner_first_name: Optional[str] = Field(None, description="Owner's first name")
    owner_last_name: Optional[str] = Field(None, description="Owner's last name")
    address_street: Optional[str] = Field(None, description="Property street address")
    address_city: Optional[str] = Field(None, description="Property city")
    address_zip: Optional[str] = Field(None, description="Property ZIP code")
    parcel_id: Optional[str] = Field(None, description="Property Parcel ID")

class PropertyResult(BaseModel):
    query_details: PropertyQuery
    results: List[Dict[str, Any]] = Field(..., description="List of matching property records found")
    source: str = "Property Records Adapter (Placeholder)"
    timestamp: datetime.datetime

# --- API Key Verification Dependency (Adapted from other Adapters) ---
async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Dependency to verify the API key against the KMS."""
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key required")

    try:
        async with httpx.AsyncClient() as client:
            # Using /keys/validate endpoint as seen in vital_records_adapter
            response = await client.post(f"{KMS_URL}/keys/validate", json={"key_value": x_api_key})
            response.raise_for_status()
            validation_result = response.json()

            if not validation_result.get("is_valid") or validation_result.get("service_name") != SERVICE_NAME:
                print(f"Invalid API Key received: {x_api_key[:8]}... Reason: {validation_result.get('reason')}")
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Invalid or unauthorized API Key: {validation_result.get('reason', 'Validation failed')}")
            print(f"Valid API Key received: {validation_result.get('key_id')}")
            return validation_result # Contains is_valid, key_id, service_name
    except httpx.RequestError as e:
        print(f"Error connecting to KMS: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not connect to Key Management Service")
    except Exception as e:
        print(f"Unexpected error during API key verification: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error during API key verification")

# --- API Endpoint ---
@app.post("/query", response_model=PropertyResult)
async def query_property_records(query: PropertyQuery, api_key_data: Dict[str, Any] = Depends(verify_api_key)) -> PropertyResult:
    """Simulates querying property records based on provided details. Requires valid API Key."""
    print(f"Received property records query: {query.model_dump()} (Key ID: {api_key_data.get('key_id')})")
    matching_results = []

    # Simple placeholder matching logic
    for key, data in placeholder_data.items():
        match = False
        # Match by Parcel ID (if provided, highest priority)
        if query.parcel_id and data.get("parcel_id") == query.parcel_id:
            match = True
        # Match by Address (if provided)
        elif query.address_street:
            address_match = True
            if query.address_street.lower() not in data.get("address", "").lower():
                address_match = False
            if query.address_city and query.address_city.lower() not in data.get("address", "").lower():
                address_match = False
            if query.address_zip and query.address_zip not in data.get("address", ""):
                address_match = False
            if address_match:
                match = True
        # Match by Owner Name (if provided and no address/parcel match)
        elif query.owner_last_name:
            name_match = False
            for owner in data.get("owner_names", []):
                owner_lower = owner.lower()
                last_name_match = query.owner_last_name.lower() in owner_lower
                first_name_match = not query.owner_first_name or query.owner_first_name.lower() in owner_lower
                if last_name_match and first_name_match:
                    name_match = True
                    break
            if name_match:
                match = True

        if match:
            matching_results.append(data.copy())

    print(f"Found {len(matching_results)} potential matches.")

    return PropertyResult(
        query_details=query,
        results=matching_results,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )

@app.get("/health", status_code=200)
async def health_check() -> Dict[str, str]:
    """Basic health check."""
    return {"status": "ok"}

# --- Main execution (for running with uvicorn) ---
# Example: uvicorn services.public_records.src.property_records_adapter.main:app --reload --port 8043


