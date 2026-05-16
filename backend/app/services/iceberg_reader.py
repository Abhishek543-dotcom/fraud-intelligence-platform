"""Shared Iceberg reader service — reusable helpers for querying Iceberg tables via Nessie + PyIceberg + DuckDB."""

import os
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Nessie base URL
# ---------------------------------------------------------------------------

_raw_nessie = os.getenv("NESSIE_URI", "http://nessie:19120/api/v1").rstrip("/")
NESSIE_BASE = _raw_nessie.split("/api/")[0] if "/api/" in _raw_nessie else _raw_nessie


def _get_nessie_base() -> str:
    """Return the Nessie base URL (scheme + host + port, no path)."""
    return NESSIE_BASE


def _get_catalog():
    """Load the PyIceberg Nessie REST catalog with MinIO S3 storage.

    Returns None if pyiceberg is not installed or catalog is unreachable.
    """
    try:
        from pyiceberg.catalog import load_catalog

        return load_catalog(
            "nessie",
            **{
                "uri": f"{_get_nessie_base()}/api/v1",
                "ref": "main",
                "type": "rest",
                "s3.endpoint": os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
                "s3.access-key-id": os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
                "s3.secret-access-key": os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
                "warehouse": os.getenv("ICEBERG_WAREHOUSE", "s3a://lakehouse/warehouse"),
            },
        )
    except Exception as exc:
        logger.warning("iceberg_catalog_unavailable", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def list_tables() -> list[dict[str, str]]:
    """Fetch all table entries from the Nessie catalog.

    Returns a list of dicts with keys: namespace, name, full_name, type.
    """
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{_get_nessie_base()}/api/v1/trees/tree/main/entries")
            resp.raise_for_status()
            entries = resp.json().get("entries", [])
    except Exception as exc:
        logger.warning("nessie_list_tables_failed", error=str(exc))
        return []

    tables: list[dict[str, str]] = []
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
            {
                "namespace": namespace,
                "name": table_name,
                "full_name": ".".join(name_parts),
                "type": kind,
            }
        )
    return tables


def query_table(
    full_table_name: str,
    sql: str,
    limit: int = 1000,
) -> dict[str, Any]:
    """Load an Iceberg table via PyIceberg, scan to Arrow, and run SQL with DuckDB.

    Returns {"columns": [...], "rows": [[...], ...], "row_count": int}.
    Falls back to empty result on failure.
    """
    try:
        import duckdb

        catalog = _get_catalog()
        if catalog is None:
            return {"columns": [], "rows": [], "row_count": 0}

        iceberg_table = catalog.load_table(full_table_name)
        arrow_table = iceberg_table.scan().to_arrow()

        con = duckdb.connect()
        # Register table under both dotted-underscore and short names
        safe_name = full_table_name.replace(".", "_")
        short_name = full_table_name.rsplit(".", 1)[-1]
        con.register(safe_name, arrow_table)
        con.register(short_name, arrow_table)

        sql_with_limit = sql.strip().rstrip(";")
        if limit and "LIMIT" not in sql.upper():
            sql_with_limit = f"{sql_with_limit} LIMIT {limit}"

        result = con.execute(sql_with_limit)
        columns = [desc[0] for desc in result.description]
        rows = [list(row) for row in result.fetchall()]

        return {"columns": columns, "rows": rows, "row_count": len(rows)}

    except Exception as exc:
        logger.warning("iceberg_query_failed", table=full_table_name, error=str(exc))
        return {"columns": [], "rows": [], "row_count": 0}


def get_table_row_count(full_table_name: str) -> int:
    """Quick row count for an Iceberg table via PyIceberg scan."""
    try:
        catalog = _get_catalog()
        if catalog is None:
            return 0
        iceberg_table = catalog.load_table(full_table_name)
        arrow_table = iceberg_table.scan().to_arrow()
        return arrow_table.num_rows
    except Exception as exc:
        logger.warning("iceberg_row_count_failed", table=full_table_name, error=str(exc))
        return 0


def get_table_schema(full_table_name: str) -> list[dict[str, str]]:
    """Return column name/type pairs for an Iceberg table.

    Returns [{"name": "col", "type": "string"}, ...].
    """
    try:
        catalog = _get_catalog()
        if catalog is None:
            return []
        iceberg_table = catalog.load_table(full_table_name)
        return [
            {"name": field.name, "type": str(field.field_type)}
            for field in iceberg_table.schema().fields
        ]
    except Exception as exc:
        logger.warning("iceberg_schema_failed", table=full_table_name, error=str(exc))
        return []
