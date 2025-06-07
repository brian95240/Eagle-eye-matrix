from pydantic import BaseModel, Field
from typing import Dict, Optional
import datetime

class ResourceMetrics(BaseModel):
    """Represents resource usage metrics for a specific service."""
    cpu_utilization_percent: Optional[float] = Field(None, description="CPU utilization percentage")
    memory_usage_mb: Optional[float] = Field(None, description="Memory usage in megabytes")
    disk_io_rate: Optional[float] = Field(None, description="Disk I/O rate (e.g., MB/s)")
    network_io_rate: Optional[float] = Field(None, description="Network I/O rate (e.g., MB/s)")

class ServiceResourceReport(BaseModel):
    """Represents a resource report for a specific service at a point in time."""
    service_name: str = Field(..., description="Name of the service being reported")
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="Timestamp of the report")
    metrics: ResourceMetrics = Field(..., description="Collected resource metrics")
    status: str = Field(default="ok", description="Overall status based on metrics (e.g., ok, warning, critical)")

