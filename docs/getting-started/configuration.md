# Configuration Reference

All platform configuration is managed through environment variables defined in the `.env` file at the project root. This page documents every variable, its default, and which services consume it.

## Environment File

```bash
# Copy the example environment file
cp .env.example .env

# Edit as needed
vim .env
```

!!! warning "Never commit secrets"
    The `.env` file is in `.gitignore`. The `.env.example` file contains safe defaults for local development. For production deployments, use a secrets manager.

## Kafka Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BROKER` | `kafka:29092` | Internal broker address for inter-service communication |
| `KAFKA_EXTERNAL_BROKER` | `localhost:9092` | External broker address for host-machine access |
| `KAFKA_KRAFT_CLUSTER_ID` | `MkU3OEVBNTcwNTJENDM2Qk` | KRaft cluster identifier (base64-encoded UUID) |
| `KAFKA_HEAP_OPTS` | `-Xmx512m -Xms512m` | JVM heap for Kafka broker |
| `KAFKA_NUM_PARTITIONS` | `6` | Default partition count for auto-created topics |
| `KAFKA_DEFAULT_REPLICATION_FACTOR` | `1` | Replication factor (1 for single-broker local) |
| `KAFKA_LOG_RETENTION_HOURS` | `168` | Topic log retention (7 days) |
| `KAFKA_LOG_SEGMENT_BYTES` | `1073741824` | Log segment size (1 GB) |

!!! tip "KRaft cluster ID"
    The cluster ID must be a valid base64 string. Generate a new one with:
    ```bash
    kafka-storage random-uuid | base64
    ```

## MinIO (Object Storage)

| Variable | Default | Description |
|----------|---------|-------------|
| `MINIO_ENDPOINT` | `http://minio:9000` | Internal MinIO API endpoint |
| `MINIO_EXTERNAL_ENDPOINT` | `http://localhost:9000` | External MinIO API endpoint |
| `MINIO_CONSOLE_PORT` | `9001` | MinIO web console port |
| `MINIO_ROOT_USER` | `minioadmin` | Root admin username |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | Root admin password |
| `MINIO_ACCESS_KEY` | `minioadmin` | S3-compatible access key |
| `MINIO_SECRET_KEY` | `minioadmin` | S3-compatible secret key |
| `MINIO_REGION` | `us-east-1` | S3 region for bucket operations |

## PostgreSQL

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `fraud_admin` | Database superuser |
| `POSTGRES_PASSWORD` | `fraud_password` | Database password |
| `POSTGRES_DB` | `fraud_platform` | Primary database name |
| `POSTGRES_HOST` | `postgres` | Internal hostname |
| `POSTGRES_PORT` | `5432` | Database port |

!!! info "Shared by multiple services"
    PostgreSQL is used by both the Backend API (application data) and Airflow (metadata store). Both services connect using the same credentials.

## Nessie Catalog

| Variable | Default | Description |
|----------|---------|-------------|
| `NESSIE_URI` | `http://nessie:19120/api/v1` | Nessie REST catalog API |
| `NESSIE_EXTERNAL_URI` | `http://localhost:19120` | External Nessie UI address |
| `NESSIE_DEFAULT_BRANCH` | `main` | Default Git-like branch for catalog |

## Apache Iceberg

| Variable | Default | Description |
|----------|---------|-------------|
| `ICEBERG_WAREHOUSE` | `s3a://iceberg-warehouse/` | Warehouse root path in MinIO |
| `ICEBERG_CATALOG_TYPE` | `nessie` | Catalog implementation (nessie, hive, rest) |
| `ICEBERG_DEFAULT_FILE_FORMAT` | `parquet` | Data file format |

## Apache Airflow

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRFLOW_UID` | `50000` | Unix UID for Airflow process |
| `AIRFLOW__CORE__EXECUTOR` | `LocalExecutor` | Task executor type |
| `AIRFLOW__CORE__LOAD_EXAMPLES` | `false` | Disable example DAGs |
| `AIRFLOW__CORE__DAGS_FOLDER` | `/opt/airflow/dags` | DAG file location |
| `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` | `postgresql+psycopg2://fraud_admin:fraud_password@postgres:5432/fraud_platform` | Metadata DB connection |
| `AIRFLOW__WEBSERVER__WEB_SERVER_PORT` | `8082` | Webserver port |
| `AIRFLOW__WEBSERVER__RBAC` | `true` | Enable role-based access control |
| `AIRFLOW__SCHEDULER__MIN_FILE_PROCESS_INTERVAL` | `30` | DAG file scan interval (seconds) |
| `AIRFLOW__LOGGING__LOGGING_LEVEL` | `INFO` | Log verbosity |

## Apache Spark

| Variable | Default | Description |
|----------|---------|-------------|
| `SPARK_MASTER_URL` | `spark://spark-master:7077` | Spark master connection URL |
| `SPARK_MASTER_WEBUI_PORT` | `8080` | Spark master dashboard port |
| `SPARK_WORKER_WEBUI_PORT` | `8081` | Spark worker dashboard port |
| `SPARK_WORKER_MEMORY` | `2g` | Memory allocated to Spark worker |
| `SPARK_WORKER_CORES` | `2` | CPU cores for Spark worker |
| `SPARK_EXECUTOR_MEMORY` | `1g` | Per-executor memory |
| `SPARK_DRIVER_MEMORY` | `1g` | Spark driver memory |
| `SPARK_SQL_SHUFFLE_PARTITIONS` | `4` | Shuffle partitions (low for local) |
| `SPARK_STREAMING_TRIGGER_INTERVAL` | `10 seconds` | Micro-batch interval |

!!! warning "Memory-constrained environment"
    With 8 GB Docker memory shared across 16 services, Spark gets 2 GB total. Do not increase `SPARK_WORKER_MEMORY` beyond `2g` without reducing other service allocations. See the [Performance Tuning](../runbook/performance-tuning.md) guide.

## Ollama (Local LLM)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://ollama:11434` | Internal Ollama API endpoint |
| `OLLAMA_EXTERNAL_HOST` | `http://localhost:11434` | External Ollama API endpoint |
| `OLLAMA_MODEL` | `phi3:mini` | LLM model for investigation copilot |
| `OLLAMA_NUM_CTX` | `4096` | Context window size (tokens) |
| `OLLAMA_MEMORY_LIMIT` | `2g` | Maximum memory for model inference |

## ChromaDB (Vector Store)

| Variable | Default | Description |
|----------|---------|-------------|
| `CHROMA_HOST` | `chromadb` | Internal ChromaDB hostname |
| `CHROMA_PORT` | `8100` | ChromaDB API port |
| `CHROMA_PERSIST_DIRECTORY` | `/chroma/data` | Persistent storage path |
| `CHROMA_COLLECTION_NAME` | `fraud_alerts` | Default vector collection |

## Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | Full Redis connection URL |
| `REDIS_HOST` | `redis` | Internal Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database number |
| `REDIS_CACHE_TTL` | `300` | Default cache TTL (seconds) |

## Backend API (FastAPI)

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_HOST` | `0.0.0.0` | Bind address |
| `BACKEND_PORT` | `8000` | API server port |
| `BACKEND_WORKERS` | `2` | Uvicorn worker count |
| `BACKEND_LOG_LEVEL` | `info` | Logging verbosity |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins (comma-separated) |
| `JWT_SECRET_KEY` | `dev-secret-key-change-in-prod` | JWT signing key |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXPIRATION_MINUTES` | `60` | Token expiration |

## Frontend (React + Vite)

| Variable | Default | Description |
|----------|---------|-------------|
| `FRONTEND_PORT` | `3000` | Dev server port |
| `VITE_API_URL` | `http://localhost:8000` | Backend API base URL |
| `VITE_WS_URL` | `ws://localhost:8000/ws/alerts` | WebSocket endpoint |
| `VITE_GRAFANA_URL` | `http://localhost:3001` | Embedded Grafana URL |

!!! info "Vite environment variables"
    Variables prefixed with `VITE_` are embedded at build time. Changes require rebuilding the frontend:
    ```bash
    make build-frontend
    ```

## Monitoring (Prometheus + Grafana)

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_PORT` | `9090` | Prometheus UI port |
| `PROMETHEUS_RETENTION` | `15d` | Metrics retention period |
| `GRAFANA_PORT` | `3001` | Grafana dashboard port |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin username |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana admin password |
| `GRAFANA_PROVISIONING` | `/etc/grafana/provisioning` | Auto-provisioned dashboards path |

## Transaction Simulator

| Variable | Default | Description |
|----------|---------|-------------|
| `SIMULATOR_TPS` | `100` | Transactions per second |
| `SIMULATOR_FRAUD_RATE` | `0.02` | Fraud injection rate (2%) |
| `SIMULATOR_PATTERNS` | `velocity,geo_anomaly,amount_spike,card_testing,account_takeover` | Active fraud patterns |

## Docker Compose Profiles

The platform uses Docker Compose profiles to control which services start. Configure profiles in the `COMPOSE_PROFILES` variable or use Makefile targets.

| Profile | Services Included | Memory Usage |
|---------|-------------------|-------------|
| **core** | Kafka, Spark (master+worker), MinIO, Nessie, Airflow (webserver+scheduler), PostgreSQL, Redis, Backend API, Transaction Simulator | ~5.5 GB |
| **ml** | ML inference service (XGBoost + Isolation Forest + Random Forest) | ~512 MB |
| **monitoring** | Prometheus, Grafana | ~512 MB |
| **frontend** | React dashboard (Vite production build) | ~128 MB |
| **ai** | Ollama (phi3:mini), ChromaDB | ~2.5 GB |

### Profile Combinations

=== "Development (Core Only)"

    ```bash
    COMPOSE_PROFILES=core docker compose up -d
    # Or: make up-core
    # Memory: ~5.5 GB
    ```

=== "Core + ML"

    ```bash
    COMPOSE_PROFILES=core,ml docker compose up -d
    # Or: make up-ml
    # Memory: ~6 GB
    ```

=== "Full Platform"

    ```bash
    COMPOSE_PROFILES=core,ml,monitoring,frontend,ai docker compose up -d
    # Or: make up
    # Memory: ~8 GB
    ```

!!! warning "AI profile memory impact"
    The `ai` profile loads the Ollama LLM into memory (~2.5 GB). If running on 8 GB Docker allocation, only combine `ai` with `core` — skip `monitoring` and `frontend` to stay within limits, or increase Docker memory to 10 GB.

## Overriding Configuration

### Per-Service Override

Create a `docker-compose.override.yml` for local customizations:

```yaml
# docker-compose.override.yml
services:
  backend:
    environment:
      - BACKEND_LOG_LEVEL=debug
      - BACKEND_WORKERS=1
  spark-worker:
    environment:
      - SPARK_WORKER_MEMORY=3g
```

### Command-Line Override

```bash
# Override a single variable
SIMULATOR_TPS=500 make up

# Override multiple variables
SPARK_WORKER_MEMORY=3g KAFKA_HEAP_OPTS="-Xmx1g -Xms1g" make up
```

## Next Steps

- [Architecture Overview](../architecture/overview.md) — Understand how components interact
- [Component Deep Dives](../components/kafka.md) — Detailed per-service documentation
- [Operations Runbook](../runbook/operations.md) — Day-to-day management
