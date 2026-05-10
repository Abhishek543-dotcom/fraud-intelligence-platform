# Performance Tuning

Optimization guide for running the Fraud Intelligence Platform on resource-constrained environments (16GB RAM target).

---

## Memory Optimization

!!! warning "Critical for Local Development"
    The full platform can consume 12-16 GB of RAM. Careful memory allocation is essential to prevent OOM kills and swapping.

### Service Memory Allocation

| Service | Current Allocation | Minimum | Recommended (16GB) | Maximum |
|---------|-------------------|---------|---------------------|---------|
| Kafka (KRaft) | 1.5 GB | 512 MB | 1 GB | 2 GB |
| Spark Master | 2 GB | 1 GB | 2 GB | 4 GB |
| Spark (Driver + Executor) | 3 GB | 1.5 GB | 2.5 GB | 6 GB |
| MinIO | 512 MB | 256 MB | 512 MB | 1 GB |
| Backend API | 512 MB | 256 MB | 512 MB | 1 GB |
| Frontend | 256 MB | 128 MB | 256 MB | 512 MB |
| ML Service | 1 GB | 512 MB | 1 GB | 2 GB |
| Ollama (LLM) | 4 GB | 2 GB | 3 GB | 8 GB |
| Airflow (all components) | 1.5 GB | 768 MB | 1 GB | 2 GB |
| Redis (Feature Store) | 256 MB | 128 MB | 256 MB | 512 MB |
| **Total** | **~15 GB** | **~7 GB** | **~12 GB** | **~27 GB** |

### Memory Profiles

=== "Minimal (8 GB)"

    ```yaml
    # docker-compose.override.yml
    services:
      kafka:
        environment:
          KAFKA_HEAP_OPTS: "-Xmx512m -Xms256m"
      spark-master:
        environment:
          SPARK_DRIVER_MEMORY: "1g"
          SPARK_EXECUTOR_MEMORY: "1g"
      ml-service:
        deploy:
          resources:
            limits:
              memory: 512m
    # Don't start Ollama or monitoring
    ```

=== "Standard (16 GB)"

    ```yaml
    # docker-compose.override.yml
    services:
      kafka:
        environment:
          KAFKA_HEAP_OPTS: "-Xmx1g -Xms512m"
      spark-master:
        environment:
          SPARK_DRIVER_MEMORY: "2g"
          SPARK_EXECUTOR_MEMORY: "2g"
      ollama:
        deploy:
          resources:
            limits:
              memory: 4g
    ```

=== "High Performance (32 GB)"

    ```yaml
    # docker-compose.override.yml
    services:
      kafka:
        environment:
          KAFKA_HEAP_OPTS: "-Xmx2g -Xms1g"
      spark-master:
        environment:
          SPARK_DRIVER_MEMORY: "4g"
          SPARK_EXECUTOR_MEMORY: "4g"
      ollama:
        deploy:
          resources:
            limits:
              memory: 8g
    ```

---

## Kafka Tuning

### Heap Configuration

```bash
# Environment variable in docker-compose.yml
KAFKA_HEAP_OPTS: "-Xmx1g -Xms512m"

# For high throughput
KAFKA_HEAP_OPTS: "-Xmx2g -Xms1g"
```

### Producer Tuning

| Parameter | Default | Local Dev | High Throughput | Description |
|-----------|---------|-----------|-----------------|-------------|
| `batch.size` | 16384 | 32768 | 65536 | Bytes per batch |
| `linger.ms` | 0 | 5 | 20 | Wait time to fill batch |
| `compression.type` | none | snappy | lz4 | Compression algorithm |
| `buffer.memory` | 32 MB | 32 MB | 64 MB | Total producer buffer |
| `acks` | all | all | all | Durability guarantee |

### Compression Comparison

| Algorithm | CPU Usage | Compression Ratio | Throughput Impact |
|-----------|-----------|-------------------|-------------------|
| none | 0% | 1.0x | Baseline |
| snappy | Low | 1.5-2x | -5% latency, +30% throughput |
| lz4 | Low | 1.5-2.5x | -3% latency, +35% throughput |
| zstd | Medium | 2-3x | -10% latency, +50% throughput |
| gzip | High | 2.5-3.5x | -20% latency, +40% throughput |

!!! tip "Recommendation"
    Use **lz4** for local development — best balance of CPU and compression. Use **zstd** for production where throughput matters more than latency.

### Log Segment Configuration

```properties
# Smaller segments for faster cleanup in dev
log.segment.bytes=104857600     # 100 MB (default: 1 GB)
log.retention.hours=24          # 1 day (default: 168 hours)
log.retention.bytes=1073741824  # 1 GB total per partition
log.cleanup.policy=delete
```

### Partition Count Impact

| Partitions | Parallelism | Memory Overhead | Recommended For |
|------------|-------------|-----------------|-----------------|
| 1 | Minimal | ~10 MB | Testing only |
| 4 | Good for local | ~40 MB | **Local development** |
| 12 | Production-like | ~120 MB | Staging |
| 32+ | High throughput | ~320 MB+ | Production |

---

## Spark Tuning

### Memory Configuration

```python
# spark-defaults.conf or environment variables
spark.driver.memory=2g
spark.executor.memory=2g
spark.executor.memoryOverhead=512m
spark.memory.fraction=0.6
spark.memory.storageFraction=0.5
```

### Shuffle Partitions

```python
# Critical for local development — default 200 is way too high
spark.sql.shuffle.partitions=4       # Local dev
spark.sql.shuffle.partitions=12      # Staging
spark.sql.shuffle.partitions=200     # Production
```

!!! danger "Common Mistake"
    Leaving `spark.sql.shuffle.partitions` at the default `200` on a local machine causes excessive overhead with tiny partitions. Set it to `4` for local development.

### Adaptive Query Execution

```python
# Enable AQE (recommended)
spark.sql.adaptive.enabled=true
spark.sql.adaptive.coalescePartitions.enabled=true
spark.sql.adaptive.skewJoin.enabled=true
spark.sql.adaptive.coalescePartitions.minPartitionSize=1m
```

### Streaming Configuration

| Parameter | Local Dev | Production | Description |
|-----------|-----------|------------|-------------|
| `trigger` | `processingTime='5 seconds'` | `processingTime='1 second'` | Micro-batch interval |
| `maxOffsetsPerTrigger` | 1000 | 10000 | Max records per batch |
| `checkpointLocation` | `/opt/spark/checkpoints/` | `s3a://checkpoints/` | Checkpoint storage |
| `minPartitions` | 4 | Matches Kafka partitions | Read parallelism |

### GC Tuning for Spark

```bash
SPARK_DRIVER_EXTRA_JAVA_OPTIONS: >
  -XX:+UseG1GC
  -XX:G1HeapRegionSize=16m
  -XX:InitiatingHeapOccupancyPercent=35
  -XX:+ParallelRefProcEnabled
  -XX:+ExitOnOutOfMemoryError
```

---

## MinIO Tuning

### Single Drive Mode Optimization

```bash
# Environment variables
MINIO_CACHE: "on"
MINIO_CACHE_DRIVES: "/cache"
MINIO_CACHE_QUOTA: 80      # Use 80% of cache drive
MINIO_CACHE_AFTER: 1        # Cache after 1 access
MINIO_CACHE_WATERMARK_LOW: 70
MINIO_CACHE_WATERMARK_HIGH: 90
```

### Read/Write Buffer Sizes

```bash
# For Iceberg workloads (large sequential reads/writes)
MINIO_API_READ_DEADLINE: "30s"
MINIO_API_WRITE_DEADLINE: "30s"
```

---

## Docker Tuning

### Docker Desktop Settings

| Setting | Minimum | Recommended | Notes |
|---------|---------|-------------|-------|
| CPUs | 4 | 6-8 | More CPUs help Spark parallelism |
| Memory | 8 GB | 12-16 GB | See memory allocation table above |
| Swap | 1 GB | 2 GB | Safety net for memory spikes |
| Disk | 32 GB | 64 GB | Iceberg data, Docker images |

### BuildKit Optimization

```bash
# Enable BuildKit for faster builds
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Build with caching
docker compose build --parallel

# Use mounted cache for pip/npm
# In Dockerfile:
# RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
```

### Layer Caching Strategy

```dockerfile
# Order from least-changed to most-changed
COPY requirements.txt .
RUN pip install -r requirements.txt    # Cached if requirements unchanged
COPY src/ src/                          # Only invalidates from here down
```

---

## JVM Services Tuning

### Container-Aware JVM Settings

```bash
# Use percentage-based memory (respects container limits)
JAVA_OPTS: >
  -XX:MaxRAMPercentage=75.0
  -XX:InitialRAMPercentage=50.0
  -XX:+UseContainerSupport
  -XX:+UseG1GC
  -XX:MaxGCPauseMillis=200
```

!!! info "Container-Aware JVM"
    JDK 11+ automatically detects container memory limits. Use `-XX:MaxRAMPercentage` instead of fixed `-Xmx` values to adapt to different environments.

---

## Python Services Tuning

### Uvicorn Configuration

```python
# Backend API
UVICORN_WORKERS=2          # 2 for local, CPU_COUNT for production
UVICORN_LOOP=uvloop        # Faster event loop
UVICORN_HTTP=httptools     # Faster HTTP parsing
UVICORN_BACKLOG=2048
```

### Connection Pool Sizes

```python
# Database connections
DB_POOL_SIZE=5             # Local dev
DB_POOL_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30

# Redis connections
REDIS_POOL_SIZE=10
REDIS_POOL_TIMEOUT=20
```

---

## Benchmarking

### Transaction Throughput

```bash
# Run throughput benchmark
make benchmark

# Custom TPS target
docker exec transaction-simulator python benchmark.py \
  --target-tps 100 \
  --duration 300 \
  --report-interval 10
```

### End-to-End Latency Measurement

```bash
# Measure time from transaction generation to fraud alert
curl -X POST http://localhost:8000/api/benchmark/latency \
  -H "Content-Type: application/json" \
  -d '{"num_transactions": 100, "include_fraud": true}'
```

### Performance Targets

| Metric | Local Dev | Staging | Production |
|--------|-----------|---------|------------|
| Transaction Throughput | 50-100 TPS | 500-1K TPS | 10K+ TPS |
| End-to-End Latency (p50) | < 5s | < 2s | < 500ms |
| End-to-End Latency (p99) | < 15s | < 5s | < 2s |
| Spark Batch Duration | < 10s | < 5s | < 2s |
| API Response Time (p50) | < 200ms | < 100ms | < 50ms |
| API Response Time (p99) | < 1s | < 500ms | < 200ms |
| Model Inference Time | < 100ms | < 50ms | < 20ms |

### Monitoring Commands

```bash
# Real-time container resource usage
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"

# Spark streaming metrics
curl -s http://localhost:4040/api/v1/applications/*/streaming/statistics | jq '.recentProgress[-1]'

# Kafka consumer throughput
docker exec kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group spark-fraud-detection \
  | awk '{sum+=$5} END {print "Total lag:", sum}'
```
