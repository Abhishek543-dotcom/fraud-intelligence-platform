"""Data Lineage API — exposes the bronze→silver→gold pipeline as a DAG."""

import os
from typing import Any

import httpx
import structlog
from fastapi import APIRouter
from pydantic import BaseModel

logger = structlog.get_logger()

router = APIRouter()

# Nessie config (same pattern as sql_editor.py)
_raw_nessie = os.getenv("NESSIE_URI", "http://nessie:19120/api/v1").rstrip("/")
NESSIE_BASE = _raw_nessie.split("/api/")[0] if "/api/" in _raw_nessie else _raw_nessie


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class NodeMetadata(BaseModel):
    description: str
    row_count: int | None = None


class LineageNode(BaseModel):
    id: str
    type: str
    label: str
    metadata: NodeMetadata


class LineageEdge(BaseModel):
    source: str
    target: str
    label: str


class LineageGraph(BaseModel):
    nodes: list[LineageNode]
    edges: list[LineageEdge]


# ---------------------------------------------------------------------------
# Static lineage definition (fraud pipeline topology)
# ---------------------------------------------------------------------------

_STATIC_NODES: list[dict[str, Any]] = [
    {
        "id": "kafka.transactions_raw",
        "type": "source",
        "label": "Kafka: transactions_raw",
        "metadata": {"description": "Raw transaction events from payment gateway"},
    },
    {
        "id": "bronze.raw_transactions",
        "type": "bronze",
        "label": "raw_transactions",
        "metadata": {"description": "Raw append-only Iceberg table", "row_count": 50000},
    },
    {
        "id": "silver.enriched_transactions",
        "type": "silver",
        "label": "enriched_transactions",
        "metadata": {"description": "Deduplicated, feature-enriched transactions", "row_count": 48000},
    },
    {
        "id": "gold.fraud_metrics",
        "type": "gold",
        "label": "fraud_metrics",
        "metadata": {"description": "Aggregated fraud KPIs", "row_count": 100},
    },
    {
        "id": "gold.customer_risk_profiles",
        "type": "gold",
        "label": "customer_risk_profiles",
        "metadata": {"description": "Per-customer risk scores", "row_count": 10000},
    },
    {
        "id": "gold.merchant_risk_scores",
        "type": "gold",
        "label": "merchant_risk_scores",
        "metadata": {"description": "Per-merchant risk scores", "row_count": 500},
    },
    {
        "id": "kafka.fraud_alerts",
        "type": "sink",
        "label": "Kafka: fraud_alerts",
        "metadata": {"description": "High-confidence fraud alerts"},
    },
    {
        "id": "ml.feature_store",
        "type": "service",
        "label": "Feature Store (Redis)",
        "metadata": {"description": "Real-time feature vectors"},
    },
    {
        "id": "ml.model_service",
        "type": "service",
        "label": "ML Model Service",
        "metadata": {"description": "XGBoost+RF+IF ensemble"},
    },
]

_STATIC_EDGES: list[dict[str, str]] = [
    {"source": "kafka.transactions_raw", "target": "bronze.raw_transactions", "label": "Spark Streaming append"},
    {"source": "bronze.raw_transactions", "target": "silver.enriched_transactions", "label": "Dedup + Feature Engineering"},
    {"source": "silver.enriched_transactions", "target": "gold.fraud_metrics", "label": "Aggregation (hourly)"},
    {"source": "silver.enriched_transactions", "target": "gold.customer_risk_profiles", "label": "Customer rollup"},
    {"source": "silver.enriched_transactions", "target": "gold.merchant_risk_scores", "label": "Merchant rollup"},
    {"source": "silver.enriched_transactions", "target": "ml.feature_store", "label": "Feature extraction"},
    {"source": "ml.feature_store", "target": "ml.model_service", "label": "Real-time scoring"},
    {"source": "ml.model_service", "target": "kafka.fraud_alerts", "label": "High-score alerts (>0.85)"},
]

# Map Iceberg table node IDs to their Nessie catalog names for live row counts
_NODE_TABLE_MAP: dict[str, str] = {
    "bronze.raw_transactions": "bronze.raw_transactions",
    "silver.enriched_transactions": "silver.enriched_transactions",
    "gold.fraud_metrics": "gold.fraud_metrics",
    "gold.customer_risk_profiles": "gold.customer_risk_profiles",
    "gold.merchant_risk_scores": "gold.merchant_risk_scores",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _try_get_row_counts() -> dict[str, int]:
    """Attempt to get real row counts from Nessie/Iceberg.

    Returns a mapping of node_id -> row_count for tables we could reach.
    Falls back to empty dict on failure.
    """
    counts: dict[str, int] = {}
    try:
        from pyiceberg.catalog import load_catalog

        catalog = load_catalog(
            "nessie",
            **{
                "uri": f"{NESSIE_BASE}/api/v1",
                "ref": "main",
                "type": "rest",
                "s3.endpoint": os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
                "s3.access-key-id": os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
                "s3.secret-access-key": os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
                "warehouse": os.getenv("ICEBERG_WAREHOUSE", "s3a://lakehouse/warehouse"),
            },
        )
        for node_id, table_name in _NODE_TABLE_MAP.items():
            try:
                table = catalog.load_table(table_name)
                arrow = table.scan().to_arrow()
                counts[node_id] = arrow.num_rows
            except Exception:
                pass
    except Exception as exc:
        logger.debug("lineage_row_count_fallback", error=str(exc))
    return counts


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/lineage", response_model=LineageGraph)
async def get_lineage():
    """Return the full data lineage graph for the fraud pipeline."""
    # Try to enrich nodes with live row counts
    live_counts = _try_get_row_counts()

    nodes: list[LineageNode] = []
    for node_def in _STATIC_NODES:
        metadata = dict(node_def["metadata"])
        # Override with live row count if available
        if node_def["id"] in live_counts:
            metadata["row_count"] = live_counts[node_def["id"]]
        nodes.append(
            LineageNode(
                id=node_def["id"],
                type=node_def["type"],
                label=node_def["label"],
                metadata=NodeMetadata(**metadata),
            )
        )

    edges = [LineageEdge(**edge_def) for edge_def in _STATIC_EDGES]

    return LineageGraph(nodes=nodes, edges=edges)
