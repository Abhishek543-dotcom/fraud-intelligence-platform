#!/usr/bin/env bash
# ============================================================
# Kafka Topic Initialization
# Creates all required topics for the fraud intelligence platform
# ============================================================
set -euo pipefail

KAFKA_CONTAINER="fraud-kafka"
BOOTSTRAP="localhost:9092"

echo "============================================"
echo "  Kafka Topic Initialization"
echo "============================================"
echo ""

# Wait for Kafka to be ready
echo "Waiting for Kafka broker to be ready..."
for i in $(seq 1 60); do
    if docker exec "${KAFKA_CONTAINER}" kafka-broker-api-versions.sh --bootstrap-server "${BOOTSTRAP}" > /dev/null 2>&1; then
        echo "Kafka broker is ready."
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "ERROR: Kafka broker did not become ready in time."
        exit 1
    fi
    sleep 2
done

echo ""

create_topic() {
    local topic="$1"
    local partitions="$2"
    local retention_ms="$3"
    local cleanup_policy="${4:-delete}"

    echo -n "Creating topic: ${topic} (partitions=${partitions}, retention=${retention_ms}ms, cleanup=${cleanup_policy})... "

    local config_args="--config retention.ms=${retention_ms} --config cleanup.policy=${cleanup_policy}"

    if docker exec "${KAFKA_CONTAINER}" kafka-topics.sh \
        --bootstrap-server "${BOOTSTRAP}" \
        --create \
        --topic "${topic}" \
        --partitions "${partitions}" \
        --replication-factor 1 \
        --config "retention.ms=${retention_ms}" \
        --config "cleanup.policy=${cleanup_policy}" \
        --if-not-exists 2>/dev/null; then
        echo "OK"
    else
        echo "ALREADY EXISTS or ERROR"
    fi
}

# transactions_raw: raw transaction events from simulator
# 6 partitions, 7 day retention
create_topic "transactions_raw" 6 604800000 "delete"

# transactions_enriched: enriched with feature engineering
# 6 partitions, 14 day retention
create_topic "transactions_enriched" 6 1209600000 "delete"

# fraud_alerts: confirmed fraud alerts
# 3 partitions, 30 day retention, compact
create_topic "fraud_alerts" 3 2592000000 "compact"

# model_predictions: ML model prediction results
# 6 partitions, 14 day retention
create_topic "model_predictions" 6 1209600000 "delete"

# replay_events: for replaying historical transactions
# 3 partitions, 30 day retention
create_topic "replay_events" 3 2592000000 "delete"

# audit_logs: audit trail for compliance
# 3 partitions, 90 day retention, compact
create_topic "audit_logs" 3 7776000000 "compact"

# dlq_transactions: dead letter queue for failed processing
# 3 partitions, 30 day retention
create_topic "dlq_transactions" 3 2592000000 "delete"

echo ""
echo "Listing all topics:"
docker exec "${KAFKA_CONTAINER}" kafka-topics.sh \
    --bootstrap-server "${BOOTSTRAP}" \
    --list

echo ""
echo "============================================"
echo "  Kafka topic initialization complete."
echo "============================================"
