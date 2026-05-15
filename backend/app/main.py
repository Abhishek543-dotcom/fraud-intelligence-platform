import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app, Counter, Histogram

from app.config import get_settings
from app.dependencies import close_redis
from app.routers import transactions, fraud_alerts, ml_predictions, investigation, metrics, websocket, sql_editor
from app.services.kafka_consumer import KafkaAlertConsumer

logger = structlog.get_logger()
settings = get_settings()

# Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    logger.info("Starting Fraud Intelligence Backend")

    # Start background Kafka consumer for alerts
    consumer = KafkaAlertConsumer(
        broker=settings.kafka_broker,
        topic="fraud_alerts",
        ws_manager=websocket.manager,
    )
    consumer_task = asyncio.create_task(consumer.start())
    app.state.kafka_consumer = consumer
    app.state.kafka_consumer_task = consumer_task

    logger.info("Backend startup complete")
    yield

    # Shutdown
    logger.info("Shutting down backend")
    consumer.stop()
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await close_redis()
    logger.info("Backend shutdown complete")


app = FastAPI(
    title="Fraud Intelligence Platform API",
    description="Real-time fraud detection and investigation API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track request count and latency."""
    import time

    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    endpoint = request.url.path
    method = request.method
    status = response.status_code

    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
    REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

    return response


# Include routers
app.include_router(transactions.router, prefix="/api", tags=["transactions"])
app.include_router(fraud_alerts.router, prefix="/api", tags=["alerts"])
app.include_router(ml_predictions.router, prefix="/api", tags=["ml"])
app.include_router(investigation.router, prefix="/api", tags=["investigation"])
app.include_router(metrics.router, prefix="/api", tags=["metrics"])
app.include_router(websocket.router, tags=["websocket"])
app.include_router(sql_editor.router, prefix="/api", tags=["sql-editor"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "fraud-intelligence-backend"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "message": str(exc)},
    )
