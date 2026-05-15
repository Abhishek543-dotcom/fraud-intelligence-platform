#!/usr/bin/env sh
# ============================================================
# MinIO Bucket Initialization
# Runs INSIDE the minio/mc image (which already provides `mc`)
# ============================================================
set -eu

MINIO_HOST="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_USER="${MINIO_ROOT_USER:-${MINIO_ACCESS_KEY:-minioadmin}}"
MINIO_PASS="${MINIO_ROOT_PASSWORD:-${MINIO_SECRET_KEY:-minioadmin123}}"

echo "Waiting for MinIO at ${MINIO_HOST} ..."
i=0
while [ "$i" -lt 60 ]; do
    if mc alias set local "${MINIO_HOST}" "${MINIO_USER}" "${MINIO_PASS}" >/dev/null 2>&1; then
        echo "MinIO is reachable."
        break
    fi
    i=$((i+1))
    sleep 2
done

if [ "$i" -ge 60 ]; then
    echo "ERROR: MinIO did not become ready in time."
    exit 1
fi

create_bucket() {
    bucket="$1"
    if mc ls "local/${bucket}" >/dev/null 2>&1; then
        echo "  bucket already exists: ${bucket}"
    else
        echo "  creating bucket: ${bucket}"
        mc mb "local/${bucket}"
    fi
}

create_bucket "lakehouse"
create_bucket "spark-checkpoints"
create_bucket "ml-models"
create_bucket "airflow-logs"

echo
echo "Buckets:"
mc ls local/
echo
echo "MinIO bucket initialization complete."
