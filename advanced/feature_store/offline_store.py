"""Iceberg-backed offline feature store for batch features and training data."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class OfflineFeatureStore:
    """Iceberg-backed historical feature store.

    Provides point-in-time correct feature retrieval for model training,
    feature materialization via Spark, and schema versioning.
    """

    def __init__(self, spark_session, catalog: str = "nessie", warehouse: str = "fraud_db") -> None:
        """Initialize the offline store.

        Args:
            spark_session: Active SparkSession configured for Iceberg.
            catalog: Iceberg catalog name.
            warehouse: Database/warehouse name.
        """
        self._spark = spark_session
        self._catalog = catalog
        self._warehouse = warehouse

    def _table_path(self, feature_group: str) -> str:
        return f"{self._catalog}.{self._warehouse}.features_{feature_group}"

    def get_features_at_time(
        self,
        feature_group: str,
        entity_ids: list[str],
        point_in_time: datetime,
        features: Optional[list[str]] = None,
    ):
        """Retrieve point-in-time correct features.

        Uses Iceberg time-travel to get feature values as they were
        at a specific historical moment — critical for avoiding
        data leakage during model training.

        Args:
            feature_group: Name of the feature group (e.g., "customer_profile").
            entity_ids: Entity IDs to retrieve.
            point_in_time: The timestamp at which to evaluate features.
            features: Specific feature columns (None = all).

        Returns:
            Spark DataFrame with features.
        """
        table = self._table_path(feature_group)
        cols = ", ".join(features) if features else "*"
        ids = ", ".join(f"'{eid}'" for eid in entity_ids)

        query = f"""
            SELECT {cols} FROM {table}
            TIMESTAMP AS OF '{point_in_time.isoformat()}'
            WHERE entity_id IN ({ids})
        """

        logger.info("offline_feature_query",
                     feature_group=feature_group,
                     entity_count=len(entity_ids),
                     point_in_time=point_in_time.isoformat())

        return self._spark.sql(query)

    def materialize_features(
        self,
        feature_group: str,
        source_query: str,
        mode: str = "append",
    ) -> dict:
        """Materialize features from a source query into the Iceberg feature table.

        Args:
            feature_group: Target feature group name.
            source_query: SQL query that produces the feature data.
            mode: Write mode ("append" or "overwrite").

        Returns:
            Summary dict with row count and table info.
        """
        table = self._table_path(feature_group)

        logger.info("materializing_features",
                     feature_group=feature_group,
                     mode=mode)

        df = self._spark.sql(source_query)
        row_count = df.count()

        df.writeTo(table).using("iceberg")
        if mode == "overwrite":
            df.writeTo(table).overwritePartitions()
        else:
            df.writeTo(table).append()

        logger.info("features_materialized",
                     feature_group=feature_group,
                     rows=row_count)

        return {
            "feature_group": feature_group,
            "table": table,
            "rows_written": row_count,
            "mode": mode,
        }

    def get_training_dataset(
        self,
        feature_groups: list[str],
        entity_column: str = "entity_id",
        label_table: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ):
        """Generate a training dataset by joining feature groups with labels.

        Args:
            feature_groups: List of feature group names to join.
            entity_column: Column to join on.
            label_table: Optional table containing ground-truth labels.
            start_time: Optional time range filter start.
            end_time: Optional time range filter end.

        Returns:
            Spark DataFrame with joined features and labels.
        """
        if not feature_groups:
            raise ValueError("At least one feature group required")

        base_table = self._table_path(feature_groups[0])
        query = f"SELECT * FROM {base_table} AS fg0"

        for i, fg in enumerate(feature_groups[1:], 1):
            fg_table = self._table_path(fg)
            query += f" JOIN {fg_table} AS fg{i} ON fg0.{entity_column} = fg{i}.{entity_column}"

        if label_table:
            query += f" JOIN {label_table} ON fg0.{entity_column} = {label_table}.{entity_column}"

        conditions = []
        if start_time:
            conditions.append(f"fg0.event_timestamp >= '{start_time.isoformat()}'")
        if end_time:
            conditions.append(f"fg0.event_timestamp <= '{end_time.isoformat()}'")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        logger.info("training_dataset_query", feature_groups=feature_groups, label_table=label_table)
        return self._spark.sql(query)

    def get_schema_versions(self, feature_group: str) -> list[dict]:
        """List schema versions for a feature group using Iceberg metadata.

        Returns:
            List of schema version dicts.
        """
        table = self._table_path(feature_group)
        snapshots = self._spark.sql(f"SELECT * FROM {table}.snapshots ORDER BY committed_at DESC")
        return [row.asDict() for row in snapshots.collect()]
