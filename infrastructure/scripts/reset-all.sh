#!/usr/bin/env bash
# ============================================================
# Full Reset — stops everything, removes volumes, rebuilds
# ============================================================
set -euo pipefail

COMPOSE="docker compose"
ALL_PROFILES="--profile core --profile ml --profile ai --profile monitoring --profile frontend"

echo ""
echo "============================================"
echo "  Fraud Intelligence Platform — Full Reset"
echo "============================================"
echo ""
echo "WARNING: This will destroy ALL data including:"
echo "  - Kafka topics and messages"
echo "  - MinIO buckets and objects"
echo "  - PostgreSQL databases"
echo "  - Spark checkpoints"
echo "  - Iceberg tables"
echo "  - Redis cache"
echo "  - Ollama models"
echo "  - ChromaDB vectors"
echo "  - Airflow logs and DAG state"
echo ""

read -p "Are you sure? (y/N): " confirm
if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "[1/4] Stopping all services..."
${COMPOSE} ${ALL_PROFILES} down -v --remove-orphans 2>/dev/null || true

echo ""
echo "[2/4] Removing orphan volumes..."
docker volume ls --filter "name=fraud" -q | xargs -r docker volume rm 2>/dev/null || true

echo ""
echo "[3/4] Rebuilding images..."
${COMPOSE} ${ALL_PROFILES} build --no-cache

echo ""
echo "[4/4] Starting core services..."
${COMPOSE} --profile core up -d

echo ""
echo "Waiting for services to be healthy..."
sleep 15

echo ""
echo "Initializing Kafka topics..."
bash "$(dirname "$0")/init-kafka-topics.sh"

echo ""
echo "Initializing MinIO buckets..."
bash "$(dirname "$0")/../minio/init-buckets.sh"

echo ""
echo "============================================"
echo "  Reset complete. Core services are running."
echo "============================================"
echo ""
echo "Service URLs:"
echo "  Airflow:     http://localhost:8082"
echo "  Spark UI:    http://localhost:8080"
echo "  MinIO:       http://localhost:9001"
echo "  Nessie:      http://localhost:19120"
echo "  Backend:     http://localhost:8888"
echo ""
echo "Run 'make up-all' to start all services."
echo ""
