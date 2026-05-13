#!/bin/bash
set -e

SPARK_MODE="${SPARK_MODE:-master}"
SPARK_MASTER_HOST="${SPARK_MASTER_HOST:-spark-master}"
SPARK_MASTER_PORT="${SPARK_MASTER_PORT:-7077}"
SPARK_MASTER_WEBUI_PORT="${SPARK_MASTER_WEBUI_PORT:-8080}"
SPARK_WORKER_WEBUI_PORT="${SPARK_WORKER_WEBUI_PORT:-8081}"
SPARK_WORKER_MEMORY="${SPARK_WORKER_MEMORY:-1g}"
SPARK_WORKER_CORES="${SPARK_WORKER_CORES:-1}"
SPARK_DAEMON_MEMORY="${SPARK_DAEMON_MEMORY:-512m}"

export SPARK_DAEMON_MEMORY

if [ "$SPARK_MODE" = "master" ]; then
    exec ${SPARK_HOME}/sbin/../bin/spark-class org.apache.spark.deploy.master.Master \
        --host "$SPARK_MASTER_HOST" \
        --port "$SPARK_MASTER_PORT" \
        --webui-port "$SPARK_MASTER_WEBUI_PORT"
elif [ "$SPARK_MODE" = "worker" ]; then
    exec ${SPARK_HOME}/sbin/../bin/spark-class org.apache.spark.deploy.worker.Worker \
        --webui-port "$SPARK_WORKER_WEBUI_PORT" \
        -m "$SPARK_WORKER_MEMORY" \
        -c "$SPARK_WORKER_CORES" \
        "$SPARK_MASTER_URL"
else
    echo "Unknown SPARK_MODE: $SPARK_MODE"
    exit 1
fi
