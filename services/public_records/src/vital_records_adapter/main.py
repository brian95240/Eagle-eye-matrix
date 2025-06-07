from fastapi import FastAPI, HTTPException, Depends, Header, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import datetime
import httpx

# --- Configuration ---
KMS_URL = "http://localhost:8050"
SERVICE_NAME = "vital-records-adapter"

app = FastAPI(
    title="EEM Vital Records Adapter (Placeholder)",
    description="Simulates access to vital records (birth, death, marriage). Requires API Key.",
    version="0.2.0" # Version updated
)

# --- HTTP Client ---
http_client = httpx.AsyncClient(timeout=5.0)

# --- Placeholder Data ---
placeholder_data = {
    "john_doe_19900115": {
        "birth_record": {
            "full_name": "John Michael Doe",
            "date_of_birth": "1990-01-15",
            "place_of_birth": "Anytown, USA",
            "mother_name": "Jane Smith",
            "father_name": "Richard Doe"
        },
        "marriage_records": [
            {
                "spouse_name": "Alice Williams",
                "date_of_marriage": "2015-06-20",
                "place_of_marriage": "Anytown, USA"
            }
        ],
        "death_record": None
    },
    "jane_smith_19650310": {
        "birth_record": {
            "full_name": "Jane Anne Smith",
            "date_of_birth": "1965-03-10",
            "place_of_birth": "Otherville, USA",
            "mother_name": "Mary Jones",
            "father_name": "Robert Smith"
        },
        "marriage_records": [
             {
                "spouse_name": "Richard Doe",
                "date_of_marriage": "1988-11-05",
                "place_of_marriage": "Otherville, USA"
            }
        ],
        "death_record": None
    }
}

# --- Request/Response Models ---
class VitalQuery(BaseModel):
    first_name: Optional[str] = Field(None, description="First name")
    last_name: str = Field(..., description="Last name")
    date_of_birth: Optional[str] = Field(None, description="Date of birth (YYYY-MM-DD)")

class VitalResult(BaseModel):
    query_details: VitalQuery
    results: List[Dict[str, Any]] = Field(..., description="List of matching vital records found")
    source: str = "Vital Records Adapter (Placeholder)"
    timestamp: datetime.datetime

# --- Security Dependency ---
async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Dependency to verify the API key against the KMS."""
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key required")

    try:
        response = await http_client.post(f"{KMS_URL}/keys/validate", json={"key_value": x_api_key})
        response.raise_for_status()
        validation_result = response.json()

        if not validation_result.get("is_valid") or validation_result.get("service_name") != SERVICE_NAME:
            print(f"Invalid API Key received: {x_api_key[:8]}... Reason: {validation_result.get('reason')}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Invalid or unauthorized API Key: {validation_result.get('reason', 'Validation failed')}")
        print(f"Valid API Key received: {validation_result.get('key_id')}")
        # Optionally, you could return the key_id or service_name if needed downstream
        return validation_result # Contains is_valid, key_id, service_name
    except httpx.RequestError as e:
        print(f"Error connecting to KMS: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not connect to Key Management Service")
    except Exception as e:
        print(f"Error during key validation: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error during key validation")

# --- API Endpoint ---
@app.post("/query", response_model=VitalResult, dependencies=[Depends(verify_api_key)])
async def query_vital_records(query: VitalQuery) -> VitalResult:
    """Simulates querying vital records based on provided details. Requires valid API Key."""
    print(f"Received vital records query: {query.model_dump()}")
    matching_results = []

    # Simple placeholder matching logic (same as before)
    search_key_base = f"{query.first_name or ''}_{query.last_name}".lower()
    search_key_dob = f"{query.date_of_birth}" if query.date_of_birth else ""
    full_search_key = f"{search_key_base}_{search_key_dob}"

    if query.date_of_birth and full_search_key in placeholder_data:
        matching_results.append(placeholder_data[full_search_key])
    else:
        for key, data in placeholder_data.items():
            if search_key_base in key:
                if not query.date_of_birth or (data.get("birth_record") and data["birth_record"].get("date_of_birth") == query.date_of_birth):
                    matching_results.append(data)

    print(f"Found {len(matching_results)} potential matches.")

    return VitalResult(
        query_details=query,
        results=matching_results,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )

@app.get("/health", status_code=200)
async def health_check() -> Dict[str, str]:
    """Basic health check."""
    # Could add a check to KMS health endpoint here
    return {"status": "ok"}

@app.on_event("shutdown")
async def shutdown_event():
    """Close the HTTP client on shutdown."""
    await http_client.aclose()

# --- Main execution (for running with uvicorn) ---
# Example: uvicorn services.public_records.src.vital_records_adapter.main:app --reload --port 8040

