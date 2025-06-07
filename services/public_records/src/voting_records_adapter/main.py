from fastapi import FastAPI, HTTPException, Depends, Header, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import datetime
import httpx
import os

# --- Configuration ---
SERVICE_NAME = "voting_records_adapter"
KMS_URL = os.getenv("KMS_URL", "http://localhost:8050") # Get KMS URL from env or default

app = FastAPI(
    title="EEM Voting Records Adapter (Placeholder)",
    description="Simulates access to voting registration records, requires API key.",
    version="0.1.1" # Incremented version
)

# --- Placeholder Data ---
placeholder_data = {
    "john_doe_19900115_anytown": {
        "full_name": "John Michael Doe",
        "date_of_birth": "1990-01-15",
        "registration_address": "123 Main St, Anytown, USA, 12345",
        "registration_date": "2012-05-10",
        "party_affiliation": "Independent",
        "voting_history": [
            {"election_date": "2024-11-05", "voted": True},
            {"election_date": "2022-11-08", "voted": True},
            {"election_date": "2020-11-03", "voted": False}
        ]
    },
    "alice_williams_19920722_anytown": {
        "full_name": "Alice Grace Williams",
        "date_of_birth": "1992-07-22",
        "registration_address": "123 Main St, Anytown, USA, 12345",
        "registration_date": "2014-08-15",
        "party_affiliation": "Democrat",
        "voting_history": [
            {"election_date": "2024-11-05", "voted": True},
            {"election_date": "2022-11-08", "voted": True},
            {"election_date": "2020-11-03", "voted": True}
        ]
    },
    "jane_smith_19650310_otherville": {
        "full_name": "Jane Anne Smith",
        "date_of_birth": "1965-03-10",
        "registration_address": "456 Oak Ave, Otherville, USA, 67890",
        "registration_date": "1995-01-20",
        "party_affiliation": "Republican",
        "voting_history": [
            {"election_date": "2024-11-05", "voted": True},
            {"election_date": "2020-11-03", "voted": True}
        ]
    }
}

# --- Request/Response Models ---
class VotingQuery(BaseModel):
    first_name: Optional[str] = Field(None, description="First name")
    last_name: str = Field(..., description="Last name")
    date_of_birth: Optional[str] = Field(None, description="Date of birth (YYYY-MM-DD)")
    address_street: Optional[str] = Field(None, description="Street address")
    address_city: Optional[str] = Field(None, description="City")
    address_zip: Optional[str] = Field(None, description="ZIP code")

class VotingResult(BaseModel):
    query_details: VotingQuery
    results: List[Dict[str, Any]] = Field(..., description="List of matching voting records found")
    source: str = "Voting Records Adapter (Placeholder)"
    timestamp: datetime.datetime

# --- API Key Verification Dependency ---
async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Dependency to verify the API key against the KMS."""
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key required")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{KMS_URL}/verify_key", json={"api_key": x_api_key, "service_name": SERVICE_NAME})
            response.raise_for_status()
            validation_result = response.json()

            if not validation_result.get("is_valid") or validation_result.get("service_name") != SERVICE_NAME:
                print(f"Invalid API Key received: {x_api_key[:8]}... Reason: {validation_result.get("reason")}")
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Invalid or unauthorized API Key: {validation_result.get("reason", "Validation failed")}")
            print(f"Valid API Key received: {validation_result.get("key_id")}")
            # Optionally, you could return the key_id or service_name if needed downstream
            return validation_result # Contains is_valid, key_id, service_name
    except httpx.RequestError as e:
        print(f"Error connecting to KMS: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not connect to Key Management Service")
    except Exception as e:
        print(f"Unexpected error during API key verification: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error during API key verification")

# --- API Endpoint ---
@app.post("/query", response_model=VotingResult)
async def query_voting_records(query: VotingQuery, api_key_data: Dict[str, Any] = Depends(verify_api_key)) -> VotingResult:
    """Simulates querying voting records based on provided details. Requires valid API Key."""
    print(f"Received voting records query: {query.model_dump()} (Key ID: {api_key_data.get("key_id")})")
    matching_results = []

    # Simple placeholder matching logic - less precise than vital records
    for key, data in placeholder_data.items():
        match = True
        # Name matching (required last name, optional first)
        if query.last_name.lower() not in data["full_name"].lower():
            match = False
        if query.first_name and query.first_name.lower() not in data["full_name"].lower():
            match = False
        # DOB matching (if provided)
        if query.date_of_birth and data.get("date_of_birth") != query.date_of_birth:
            match = False
        # Address matching (if provided - simple substring checks)
        if query.address_street and query.address_street.lower() not in data.get("registration_address", "").lower():
            match = False
        if query.address_city and query.address_city.lower() not in data.get("registration_address", "").lower():
            match = False
        if query.address_zip and query.address_zip not in data.get("registration_address", ""):
             match = False

        if match:
            matching_results.append(data)

    print(f"Found {len(matching_results)} potential matches.")

    return VotingResult(
        query_details=query,
        results=matching_results,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )

@app.get("/health", status_code=200)
async def health_check() -> Dict[str, str]:
    """Basic health check."""
    return {"status": "ok"}

# --- Main execution (for running with uvicorn) ---
# Example: uvicorn services.public_records.src.voting_records_adapter.main:app --reload --port 8041

