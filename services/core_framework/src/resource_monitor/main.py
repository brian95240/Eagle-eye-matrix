import asyncio
import json
import psutil
from fastapi import FastAPI, HTTPException, Depends, status
import redis.asyncio as redis
from typing import Dict, Any, Optional
import datetime
import os

from .models import ResourceMetrics, ServiceResourceReport

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
MONITORING_INTERVAL_SECONDS = 60 # How often to collect and report metrics
SERVICE_NAME = os.getenv("EEM_SERVICE_NAME", "resource-monitor") # Identify self
EVENT_STREAM_KEY = "eem_event_stream" # Redis stream key for events

# --- Redis Connection ---
async def get_redis_connection() -> redis.Redis:
    """Dependency to get an async Redis connection."""
    connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    try:
        yield connection
    finally:
        await connection.close()

# --- Metrics Collection ---
def get_system_metrics() -> ResourceMetrics:
    """Collects basic system-wide resource metrics."""
    # Note: psutil methods might block briefly. For high-frequency monitoring,
    # consider running them in a separate thread or process.
    cpu = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk_io = psutil.disk_io_counters()
    net_io = psutil.net_io_counters()

    return ResourceMetrics(
        cpu_utilization_percent=cpu,
        memory_usage_mb=memory.used / (1024 * 1024),
        # Disk/Net IO rates are harder to calculate accurately without tracking over time.
        # Reporting raw counters might be more practical initially.
        # disk_io_rate=disk_io.read_bytes + disk_io.write_bytes, # Example: total bytes
        # network_io_rate=net_io.bytes_sent + net_io.bytes_recv # Example: total bytes
    )

# --- Background Monitoring Task ---
async def monitor_and_report(redis_conn: redis.Redis):
    """Periodically collects metrics and publishes an event."""
    print(f"Starting resource monitoring loop (interval: {MONITORING_INTERVAL_SECONDS}s)")
    while True:
        try:
            metrics = get_system_metrics()
            report = ServiceResourceReport(
                service_name=SERVICE_NAME, # Reporting metrics for the monitor itself for now
                metrics=metrics
                # Status logic could be added here based on thresholds
            )

            # Construct the event payload
            event_payload = {
                "eventType": "system.resource.metrics.reported",
                "sourceService": SERVICE_NAME,
                "timestamp": report.timestamp.isoformat(),
                "payload": report.model_dump(exclude={"timestamp"}) # Exclude timestamp from nested payload
            }

            await redis_conn.xadd(EVENT_STREAM_KEY, {"event_data": json.dumps(event_payload)})
            print(f"Published resource metrics event: {report.model_dump_json()}")

        except Exception as e:
            print(f"Error during resource monitoring loop: {e}")

        await asyncio.sleep(MONITORING_INTERVAL_SECONDS)

# --- FastAPI App ---
app = FastAPI(
    title="EEM Resource Monitor Service",
    description="Monitors system resources and reports metrics.",
    version="0.1.0"
)

@app.on_event("startup")
async def startup_event():
    """Start the background monitoring task."""
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    asyncio.create_task(monitor_and_report(redis_conn))

@app.get("/metrics/current", response_model=ResourceMetrics)
async def get_current_metrics() -> ResourceMetrics:
    """Returns the latest collected system metrics."""
    try:
        return get_system_metrics()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metrics: {e}"
        )

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
# Example: uvicorn services.core_framework.src.resource_monitor.main:app --reload --port 8003

