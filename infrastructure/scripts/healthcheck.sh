#!/usr/bin/env bash
# ============================================================
# Health Check — verifies all platform services are running
# ============================================================
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

check_service() {
    local name="$1"
    local container="$2"
    local check_cmd="$3"

    printf "  %-25s" "${name}"

    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$" 2>/dev/null; then
        echo -e "${YELLOW}NOT RUNNING${NC}"
        ((WARN++))
        return
    fi

    if eval "${check_cmd}" > /dev/null 2>&1; then
        echo -e "${GREEN}HEALTHY${NC}"
        ((PASS++))
    else
        echo -e "${RED}UNHEALTHY${NC}"
        ((FAIL++))
    fi
}

echo ""
echo "============================================"
echo "  Fraud Intelligence Platform Health Check"
echo "============================================"
echo ""

echo "Core Services:"
check_service "Kafka" "fraud-kafka" \
    "docker exec fraud-kafka kafka-broker-api-versions.sh --bootstrap-server localhost:9092"

check_service "Spark Master" "fraud-spark-master" \
    "curl -sf http://localhost:8080/"

check_service "Spark Worker" "fraud-spark-worker" \
    "curl -sf http://localhost:8081/"

check_service "MinIO" "fraud-minio" \
    "curl -sf http://localhost:9000/minio/health/ready"

check_service "Nessie" "fraud-nessie" \
    "curl -sf http://localhost:19120/api/v1/config"

check_service "PostgreSQL" "fraud-postgres" \
    "docker exec fraud-postgres pg_isready -U airflow"

check_service "Redis" "fraud-redis" \
    "docker exec fraud-redis redis-cli ping"

check_service "Airflow Webserver" "fraud-airflow-webserver" \
    "curl -sf http://localhost:8082/health"

check_service "Airflow Scheduler" "fraud-airflow-scheduler" \
    "docker exec fraud-airflow-scheduler airflow jobs check --job-type SchedulerJob --hostname \$(docker exec fraud-airflow-scheduler hostname)"

echo ""
echo "Application Services:"
check_service "Backend (FastAPI)" "fraud-backend" \
    "curl -sf http://localhost:8888/health"

check_service "Simulator" "fraud-simulator" \
    "docker exec fraud-simulator python -c 'import os; print(os.getpid())'"

echo ""
echo "Frontend Services:"
check_service "Frontend (React)" "fraud-frontend" \
    "curl -sf http://localhost:3000/"

echo ""
echo "AI Services:"
check_service "Ollama" "fraud-ollama" \
    "curl -sf http://localhost:11434/api/version"

check_service "ChromaDB" "fraud-chromadb" \
    "curl -sf http://localhost:8000/api/v1/heartbeat"

echo ""
echo "ML Services:"
check_service "ML Service" "fraud-ml-service" \
    "curl -sf http://localhost:8889/health"

echo ""
echo "Monitoring Services:"
check_service "Prometheus" "fraud-prometheus" \
    "curl -sf http://localhost:9090/-/healthy"

check_service "Grafana" "fraud-grafana" \
    "curl -sf http://localhost:3001/api/health"

echo ""
echo "============================================"
echo -e "  Results: ${GREEN}${PASS} healthy${NC}, ${RED}${FAIL} unhealthy${NC}, ${YELLOW}${WARN} not running${NC}"
echo "============================================"
echo ""

if [ "${FAIL}" -gt 0 ]; then
    exit 1
fi
