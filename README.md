# 🏦 AI-Powered Real-Time Fraud & Risk Intelligence Platform

[![Documentation](https://img.shields.io/badge/docs-live-blue?style=flat-square)](https://abhishek543-dotcom.github.io/fraud-intelligence-platform/)
[![Docker Compose](https://img.shields.io/badge/docker%20compose-up-green?style=flat-square&logo=docker)](docker-compose.yml)
[![License](https://img.shields.io/badge/license-MIT-purple?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-blue?style=flat-square&logo=python)](https://python.org)
[![Spark](https://img.shields.io/badge/spark-3.5-orange?style=flat-square&logo=apachespark)](https://spark.apache.org)

A production-grade, cloud-native fraud detection platform running **entirely locally** on Docker Desktop. Demonstrates end-to-end real-time streaming, ML inference, GenAI investigation, and observability — architected like systems at Stripe, Uber, and JPMorgan.

---

## Architecture

```
Transaction Simulator (100 TPS)
        │
        ▼
┌─────────────────────┐
│  Apache Kafka       │  7 topics, KRaft mode (no Zookeeper)
│  (Event Backbone)   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐     ┌──────────────────┐
│  Spark Structured   │────▶│  ML Ensemble     │
│  Streaming          │     │  XGBoost + IF    │
│  (Feature Engine)   │     └────────┬─────────┘
└────────┬────────────┘              │
         │                           ▼
         ▼                  ┌──────────────────┐
┌─────────────────────┐     │  Fraud Alerts    │
│  Apache Iceberg     │     │  → WebSocket     │
│  Bronze/Silver/Gold │     │  → Dashboard     │
│  (MinIO + Nessie)   │     └──────────────────┘
└─────────────────────┘
         │
         ▼
┌─────────────────────┐     ┌──────────────────┐
│  FastAPI Backend     │────▶│  React Dashboard │
│  REST + WebSocket    │     │  Live Alerts     │
└────────┬────────────┘     └──────────────────┘
         │
         ▼
┌─────────────────────┐
│  Ollama + ChromaDB  │
│  AI Investigation   │
│  Copilot (RAG)      │
└─────────────────────┘
```

---

## Key Features

| Feature | Implementation |
|---------|---------------|
| **Real-Time Streaming** | Kafka (KRaft) → Spark Structured Streaming with watermarks, stateful ops |
| **Medallion Lakehouse** | Apache Iceberg on MinIO with Bronze/Silver/Gold layers, time travel |
| **ML Fraud Detection** | XGBoost + Isolation Forest + Random Forest ensemble, <10ms inference |
| **10 Engineered Features** | geo_velocity, amount_zscore, rapid_tx_count, device_consistency, etc. |
| **AI Investigation Copilot** | RAG pipeline with Ollama phi3:mini + ChromaDB for NL fraud search |
| **Live Dashboard** | React + Vite with WebSocket alerts, geo heatmap, model metrics |
| **Graph Fraud Detection** | NetworkX community detection for fraud ring identification |
| **Event Replay Engine** | Time-travel based replay from Iceberg snapshots |
| **Observability** | Prometheus + Grafana + OpenTelemetry + Great Expectations |
| **Self-Healing** | Auto-restart streaming jobs with exponential backoff |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Streaming | Apache Kafka 3.7 (KRaft) |
| Processing | Apache Spark 3.5 Structured Streaming |
| Lakehouse | Apache Iceberg + Nessie Catalog |
| Object Storage | MinIO (S3-compatible) |
| ML Models | XGBoost, Isolation Forest, Random Forest |
| LLM | Ollama (phi3:mini) + LangChain |
| Vector DB | ChromaDB |
| Backend | FastAPI + WebSockets |
| Frontend | React + Vite + Tailwind + Recharts |
| Orchestration | Apache Airflow 2.8 |
| Monitoring | Prometheus + Grafana |
| Feature Store | Redis (online) + Iceberg (offline) |
| Security | JWT + RBAC + Audit Logging |
| Containers | Docker Compose (16 services) |
| Kubernetes | Docker Desktop K8s + Helm |

---

## Quick Start

### Prerequisites

- **Docker Desktop** with 8GB RAM allocated
- **Apple Silicon** (ARM64) or Intel Mac
- **make** (comes with Xcode CLI tools)

### Start the Platform

```bash
# Clone
git clone https://github.com/Abhishek543-dotcom/fraud-intelligence-platform.git
cd fraud-intelligence-platform

# Build custom images
make build

# Start core services
make up

# Initialize Kafka topics and MinIO buckets
make init

# Start everything (core + ML + monitoring + frontend + AI)
make up-all

# Check status
make ps
```

### Access Services

| Service | URL |
|---------|-----|
| **Frontend Dashboard** | http://localhost:3000 |
| **Backend API** | http://localhost:8000 |
| **API Docs (Swagger)** | http://localhost:8000/docs |
| **Spark Master UI** | http://localhost:8080 |
| **Airflow** | http://localhost:8081 |
| **MinIO Console** | http://localhost:9001 |
| **Grafana** | http://localhost:3001 |
| **Prometheus** | http://localhost:9090 |
| **Nessie Catalog** | http://localhost:19120 |

---

## Project Structure

```
fraud-intelligence-platform/
├── docker-compose.yml          # 16 services, profiles, 8GB memory budget
├── Makefile                    # 25+ operational targets
├── mkdocs.yml                  # Documentation site config
│
├── streaming/
│   ├── producers/              # AsyncIO transaction simulator
│   │   ├── generators/         # 7 fraud pattern generators
│   │   └── models/             # Pydantic transaction models
│   ├── spark-jobs/             # Spark Structured Streaming pipeline
│   ├── consumers/              # Kafka consumers
│   └── schemas/                # Avro schemas
│
├── lakehouse/
│   ├── catalog/                # Nessie + Spark-Iceberg config
│   ├── schemas/                # Bronze/Silver/Gold table definitions
│   ├── maintenance/            # Compaction, snapshot expiry
│   └── replay/                 # Event replay engine
│
├── ml/
│   ├── training/               # XGBoost, IF, RF, ensemble training
│   ├── inference/              # FastAPI model server, streaming scorer
│   └── features/               # Feature definitions and pipeline
│
├── ai-copilot/
│   ├── rag/                    # Embeddings, vector store, retriever
│   ├── chains/                 # LangChain investigation workflows
│   └── prompts/                # Prompt templates
│
├── backend/                    # FastAPI REST + WebSocket
├── frontend/                   # React + Vite + Tailwind dashboard
│
├── airflow/dags/               # 5 orchestration DAGs
├── observability/              # Prometheus, Grafana, OTEL, Great Expectations
├── security/                   # JWT, RBAC, audit logging, TLS
├── advanced/                   # Graph fraud, feature store, chaos, self-healing
│
├── infrastructure/
│   ├── docker/                 # 6 Dockerfiles
│   ├── kubernetes/             # K8s manifests + Kustomize
│   ├── helm/                   # Helm chart
│   └── scripts/                # Init, health check, deploy scripts
│
└── docs/                       # MkDocs documentation (29 pages)
```

---

## Memory Budget (8GB Docker)

| Service | Allocation |
|---------|-----------|
| Kafka (KRaft) | 512 MB |
| Spark Master | 256 MB |
| Spark Worker | 1024 MB |
| MinIO | 256 MB |
| Nessie | 256 MB |
| Airflow (web + scheduler) | 768 MB |
| PostgreSQL | 256 MB |
| FastAPI Backend | 256 MB |
| React Frontend | 128 MB |
| Prometheus | 128 MB |
| Grafana | 128 MB |
| Ollama (phi3:mini) | 2048 MB |
| ChromaDB | 256 MB |
| Simulator | 128 MB |
| Redis | 128 MB |
| **Total** | **~6.5 GB** |

---

## Makefile Targets

```bash
make help              # Show all targets
make build             # Build custom Docker images
make up                # Start core services
make up-all            # Start ALL services
make down              # Stop everything
make init              # Create Kafka topics + MinIO buckets
make ps                # Show running containers
make health            # Run health checks
make logs              # Tail core service logs
make spark-shell       # Open PySpark shell
make kafka-console     # Kafka console consumer
make test              # Run all tests
make lint              # Run linters
make clean             # Stop + remove volumes
make docs-serve        # Preview docs locally
make docs-build        # Build docs site
```

---

## Documentation

Full documentation is available at:

**[https://abhishek543-dotcom.github.io/fraud-intelligence-platform/](https://abhishek543-dotcom.github.io/fraud-intelligence-platform/)**

Includes:
- System architecture with Mermaid diagrams
- Component deep-dives (Kafka, Spark, Iceberg, ML, AI, etc.)
- Operational runbook (troubleshooting, disaster recovery, performance tuning)
- API reference (REST + WebSocket)
- Interview preparation guide (system design questions + answers)

---

## Fraud Detection Pipeline

### Fraud Patterns Generated

| Pattern | Description | Detection Method |
|---------|-------------|-----------------|
| Card Testing | Rapid small transactions at different merchants | `rapid_tx_count > 5` in 5-min window |
| Impossible Travel | Transactions in distant cities within minutes | `geo_velocity_kmh > 900` |
| Device Mismatch | New device fingerprint for known customer | `device_consistency = 0` |
| Mule Account | Multiple deposits → single large withdrawal | Graph analysis |
| Spending Spike | Transaction far above customer average | `amount_zscore > 3.0` |
| Off-Hours | Transaction during unusual hours for customer | `is_unusual_hour = 1` |
| High-Risk Merchant | Transaction at merchant with fraud history | `merchant_risk_score > 0.7` |

### ML Ensemble Scoring

```
Final Score = 0.5 × XGBoost(features)
            + 0.3 × RandomForest(features)
            + 0.2 × IsolationForest(features)

Actions:
  score > 0.85 → BLOCK transaction
  score > 0.60 → FLAG for review
  score > 0.40 → ALERT investigation team
```

---

## Production Migration Path

| Local | AWS Equivalent | Effort |
|-------|---------------|--------|
| Docker Compose | EKS (Helm chart provided) | Medium |
| Kafka (Docker) | Amazon MSK | Low |
| Spark (Docker) | EMR on EKS | Medium |
| MinIO | Amazon S3 | Low |
| Nessie | AWS Glue Catalog | Medium |
| Ollama | SageMaker / Bedrock | Medium |
| Prometheus + Grafana | CloudWatch + Managed Grafana | Low |
| PostgreSQL | Amazon RDS | Low |

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'feat: add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

See [Contributing Guide](https://abhishek543-dotcom.github.io/fraud-intelligence-platform/development/contributing/) for detailed guidelines.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built for learning, interviewing, and demonstrating enterprise-grade data engineering.**

[Documentation](https://abhishek543-dotcom.github.io/fraud-intelligence-platform/) · [Report Bug](https://github.com/Abhishek543-dotcom/fraud-intelligence-platform/issues) · [Request Feature](https://github.com/Abhishek543-dotcom/fraud-intelligence-platform/issues)

</div>
