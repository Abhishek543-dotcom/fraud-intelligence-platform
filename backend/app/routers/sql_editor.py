"""SQL Editor API — browse Iceberg tables and execute read-only SQL queries."""

import os
import re
import time
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = structlog.get_logger()

router = APIRouter()

# NESSIE_URI env may include path like /api/v1 — extract the base (scheme + host + port)
_raw_nessie = os.getenv("NESSIE_URI", "http://nessie:19120/api/v1").rstrip("/")
# Strip /api/v... suffix to get base URL
NESSIE_BASE = _raw_nessie.split("/api/")[0] if "/api/" in _raw_nessie else _raw_nessie

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=5000)
    limit: int = Field(default=1000, ge=1, le=10000)


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_time_ms: float


class TableInfo(BaseModel):
    namespace: str
    name: str
    full_name: str
    type: str


class TableSchema(BaseModel):
    namespace: str
    name: str
    columns: list[dict[str, str]]


# ---------------------------------------------------------------------------
# SQL safety check
# ---------------------------------------------------------------------------

_ALLOWED_STATEMENTS = re.compile(
    r"^\s*(SELECT|SHOW|DESCRIBE|DESC|WITH|EXPLAIN)\b",
    re.IGNORECASE,
)

_FORBIDDEN_PATTERNS = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|MERGE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


def _validate_sql(sql: str) -> None:
    """Ensure the SQL is read-only."""
    stripped = sql.strip().rstrip(";")
    if not _ALLOWED_STATEMENTS.match(stripped):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT, SHOW, DESCRIBE, and EXPLAIN statements are allowed.",
        )
    if _FORBIDDEN_PATTERNS.search(stripped):
        raise HTTPException(
            status_code=400,
            detail="Write/DDL statements are not allowed in the SQL editor.",
        )


# ---------------------------------------------------------------------------
# Nessie helpers
# ---------------------------------------------------------------------------


def _fetch_nessie_entries() -> list[dict]:
    """Fetch all entries from Nessie catalog."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{NESSIE_BASE}/api/v1/trees/tree/main/entries")
            resp.raise_for_status()
            return resp.json().get("entries", [])
    except Exception as exc:
        logger.warning("nessie_fetch_failed", error=str(exc))
        return []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/sql/tables", response_model=list[TableInfo])
async def list_tables():
    """List all Iceberg tables from the Nessie catalog."""
    entries = _fetch_nessie_entries()
    tables: list[TableInfo] = []
    for entry in entries:
        kind = entry.get("type") or entry.get("contentType") or ""
        if "NAMESPACE" in str(kind).upper():
            continue
        name_parts = entry.get("name", {}).get("elements") or []
        if len(name_parts) >= 2:
            namespace = name_parts[0]
            table_name = ".".join(name_parts[1:])
        elif len(name_parts) == 1:
            namespace = "default"
            table_name = name_parts[0]
        else:
            continue
        tables.append(
            TableInfo(
                namespace=namespace,
                name=table_name,
                full_name=".".join(name_parts),
                type=kind,
            )
        )
    return tables


@router.get("/sql/tables/{namespace}/{table}/schema", response_model=TableSchema)
async def get_table_schema(namespace: str, table: str):
    """Get schema (columns) for a specific Iceberg table.

    Uses PyIceberg to load the table and read its schema.
    Falls back to a simulated schema if PyIceberg/catalog is unavailable.
    """
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
        iceberg_table = catalog.load_table(f"{namespace}.{table}")
        columns = [
            {"name": field.name, "type": str(field.field_type)}
            for field in iceberg_table.schema().fields
        ]
        return TableSchema(namespace=namespace, name=table, columns=columns)
    except Exception as exc:
        logger.warning("schema_load_failed", namespace=namespace, table=table, error=str(exc))
        # Fallback: return empty schema with error context
        raise HTTPException(
            status_code=503,
            detail=f"Could not load schema for {namespace}.{table}: {exc}",
        )


@router.post("/sql/execute", response_model=QueryResult)
async def execute_query(request: QueryRequest):
    """Execute a read-only SQL query against Iceberg tables.

    Uses PyIceberg to load tables and DuckDB to execute SQL over Arrow data.
    """
    _validate_sql(request.sql)

    start = time.perf_counter()

    try:
        import duckdb
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

        # Create DuckDB connection and register Iceberg tables
        con = duckdb.connect()

        # Register all available tables in DuckDB
        entries = _fetch_nessie_entries()
        for entry in entries:
            kind = entry.get("type") or entry.get("contentType") or ""
            if "NAMESPACE" in str(kind).upper():
                continue
            name_parts = entry.get("name", {}).get("elements") or []
            if not name_parts:
                continue
            full_name = ".".join(name_parts)
            try:
                iceberg_table = catalog.load_table(full_name)
                arrow_table = iceberg_table.scan().to_arrow()
                # Register as both full name (with underscores) and short name
                safe_name = full_name.replace(".", "_")
                con.register(safe_name, arrow_table)
                if len(name_parts) >= 2:
                    con.register(name_parts[-1], arrow_table)
            except Exception as table_exc:
                logger.debug("skip_table_register", table=full_name, error=str(table_exc))

        # Execute the query with row limit
        sql_with_limit = request.sql.strip().rstrip(";")
        if request.limit and "LIMIT" not in request.sql.upper():
            sql_with_limit = f"{sql_with_limit} LIMIT {request.limit}"

        result = con.execute(sql_with_limit)
        columns = [desc[0] for desc in result.description]
        rows = [list(row) for row in result.fetchall()]

        elapsed = (time.perf_counter() - start) * 1000

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=round(elapsed, 2),
        )

    except HTTPException:
        raise
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        logger.error("query_execution_failed", sql=request.sql[:200], error=str(exc))
        raise HTTPException(
            status_code=400,
            detail=f"Query execution failed: {exc}",
        )
