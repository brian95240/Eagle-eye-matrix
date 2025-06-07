from fastapi import FastAPI, HTTPException, Depends, Header, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import datetime
import httpx
import os

# --- Configuration ---
SERVICE_NAME = "tax_records_adapter"
KMS_URL = os.getenv("KMS_URL", "http://localhost:8050") # Get KMS URL from env or default

app = FastAPI(
    title="EEM Tax Records Adapter (Placeholder)",
    description="Simulates access to tax-related records. Requires API Key.",
    version="0.1.1" # Incremented version
)

# --- HTTP Client ---
# Re-initialize client if needed, or use a global one if preferred
# http_client = httpx.AsyncClient(timeout=5.0)

# --- Placeholder Data ---
# Note: SSN is highly sensitive, using placeholder identifiers
placeholder_data = {
    "john_doe_19900115_123main": {
        "full_name": "John Michael Doe",
        "date_of_birth": "1990-01-15",
        "ssn_last4": "6789", # Placeholder
        "filing_address": "123 Main St, Anytown, USA, 12345",
        "filing_status_history": [
            {"year": 2023, "status": "Married Filing Jointly"},
            {"year": 2022, "status": "Married Filing Jointly"},
            {"year": 2021, "status": "Single"}
        ],
        "estimated_income_bracket": "$75k-$100k" # Highly simplified placeholder
    },
    "alice_williams_19920722_123main": {
        "full_name": "Alice Grace Williams",
        "date_of_birth": "1992-07-22",
        "ssn_last4": "1234", # Placeholder
        "filing_address": "123 Main St, Anytown, USA, 12345",
        "filing_status_history": [
            {"year": 2023, "status": "Married Filing Jointly"},
            {"year": 2022, "status": "Married Filing Jointly"}
        ],
        "estimated_income_bracket": "$75k-$100k"
    },
    "jane_smith_19650310_456oak": {
        "full_name": "Jane Anne Smith",
        "date_of_birth": "1965-03-10",
        "ssn_last4": "5678", # Placeholder
        "filing_address": "456 Oak Ave, Otherville, USA, 67890",
        "filing_status_history": [
            {"year": 2023, "status": "Married Filing Jointly"},
            {"year": 2022, "status": "Married Filing Jointly"}
        ],
        "estimated_income_bracket": "$100k-$150k"
    }
}

# --- Request/Response Models ---
class TaxQuery(BaseModel):
    first_name: Optional[str] = Field(None, description="First name")
    last_name: str = Field(..., description="Last name")
    date_of_birth: Optional[str] = Field(None, description="Date of birth (YYYY-MM-DD)")
    ssn_last4: Optional[str] = Field(None, description="Last 4 digits of SSN (use with extreme caution)")
    address_street: Optional[str] = Field(None, description="Street address")
    address_city: Optional[str] = Field(None, description="City")
    address_zip: Optional[str] = Field(None, description="ZIP code")

class TaxResult(BaseModel):
    query_details: TaxQuery
    results: List[Dict[str, Any]] = Field(..., description="List of matching tax records found")
    source: str = "Tax Records Adapter (Placeholder)"
    timestamp: datetime.datetime

# --- API Key Verification Dependency (Adapted from Vital/Voting Adapters) ---
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
@app.post("/query", response_model=TaxResult)
async def query_tax_records(query: TaxQuery, api_key_data: Dict[str, Any] = Depends(verify_api_key)) -> TaxResult:
    """Simulates querying tax records based on provided details. Requires valid API Key."""
    print(f"Received tax records query: {query.model_dump()} (Key ID: {api_key_data.get('key_id')})")
    matching_results = []

    # Simple placeholder matching logic
    for key, data in placeholder_data.items():
        match = True
        # Name matching
        if query.last_name.lower() not in data["full_name"].lower():
            match = False
        if query.first_name and query.first_name.lower() not in data["full_name"].lower():
            match = False
        # DOB matching
        if query.date_of_birth and data.get("date_of_birth") != query.date_of_birth:
            match = False
        # SSN Last 4 matching (if provided)
        if query.ssn_last4 and data.get("ssn_last4") != query.ssn_last4:
            match = False
        # Address matching (simple check on street if provided)
        if query.address_street and query.address_street.lower() not in data.get("filing_address", "").lower():
            match = False
        # Add more address checks if needed (city, zip)

        if match:
            # Return a copy to avoid modifying placeholder data if needed later
            matching_results.append(data.copy())

    print(f"Found {len(matching_results)} potential matches.")

    return TaxResult(
        query_details=query,
        results=matching_results,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )

@app.get("/health", status_code=200)
async def health_check() -> Dict[str, str]:
    """Basic health check."""
    return {"status": "ok"}

# --- Main execution (for running with uvicorn) ---
# Example: uvicorn services.public_records.src.tax_records_adapter.main:app --reload --port 8042


