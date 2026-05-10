"""OpenTelemetry instrumentation for Python services."""

from __future__ import annotations

import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def setup_telemetry(
    service_name: str,
    otlp_endpoint: Optional[str] = None,
    enable_console: bool = False,
) -> trace.Tracer:
    """Initialize OpenTelemetry tracing for a Python service.

    Args:
        service_name: Name of the service (e.g., "fraud-backend", "ml-service").
        otlp_endpoint: OTLP gRPC endpoint (e.g., "http://jaeger:4317").
            Falls back to OTEL_EXPORTER_OTLP_ENDPOINT env var, then console.
        enable_console: If True, also export spans to console (for debugging).

    Returns:
        A configured Tracer instance.
    """
    endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    resource = Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
    })

    provider = TracerProvider(resource=resource)

    if endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    if enable_console or not endpoint:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    # Auto-instrument common libraries
    FastAPIInstrumentor.instrument()
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()

    return trace.get_tracer(service_name)


def create_span(tracer: trace.Tracer, name: str, attributes: Optional[dict] = None):
    """Create a custom span context manager.

    Usage:
        tracer = setup_telemetry("my-service")
        with create_span(tracer, "model_inference", {"model": "xgboost"}):
            result = model.predict(features)
    """
    span_attrs = attributes or {}
    return tracer.start_as_current_span(name, attributes=span_attrs)
