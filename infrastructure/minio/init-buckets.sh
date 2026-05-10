#!/usr/bin/env bash
# ============================================================
# MinIO Bucket Initialization
# Creates required buckets for the fraud intelligence platform
# ============================================================
set -euo pipefail

MINIO_HOST="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_USER="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_PASS="${MINIO_SECRET_KEY:-minioadmin123}"

echo "Waiting for MinIO to be ready..."
for i in $(seq 1 30); do
    if curl -sf "${MINIO_HOST}/minio/health/ready" > /dev/null 2>&1; then
        echo "MinIO is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: MinIO did not become ready in time."
        exit 1
    fi
    sleep 2
done

# Configure mc alias
docker exec fraud-minio mc alias set local "${MINIO_HOST}" "${MINIO_USER}" "${MINIO_PASS}" 2>/dev/null || \
    mc alias set local "${MINIO_HOST}" "${MINIO_USER}" "${MINIO_PASS}" 2>/dev/null || true

create_bucket() {
    local bucket_name="$1"
    echo "Creating bucket: ${bucket_name}"
    docker exec fraud-minio mc mb "local/${bucket_name}" --ignore-existing 2>/dev/null || \
        mc mb "local/${bucket_name}" --ignore-existing 2>/dev/null || \
        echo "  Bucket ${bucket_name} may already exist"
}

# Create buckets
create_bucket "lakehouse"
create_bucket "spark-checkpoints"
create_bucket "ml-models"
create_bucket "airflow-logs"

echo ""
echo "Listing buckets:"
docker exec fraud-minio mc ls local/ 2>/dev/null || mc ls local/ 2>/dev/null || echo "  Could not list buckets"
echo ""
echo "MinIO bucket initialization complete."
