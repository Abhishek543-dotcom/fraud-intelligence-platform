---
title: System Architecture Overview
description: High-level architecture, component inventory, network topology, data schemas, and interaction sequence diagrams
---

# System Architecture Overview

This page provides a comprehensive view of the Fraud Intelligence Platform architecture: every component, how they connect, what data flows between them, and the key interaction patterns.

---

## High-Level Architecture

```mermaid
graph TB
    subgraph ingestion ["Ingestion Layer"]
        SIM["Transaction Simulator<br/>(Python)"]
    end

    subgraph streaming ["Streaming Backbone"]
        KF["Kafka KRaft Broker<br/>7 Topics · 6 Partitions"]
    end

    subgraph processing ["Stream Processing"]
        SP_D["Spark Driver"]
        SP_W["Spark Worker"]
        SP_D --- SP_W
    end

    subgraph ml ["ML Scoring"]
        XGB["XGBoost<br/>Supervised"]
        IF["Isolation Forest<br/>Unsupervised"]
    end

    subgraph storage ["Lakehouse Storage"]
        NES["Nessie Catalog<br/>(REST)"]
        ICE_B["Iceberg Bronze"]
        ICE_S["Iceberg Silver"]
        ICE_G["Iceberg Gold"]
        MIO["MinIO<br/>S3-Compatible"]
        NES --> ICE_B
        NES --> ICE_S
        NES --> ICE_G
        ICE_B --> MIO
        ICE_S --> MIO
        ICE_G --> MIO
    end

    subgraph copilot ["Investigation Copilot"]
        OLL["Ollama<br/>phi3:mini"]
        CHR["ChromaDB<br/>Vector Store"]
    end

    subgraph serving ["Serving Layer"]
        API["FastAPI<br/>REST + WebSocket"]
        DASH["React Dashboard<br/>Vite SPA"]
    end

    subgraph orchestration ["Orchestration"]
        AF_S["Airflow Scheduler"]
        AF_W["Airflow Webserver"]
        AF_PG["Airflow PostgreSQL"]
        AF_S --> AF_PG
        AF_W --> AF_PG
    end

    subgraph monitoring ["Observability"]
        PROM["Prometheus"]
        GRAF["Grafana"]
        PROM --> GRAF
    end

    SIM -->|"JSON events<br/>100 TPS"| KF
    KF -->|"transactions_raw"| SP_D
    SP_W -->|"Feature vectors"| XGB
    SP_W -->|"Feature vectors"| IF
    XGB -->|"fraud_scores"| KF
    IF -->|"anomaly_scores"| KF
    SP_W -->|"Bronze writes"| NES
    SP_W -->|"Silver writes"| NES
    KF -->|"fraud_alerts"| API
    NES -->|"SQL queries"| API
    OLL --> API
    CHR --> API
    API -->|"WebSocket + REST"| DASH
    AF_S -->|"Triggers"| SP_D
    AF_S -->|"Triggers"| XGB
    SP_D -->|"Metrics"| PROM
    KF -->|"JMX Metrics"| PROM
    API -->|"Metrics"| PROM
```

---

## Component Inventory

| Component | Technology | Purpose | Memory | Port(s) | Health Check |
|---|---|---|---|---|---|
| Transaction Simulator | Python 3.11 | Generate realistic fraud/legit transactions | 128 MB | — | Process exit code |
| Kafka Broker | Apache Kafka 3.7 (KRaft) | Event streaming backbone | 1024 MB | 9092, 29092 | `kafka-broker-api-versions` |
| Spark Driver | Apache Spark 3.5 | Stream processing coordination | 1024 MB | 4040, 7077 | Spark UI |
| Spark Worker | Apache Spark 3.5 | Stream processing execution | 1024 MB | 8081 | Worker heartbeat |
| Nessie Catalog | Nessie 0.77 | Iceberg REST catalog (Git-like) | 256 MB | 19120 | `/api/v2/config` |
| MinIO | MinIO latest | S3-compatible object store | 512 MB | 9000, 9001 | `/minio/health/live` |
| XGBoost Service | XGBoost 2.0 + FastAPI | Supervised fraud scoring | 256 MB | 8501 | `/health` |
| Isolation Forest | scikit-learn + FastAPI | Unsupervised anomaly detection | 256 MB | 8502 | `/health` |
| Ollama | Ollama + phi3:mini | Local LLM inference | 2048 MB | 11434 | `/api/tags` |
| ChromaDB | ChromaDB 0.4 | Vector store for RAG | 256 MB | 8000 | `/api/v1/heartbeat` |
| FastAPI | FastAPI 0.110 | REST API + WebSocket gateway | 256 MB | 8000 | `/health` |
| React Dashboard | React 18 + Vite 5 | Interactive fraud dashboard | 256 MB | 5173 | HTTP 200 |
| Airflow Scheduler | Airflow 2.8 | DAG scheduling and execution | 512 MB | — | `airflow jobs check` |
| Airflow Webserver | Airflow 2.8 | Airflow management UI | 256 MB | 8080 | `/health` |
| Airflow PostgreSQL | PostgreSQL 16 | Airflow metadata database | 128 MB | 5432 | `pg_isready` |
| Prometheus | Prometheus latest | Metrics collection | 256 MB | 9090 | `/-/healthy` |
| Grafana | Grafana latest | Metrics visualization | 256 MB | 3000 | `/api/health` |

!!! note "Memory Allocations"
    All memory values are Docker container limits. Actual usage may be lower. The total allocation of ~8 GB fits within the Docker Desktop memory limit on a 16 GB MacBook.

---

## Network Topology

```mermaid
graph TB
    subgraph docker_network ["fraud-net (Bridge Network)"]
        direction TB

        subgraph ports_external ["External Ports (Host-Mapped)"]
            P9092["9092 — Kafka"]
            P5173["5173 — Dashboard"]
            P8000["8000 — FastAPI"]
            P8080["8080 — Airflow UI"]
            P3000["3000 — Grafana"]
            P9090["9090 — Prometheus"]
            P9001["9001 — MinIO Console"]
            P4040["4040 — Spark UI"]
            P19120["19120 — Nessie"]
        end

        subgraph internal ["Internal Service Discovery (DNS)"]
            kafka["kafka:29092"]
            spark-master["spark-master:7077"]
            spark-worker["spark-worker:8081"]
            nessie["nessie:19120"]
            minio["minio:9000"]
            xgboost-service["xgboost-service:8501"]
            isolation-forest["isolation-forest:8502"]
            ollama["ollama:11434"]
            chromadb["chromadb:8000"]
            fastapi["fastapi:8000"]
            prometheus["prometheus:9090"]
            grafana["grafana:3000"]
            airflow-postgres["airflow-postgres:5432"]
        end
    end

    P9092 -.-> kafka
    P5173 -.-> fastapi
    P8000 -.-> fastapi
    P8080 -.-> airflow-webserver
    P3000 -.-> grafana
    P9090 -.-> prometheus
    P9001 -.-> minio
    P4040 -.-> spark-master
    P19120 -.-> nessie
```

!!! info "Service Discovery"
    All services communicate over the `fraud-net` Docker bridge network using container DNS names. No hardcoded IPs are used—services reference each other by hostname (e.g., `kafka:29092`, `nessie:19120`).

---

## Data Schemas

### Transaction Event (Input)

```json title="Transaction JSON Schema" hl_lines="5 6 7"
{
  "transaction_id": "txn_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2024-03-15T14:30:00.000Z",
  "customer_id": "cust_00042",
  "amount": 2499.99,
  "currency": "USD",
  "merchant_id": "merch_electronics_0012",
  "merchant_category": "electronics",
  "merchant_country": "US",
  "card_type": "credit",
  "card_network": "visa",
  "entry_mode": "chip",
  "customer_lat": 37.7749,
  "customer_lon": -122.4194,
  "device_id": "dev_iphone14_abc",
  "ip_address": "192.168.1.100",
  "is_international": false,
  "is_fraud": false
}
```

### Fraud Alert (Output)

```json title="Fraud Alert Schema"
{
  "alert_id": "alert_20240315_143000_txn_a1b2c3d4",
  "transaction_id": "txn_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2024-03-15T14:30:01.200Z",
  "customer_id": "cust_00042",
  "amount": 2499.99,
  "xgboost_score": 0.87,
  "isolation_forest_score": -0.92,
  "ensemble_score": 0.89,
  "risk_level": "HIGH",
  "triggered_rules": [
    "amount_zscore_exceeded",
    "geo_velocity_anomaly"
  ],
  "top_features": {
    "amount_zscore": 3.2,
    "geo_velocity_kmh": 850.0,
    "tx_count_1h": 12
  }
}
```

### ML Prediction (Internal)

```json title="ML Prediction Schema"
{
  "transaction_id": "txn_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "model": "xgboost_v2",
  "prediction": 1,
  "probability": 0.87,
  "features_used": 10,
  "inference_latency_ms": 4.2,
  "model_version": "2024-03-15-retrain",
  "feature_importances": {
    "amount_zscore": 0.23,
    "geo_velocity_kmh": 0.19,
    "tx_count_1h": 0.15,
    "merchant_risk_score": 0.12,
    "amount_to_avg_ratio": 0.10
  }
}
```

---

## Sequence Diagrams

### Normal Transaction Flow

```mermaid
sequenceDiagram
    participant SIM as Transaction Simulator
    participant KF as Kafka
    participant SP as Spark Streaming
    participant ML as ML Ensemble
    participant ICE as Iceberg (Nessie)
    participant API as FastAPI
    participant UI as React Dashboard

    SIM->>KF: Publish transaction (transactions_raw)
    KF->>SP: Consume event
    SP->>SP: Parse JSON + validate schema
    SP->>SP: Compute 10 features (windowed + stateful)
    SP->>ML: Request scoring (HTTP)
    ML->>ML: XGBoost predict + IF score
    ML-->>SP: ensemble_score: 0.12 (LOW)
    SP->>ICE: Write to Bronze (raw event)
    SP->>ICE: Write to Silver (enriched + scored)
    SP->>KF: Publish to scored_transactions
    Note over SP,ICE: No alert generated — score below threshold
    API->>KF: Consume scored_transactions
    API->>UI: Push via WebSocket (live feed)
```

### Fraud Detection Flow

```mermaid
sequenceDiagram
    participant SIM as Transaction Simulator
    participant KF as Kafka
    participant SP as Spark Streaming
    participant ML as ML Ensemble
    participant ICE as Iceberg (Nessie)
    participant API as FastAPI
    participant UI as React Dashboard

    SIM->>KF: Publish suspicious transaction
    KF->>SP: Consume event
    SP->>SP: Parse + compute features
    SP->>SP: amount_zscore=3.2, geo_velocity=850km/h
    SP->>ML: Request scoring
    ML->>ML: XGBoost: 0.87, IF: -0.92
    ML-->>SP: ensemble_score: 0.89 (HIGH)
    SP->>ICE: Write to Bronze + Silver
    SP->>KF: Publish to fraud_alerts topic
    SP->>KF: Publish to scored_transactions

    rect rgb(255, 230, 230)
        Note over KF,UI: Alert Path Activated
        API->>KF: Consume fraud_alerts
        API->>UI: Push HIGH alert via WebSocket
        UI->>UI: Render alert banner + sound
    end
```

### Investigation Copilot Interaction

```mermaid
sequenceDiagram
    participant USER as Analyst
    participant UI as React Dashboard
    participant API as FastAPI
    participant CHR as ChromaDB
    participant OLL as Ollama (phi3:mini)
    participant ICE as Iceberg

    USER->>UI: "Why was txn_a1b2c flagged?"
    UI->>API: POST /copilot/query
    API->>CHR: Similarity search (embedded query)
    CHR-->>API: Top 5 relevant context chunks
    API->>ICE: Fetch transaction details + history
    ICE-->>API: Transaction record + customer profile
    API->>API: Build RAG prompt (context + query)
    API->>OLL: POST /api/generate
    OLL-->>API: Generated explanation
    API-->>UI: Streaming response
    UI-->>USER: "This transaction was flagged because<br/>the amount ($2,499) is 3.2σ above<br/>the customer's average, and the<br/>geo-velocity of 850 km/h suggests<br/>impossible travel..."
```

---

## Inter-Service Dependencies

```mermaid
graph LR
    subgraph tier1 ["Tier 1: Infrastructure"]
        MIO[MinIO]
        NES[Nessie]
        KF[Kafka]
        PG[PostgreSQL]
    end

    subgraph tier2 ["Tier 2: Processing"]
        SP[Spark]
        ML_X[XGBoost]
        ML_I[Isolation Forest]
        OLL[Ollama]
        CHR[ChromaDB]
    end

    subgraph tier3 ["Tier 3: Application"]
        API[FastAPI]
        AF[Airflow]
        SIM[Simulator]
    end

    subgraph tier4 ["Tier 4: Presentation"]
        DASH[Dashboard]
        GRAF[Grafana]
    end

    MIO --> NES
    NES --> SP
    KF --> SP
    KF --> SIM
    KF --> API
    SP --> ML_X
    SP --> ML_I
    NES --> API
    OLL --> API
    CHR --> API
    PG --> AF
    API --> DASH
    PROM[Prometheus] --> GRAF
    SP --> PROM
    KF --> PROM
```

!!! warning "Startup Order"
    Services must start in tier order. Docker Compose `depends_on` with health checks enforces this. Kafka must be healthy before Spark or the Simulator starts; Nessie and MinIO must be ready before any Iceberg writes.

---

## Key Design Principles

1. **Memory-first architecture** — Every component was selected to minimize memory footprint while maintaining production-grade functionality.
2. **Event-driven by default** — Kafka sits at the center; all services communicate through topics, enabling loose coupling and replay.
3. **Medallion data quality** — Raw → validated → aggregated ensures data quality improves at each layer.
4. **Dual-model scoring** — Combining supervised and unsupervised ML catches both known and novel fraud patterns.
5. **Local-first AI** — The LLM copilot runs entirely on-device with Ollama, requiring no external API calls or keys.
