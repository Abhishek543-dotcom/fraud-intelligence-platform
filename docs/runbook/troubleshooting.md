# Troubleshooting Guide

Common issues, their diagnosis, and resolution procedures for the Fraud Intelligence Platform.

---

## Kafka Issues

### Broker Won't Start (KRaft Initialization)

!!! failure "Symptoms"
    - Kafka container exits immediately or restarts in a loop
    - Logs show `Not a valid storage directory` or `Log directory not found`
    - KRaft metadata errors on first startup

**Diagnosis:**

```bash
docker logs kafka 2>&1 | tail -50
docker inspect kafka --format '{{.State.ExitCode}}'
```

**Fix:**

```bash
# Remove stale KRaft metadata and reinitialize
docker compose down kafka
docker volume rm fraud-intelligence-platform_kafka-data
docker compose up -d kafka

# If cluster ID mismatch
docker exec kafka kafka-storage.sh random-uuid  # Generate new ID
docker exec kafka kafka-storage.sh format \
  -t <new-uuid> \
  -c /etc/kafka/kraft/server.properties
```

**Prevention:** Never manually edit files in the Kafka data volume. Always use `make clean-data` for a full reset.

---

### Topic Creation Fails

!!! failure "Symptoms"
    - `TopicExistsException` or `InvalidReplicationFactorException`
    - Services report "topic not found" despite init scripts running

**Diagnosis:**

```bash
# List existing topics
docker exec kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

# Describe specific topic
docker exec kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic transactions
```

**Fix:**

```bash
# Delete and recreate topic
docker exec kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --delete --topic transactions

docker exec kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic transactions \
  --partitions 4 \
  --replication-factor 1
```

**Prevention:** Ensure `KAFKA_AUTO_CREATE_TOPICS_ENABLE=false` and use init scripts for topic creation.

---

### Consumer Lag Growing

!!! failure "Symptoms"
    - Consumer group lag increasing over time
    - Spark streaming falling behind real-time
    - Dashboard showing stale data

**Diagnosis:**

```bash
# Check consumer group details
docker exec kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group spark-fraud-detection

# Check message production rate
docker exec kafka kafka-run-class.sh kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic transactions --time -1
```

**Fix:**

1. **Reduce simulator TPS** temporarily: `curl -X PUT http://localhost:8000/api/simulator/config -d '{"tps": 10}'`
2. **Increase Spark resources** — add executor memory or parallelism
3. **Check for processing errors** in Spark logs: `docker logs spark-master 2>&1 | grep ERROR`
4. **Reset offsets** if data loss is acceptable:

```bash
docker exec kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group spark-fraud-detection \
  --reset-offsets --to-latest \
  --topic transactions --execute
```

---

### Messages Not Appearing in Topic

!!! failure "Symptoms"
    - Producer reports success but consumer gets no messages
    - Console consumer shows empty topic

**Diagnosis:**

```bash
# Verify messages are being produced
docker exec kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic transactions \
  --from-beginning --max-messages 5

# Check topic configuration
docker exec kafka kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --describe --entity-type topics \
  --entity-name transactions
```

**Fix:**

- Verify the producer is targeting the correct topic name
- Check `retention.ms` — messages may be expiring before consumption
- Ensure the serialization format matches between producer and consumer (JSON/Avro)

---

## Spark Issues

### Streaming Job Fails to Start

!!! failure "Symptoms"
    - Spark application exits with `AnalysisException`
    - Missing Iceberg catalog or table errors
    - Kafka connection refused

**Diagnosis:**

```bash
docker logs spark-master 2>&1 | grep -E "(ERROR|Exception|WARN)" | tail -30
# Check Spark UI for application status
curl -s http://localhost:4040/api/v1/applications | jq .
```

**Fix:**

```bash
# Ensure Kafka is fully ready before Spark
docker compose restart spark-master

# Verify Iceberg catalog is accessible
docker exec spark-master spark-sql -e "SHOW NAMESPACES IN fraud_catalog"

# Check Kafka connectivity from Spark container
docker exec spark-master nc -zv kafka 9092
```

---

### OutOfMemoryError

!!! failure "Symptoms"
    - `java.lang.OutOfMemoryError: Java heap space`
    - Container killed by Docker OOM killer
    - `Exited (137)` status code

**Diagnosis:**

```bash
docker inspect spark-master --format '{{.State.OOMKilled}}'
docker stats spark-master --no-stream
```

**Fix:**

```bash
# Increase memory allocation in docker-compose.override.yml
cat > docker-compose.override.yml << 'EOF'
services:
  spark-master:
    environment:
      - SPARK_DRIVER_MEMORY=4g
    deploy:
      resources:
        limits:
          memory: 6g
EOF

docker compose up -d spark-master
```

Also consider reducing `spark.sql.shuffle.partitions` to `4` for local development.

---

### Checkpoint Corruption

!!! failure "Symptoms"
    - `StreamingQueryException: Failed to read checkpoint`
    - Streaming query won't restart after crash

**Diagnosis:**

```bash
# Check checkpoint directory
docker exec spark-master ls -la /opt/spark/checkpoints/

# Look for incomplete files
docker exec spark-master find /opt/spark/checkpoints -name "*.tmp"
```

**Fix:**

```bash
# Clear checkpoints (will reprocess from latest Kafka offsets)
docker exec spark-master rm -rf /opt/spark/checkpoints/fraud-detection/*
docker compose restart spark-master
```

!!! warning
    Clearing checkpoints means reprocessing. Use Iceberg deduplication (`MERGE`) to prevent duplicate records.

---

### Iceberg Write Failures

!!! failure "Symptoms"
    - `CommitFailedException` or `ValidationException`
    - Concurrent writes conflicting
    - MinIO connectivity errors during commit

**Diagnosis:**

```bash
docker logs spark-master 2>&1 | grep -i iceberg | tail -20
# Check MinIO connectivity
docker exec spark-master curl -s http://minio:9000/minio/health/live
```

**Fix:**

- Retry the write — Iceberg handles optimistic concurrency
- If persistent, check MinIO storage: `docker exec minio mc admin info local`
- Run table repair: `docker exec spark-master spark-sql -e "CALL fraud_catalog.system.rewrite_data_files('fraud_db.transactions')"`

---

## Docker Issues

### Container OOM Killed

!!! failure "Symptoms"
    - Container exits with code `137`
    - `docker inspect` shows `OOMKilled: true`

**Diagnosis:**

```bash
docker inspect <container> --format '{{.State.OOMKilled}}'
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

**Fix:**

Increase Docker Desktop memory allocation to at least 12GB (16GB recommended). On macOS: Docker Desktop → Settings → Resources → Memory.

---

### Port Already in Use

!!! failure "Symptoms"
    - `Bind for 0.0.0.0:8000 failed: port is already allocated`

**Diagnosis:**

```bash
lsof -i :8000
# or
netstat -tulpn | grep 8000
```

**Fix:**

```bash
# Kill the process using the port
kill -9 $(lsof -t -i :8000)

# Or change the port in .env
echo "BACKEND_PORT=8100" >> .env
docker compose up -d
```

---

### Volume Permission Errors

!!! failure "Symptoms"
    - `Permission denied` when writing to mounted volumes
    - Common with MinIO and Kafka on Linux

**Fix:**

```bash
# Fix ownership on Linux
sudo chown -R 1000:1000 ./data/kafka
sudo chown -R 1000:1000 ./data/minio

# Or run containers with matching UID
# In docker-compose.yml, add:
# user: "${UID}:${GID}"
```

---

### Apple Silicon Image Compatibility

!!! failure "Symptoms"
    - `exec format error` or `platform mismatch` warnings
    - Slow performance due to emulation

**Fix:**

```bash
# Build images for ARM64 natively
DOCKER_DEFAULT_PLATFORM=linux/arm64 docker compose build

# Or use multi-platform images in Dockerfile
FROM --platform=$TARGETPLATFORM python:3.11-slim
```

---

## MinIO Issues

### Bucket Not Accessible

**Diagnosis:**

```bash
docker exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker exec minio mc ls local/
docker exec minio mc admin info local
```

**Fix:**

```bash
# Recreate bucket
docker exec minio mc mb local/fraud-data --ignore-existing
docker exec minio mc policy set public local/fraud-data
```

### S3A Connection Errors from Spark

**Fix:** Verify `fs.s3a.endpoint`, `fs.s3a.access.key`, and `fs.s3a.secret.key` in Spark configuration match MinIO credentials. Ensure `fs.s3a.path.style.access=true` is set.

### Storage Full

```bash
docker exec minio mc admin info local  # Check disk usage
docker exec minio mc rm --recursive --force local/fraud-data/old-snapshots/
make iceberg-expire-snapshots
make iceberg-clean-orphans
```

---

## Airflow Issues

### DAG Not Appearing

**Diagnosis:**

```bash
docker exec airflow-scheduler airflow dags list
docker exec airflow-scheduler python -c "import ast; ast.parse(open('/opt/airflow/dags/my_dag.py').read())"
docker logs airflow-scheduler 2>&1 | grep -i "broken\|error\|import"
```

**Fix:** Check for Python syntax errors, missing imports, or DAG file not in the `dags/` directory. Airflow scans every 30s by default.

### Task Stuck in Queued

```bash
docker exec airflow-scheduler airflow tasks clear <dag_id> -t <task_id> -y
docker compose restart airflow-worker
```

---

## Frontend / Backend Issues

### WebSocket Disconnecting

**Diagnosis:** Check browser console for WebSocket close codes. Code `1006` indicates abnormal closure.

**Fix:**

- Verify backend is running: `curl http://localhost:8000/api/health`
- Check for proxy/firewall interference
- Increase `WS_PING_INTERVAL` if timeout-related

### CORS Errors

**Fix:** Ensure `CORS_ORIGINS=http://localhost:3000` is set in the backend environment. Restart the backend after changes.

### Ollama Model Not Loaded

```bash
# Check loaded models
curl -s http://localhost:11434/api/tags | jq .

# Pull the required model
docker exec ollama ollama pull llama3.2:3b

# Verify
docker exec ollama ollama list
```
