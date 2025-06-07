import uuid
from fastapi import FastAPI, HTTPException, Depends, status
from typing import Dict, Any, Optional, List
import datetime

# Assuming models are in a shared location or copied
# Adjust import path based on final structure
from ..models import GeoKnowledgeEntry

# --- Configuration ---
SERVICE_NAME = "geo-knowledge"

# --- In-Memory Database ---
# Simple dictionary to store knowledge entries
# Key: entry_id, Value: GeoKnowledgeEntry
knowledge_db: Dict[str, GeoKnowledgeEntry] = {}

# --- Helper Functions ---
# (Could add functions for spatial indexing/searching later)

# --- FastAPI App ---
app = FastAPI(
    title="EEM Geospatial Knowledge Base Service",
    description="Manages and provides access to geospatial knowledge entries.",
    version="0.1.0"
)

@app.post("/knowledge", response_model=GeoKnowledgeEntry, status_code=status.HTTP_201_CREATED)
async def add_knowledge_entry(entry: GeoKnowledgeEntry) -> GeoKnowledgeEntry:
    """Adds a new geospatial knowledge entry to the database."""
    if entry.entry_id in knowledge_db:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Knowledge entry with ID {entry.entry_id} already exists."
        )
    knowledge_db[entry.entry_id] = entry
    print(f"Added knowledge entry: {entry.entry_id}")
    return entry

@app.get("/knowledge/{entry_id}", response_model=GeoKnowledgeEntry)
async def get_knowledge_entry(entry_id: str) -> GeoKnowledgeEntry:
    """Retrieves a specific knowledge entry by its ID."""
    entry = knowledge_db.get(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge entry with ID {entry_id} not found."
        )
    return entry

@app.get("/knowledge", response_model=List[GeoKnowledgeEntry])
async def search_knowledge_entries(
    # Basic search parameters (can be expanded significantly)
    name: Optional[str] = None,
    entry_type: Optional[str] = None,
    # Add spatial query params later (e.g., lat, lon, radius)
) -> List[GeoKnowledgeEntry]:
    """Searches for knowledge entries based on basic criteria."""
    results = list(knowledge_db.values())

    if name:
        results = [e for e in results if e.name and name.lower() in e.name.lower()]
    if entry_type:
        results = [e for e in results if e.entry_type.lower() == entry_type.lower()]

    # Add spatial filtering here when implemented

    return results

@app.delete("/knowledge/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_entry(entry_id: str):
    """Deletes a specific knowledge entry by its ID."""
    if entry_id not in knowledge_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge entry with ID {entry_id} not found."
        )
    del knowledge_db[entry_id]
    print(f"Deleted knowledge entry: {entry_id}")
    return

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok", "database_status": "in-memory"}

# --- Pre-populate with some data (Optional Example) ---
@app.on_event("startup")
async def populate_initial_data():
    """Adds some example data on startup."""
    if not knowledge_db: # Only add if empty
        example_entries = [
            GeoKnowledgeEntry(entry_id="landmark_001", entry_type="landmark", name="Eiffel Tower", latitude=48.8584, longitude=2.2945, metadata={"city": "Paris", "country": "France"}),
            GeoKnowledgeEntry(entry_id="landmark_002", entry_type="landmark", name="Statue of Liberty", latitude=40.6892, longitude=-74.0445, metadata={"city": "New York", "country": "USA"}),
            GeoKnowledgeEntry(entry_id="region_001", entry_type="region", name="Silicon Valley", latitude=37.3875, longitude=-122.0575, metadata={"description": "Tech hub in California"}),
        ]
        for entry in example_entries:
            knowledge_db[entry.entry_id] = entry
        print(f"Pre-populated knowledge base with {len(example_entries)} entries.")

# --- Main execution (for running with uvicorn) ---
# Example: uvicorn services.geo_pipeline.src.geo_knowledge.main:app --reload --port 8012

