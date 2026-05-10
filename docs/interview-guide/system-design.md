# System Design Interview Guide

How to present and discuss the Fraud Intelligence Platform in system design interviews.

---

## How to Present This Project

### 5-Minute Elevator Pitch

> "I built a real-time fraud detection platform that processes financial transactions end-to-end using event-driven architecture. Transactions flow through Kafka into a Spark Structured Streaming pipeline that enriches them with features and scores them with an ML model. Results are stored in Apache Iceberg tables on a data lakehouse, served via a FastAPI backend with a React dashboard, and supported by an AI Investigation Copilot powered by a local LLM. The entire system runs in Docker Compose with Airflow orchestrating batch jobs, and it's designed to demonstrate production patterns like exactly-once processing, model hot-reloading, event replay, and graceful degradation."

### Whiteboard Diagram Sequence

Draw the architecture in this order to tell a coherent story:

```
Step 1: Start with the data flow
  [Transaction Simulator] → [Kafka] → [Spark Streaming] → [Iceberg/MinIO]

Step 2: Add the serving layer
  [Iceberg/MinIO] → [Backend API] → [React Dashboard]

Step 3: Add ML pipeline
  [Feature Store] ← [Spark] → [ML Service] → [Fraud Alerts]

Step 4: Add AI layer
  [Ollama LLM] → [Investigation Copilot] → [Dashboard]

Step 5: Add orchestration
  [Airflow] → manages batch jobs, retraining, data quality

Step 6: Add feedback loop
  [Analyst Feedback] → [Label Store] → [Model Retraining]
```

### Key Talking Points Per Component

| Component | What to Emphasize | Buzzwords That Resonate |
|-----------|-------------------|------------------------|
| Kafka | Event sourcing, decoupling, replay | Exactly-once, partitioning, backpressure |
| Spark Streaming | Micro-batch vs continuous, checkpointing | Structured Streaming, watermarking |
| Iceberg | Table format advantages, time travel | ACID transactions, schema evolution |
| ML Service | Online inference, model versioning | Feature store, A/B testing, drift detection |
| Airflow | DAG orchestration, scheduling | Idempotent tasks, backfill, SLA monitoring |
| Copilot | RAG pattern, local LLM | LLM integration, prompt engineering |

---

## Common Interview Questions

### 1. "How does your system handle exactly-once semantics?"

**Concise answer:** We achieve effectively exactly-once through three mechanisms: Kafka idempotent producers (`enable.idempotence=true`), Spark Structured Streaming checkpointing (offset tracking committed atomically with output), and Iceberg MERGE deduplication on transaction_id.

**Deeper discussion:**

- True exactly-once is impossible in distributed systems (FLP impossibility); we achieve "effectively once"
- Spark commits offsets and output atomically via write-ahead log + checkpoint
- If Spark crashes mid-batch, it replays from the last committed checkpoint
- Iceberg's optimistic concurrency control prevents duplicate writes on retry
- End-to-end: producer dedup → checkpoint → output dedup = no duplicates visible to consumers

**Tradeoffs:**

- Idempotent producers add ~5% latency
- Checkpointing adds disk I/O overhead
- MERGE dedup requires a primary key and costs more than APPEND

---

### 2. "What happens if Kafka goes down?"

**Concise answer:** Producers buffer locally and retry. Spark checkpoints preserve consumer offsets. On recovery, processing resumes from the last committed offset with no data loss.

**Deeper discussion:**

- KRaft mode (no ZooKeeper) means the broker itself holds metadata — single point of failure in our 1-broker setup
- In production, you'd run 3+ brokers across availability zones
- Spark's `failOnDataLoss=false` setting controls behavior when offsets are out of range
- The backend API degrades gracefully — serves cached data from Iceberg while Kafka is down

---

### 3. "How do you handle late-arriving events?"

**Concise answer:** Spark Structured Streaming uses watermarking with a configurable threshold (e.g., 10 minutes). Events within the watermark window update aggregations; events beyond it are dropped for windowed operations but still persisted to Iceberg for historical analysis.

**Deeper discussion:**

- Watermark = max event time seen - threshold
- Tradeoff: longer watermark = more accurate but higher memory/latency
- For fraud detection, timeliness matters more than perfect completeness
- Late events are still written to Iceberg (append-only), just excluded from real-time aggregations
- Batch reprocessing via Airflow DAG catches anything missed in streaming

---

### 4. "How would you scale this to 100K TPS?"

**Concise answer:** Horizontally scale each layer independently: 20+ Kafka partitions across 5+ brokers, scale Spark executors to match, use object storage (S3) for Iceberg, and add caching (Redis) and read replicas for the API layer.

**Deeper discussion:**

| Layer | Current (Local) | At 100K TPS |
|-------|----------------|-------------|
| Kafka | 1 broker, 4 partitions | 5+ brokers, 32 partitions |
| Spark | 1 executor, 2g memory | 20+ executors, auto-scaling |
| Storage | MinIO (single node) | S3 / ADLS / GCS |
| API | 1 instance | 5+ behind load balancer |
| ML | 1 instance | 3+ with GPU inference |
| Cache | Redis (single) | Redis Cluster |

---

### 5. "What's your model retraining strategy?"

**Concise answer:** Weekly automated retraining via Airflow DAG using the latest 30 days of labeled data from Iceberg. New models are validated against a holdout set, registered in the model registry, and deployed via hot-reload if metrics improve. Shadow mode compares new vs production before promotion.

---

### 6. "How do you prevent false positives?"

**Concise answer:** Multi-layered approach — threshold tuning based on precision-recall curves, human feedback loop for label correction, rule-based overrides for known-good patterns, and analyst review workflow that feeds back into training data.

---

### 7. "How would you add a new fraud detection rule?"

**Concise answer:** Rules are configuration-driven — add a new rule definition to the rule engine config, restart the backend (or hot-reload via API). The rule evaluates alongside the ML model, and both signals contribute to the final fraud score through an ensemble approach.

---

### 8. "What's your data retention strategy?"

**Concise answer:** Hot data (30 days) in Iceberg with full features, warm data (1 year) with aggregated features, cold data (7 years for compliance) in compressed Parquet on object storage. Iceberg snapshot expiry and compaction run daily via Airflow.

---

### 9. "How do you ensure data consistency across the pipeline?"

**Concise answer:** Event sourcing with Kafka as the source of truth. All derived state (Iceberg tables, feature store, alerts) can be reconstructed by replaying events. Iceberg provides ACID transactions for writes, and the replay engine validates consistency.

---

### 10. "What would you change for a multi-region deployment?"

**Concise answer:** Kafka MirrorMaker 2 for cross-region topic replication, Iceberg on S3 with cross-region replication, active-passive for writes with active-active for reads, and region-local ML inference for latency.

---

## Capacity Estimation

### Transaction Volume

```
Daily transactions:     100K TPS × 86,400 sec = 8.64 billion/day
Average event size:     ~500 bytes (JSON)
Daily raw data:         8.64B × 500B = 4.32 TB/day
With compression (4x):  ~1.08 TB/day
Monthly storage:        ~32.4 TB/month
```

### Iceberg Storage (with Time Travel)

```
Base data:              1.08 TB/day
Snapshots (7 days):     1.08 × 7 = 7.56 TB
Metadata overhead:      ~5% = 0.38 TB
Total hot storage:      ~8 TB
Annual storage (warm):  ~395 TB (compressed, no time travel)
```

### Kafka Throughput

```
Messages/sec:           100,000
Message size:           500 bytes
Throughput:             50 MB/s
With replication (3x):  150 MB/s cluster throughput
Retention (24h):        50 MB/s × 86,400 = 4.32 TB
Partitions needed:      100K / 5K per partition = ~20 partitions
```

### Network Bandwidth

```
Kafka ingress:          50 MB/s
Kafka → Spark:          50 MB/s
Spark → Iceberg:        25 MB/s (after aggregation)
API serving:            ~10 MB/s (read heavy)
Total cluster:          ~150 MB/s = 1.2 Gbps
```
