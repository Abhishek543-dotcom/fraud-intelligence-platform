"""SparkSession factory configured with Iceberg and Nessie catalog."""

import logging
import os
from typing import Optional

from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)


def get_spark_session(
    app_name: str = "FraudIntelligencePlatform",
    master: Optional[str] = None,
    extra_config: Optional[dict] = None,
) -> SparkSession:
    """Create a SparkSession configured for Iceberg with Nessie catalog and MinIO storage.

    Args:
        app_name: Application name shown in Spark UI.
        master: Spark master URL. Defaults to SPARK_MASTER_URL env var.
        extra_config: Additional Spark configuration key-value pairs.

    Returns:
        Configured SparkSession instance.
    """
    master_url = master or os.getenv("SPARK_MASTER_URL", "spark://spark-master:7077")
    nessie_uri = os.getenv("NESSIE_URI", "http://nessie:19120/api/v1")
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
    warehouse = os.getenv("ICEBERG_WAREHOUSE", "s3a://lakehouse/warehouse")

    builder = (
        SparkSession.builder
        .appName(app_name)
        .master(master_url)
        # Iceberg extensions
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        # Nessie catalog
        .config("spark.sql.catalog.nessie", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.nessie.catalog-impl", "org.apache.iceberg.nessie.NessieCatalog")
        .config("spark.sql.catalog.nessie.uri", nessie_uri)
        .config("spark.sql.catalog.nessie.ref", "main")
        .config("spark.sql.catalog.nessie.warehouse", warehouse)
        # Tell Iceberg's S3FileIO (AWS SDK v2) to talk to MinIO instead of real S3
        .config("spark.sql.catalog.nessie.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.catalog.nessie.s3.endpoint", minio_endpoint)
        .config("spark.sql.catalog.nessie.s3.access-key-id", minio_access_key)
        .config("spark.sql.catalog.nessie.s3.secret-access-key", minio_secret_key)
        .config("spark.sql.catalog.nessie.s3.path-style-access", "true")
        .config("spark.sql.catalog.nessie.s3.region", "us-east-1")
        # S3/MinIO
        .config("spark.hadoop.fs.s3a.endpoint", minio_endpoint)
        .config("spark.hadoop.fs.s3a.access.key", minio_access_key)
        .config("spark.hadoop.fs.s3a.secret.key", minio_secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        # Performance
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        # Streaming
        .config("spark.sql.streaming.checkpointLocation", "s3a://spark-checkpoints/")
    )

    if extra_config:
        for key, value in extra_config.items():
            builder = builder.config(key, value)

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    logger.info(
        "SparkSession created: app=%s, master=%s, nessie=%s",
        app_name,
        master_url,
        nessie_uri,
    )
    return spark


def create_namespaces(spark: SparkSession) -> None:
    """Create the bronze/silver/gold namespaces in the Nessie catalog if they don't exist."""
    for ns in ["bronze", "silver", "gold"]:
        try:
            spark.sql(f"CREATE NAMESPACE IF NOT EXISTS nessie.{ns}")
            logger.info("Namespace 'nessie.%s' ready.", ns)
        except Exception as e:
            logger.warning("Could not create namespace '%s': %s", ns, e)
