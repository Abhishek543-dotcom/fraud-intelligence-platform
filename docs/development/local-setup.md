# Local Development Setup

Developer environment setup guide for contributing to the Fraud Intelligence Platform.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker Desktop | 4.25+ | Container runtime |
| Python | 3.11+ | Backend, ML, Airflow |
| Node.js | 20 LTS | Frontend development |
| Git | 2.40+ | Version control |
| Make | Any | Build automation |
| VS Code | Latest | Recommended IDE |

---

## Fork and Clone

```bash
# Fork the repository on GitHub, then clone
git clone https://github.com/<your-username>/fraud-intelligence-platform.git
cd fraud-intelligence-platform

# Add upstream remote
git remote add upstream https://github.com/your-org/fraud-intelligence-platform.git

# Verify remotes
git remote -v
```

---

## Python Virtual Environment Setup

```bash
# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install all development dependencies
pip install -r requirements-dev.txt
```

!!! info "requirements-dev.txt includes"
    - Core: `pyspark`, `kafka-python`, `fastapi`, `uvicorn`
    - ML: `scikit-learn`, `xgboost`, `pandas`, `numpy`
    - Testing: `pytest`, `pytest-cov`, `pytest-asyncio`, `httpx`
    - Quality: `ruff`, `mypy`, `pre-commit`
    - Airflow: `apache-airflow`, `great-expectations`

---

## Installing Dependencies Per Service

Each service has its own dependency file for isolated development.

=== "Backend API"

    ```bash
    cd services/backend
    pip install -r requirements.txt
    pip install -r requirements-dev.txt

    # Verify
    python -c "import fastapi; print(fastapi.__version__)"
    ```

=== "ML Service"

    ```bash
    cd services/ml-service
    pip install -r requirements.txt

    # Install PyTorch (CPU only for dev)
    pip install torch --index-url https://download.pytorch.org/whl/cpu

    # Verify
    python -c "import sklearn, xgboost; print('ML deps OK')"
    ```

=== "Spark Jobs"

    ```bash
    cd services/spark-jobs
    pip install -r requirements.txt

    # PySpark needs Java 11+
    java -version  # Verify Java is installed

    # Verify
    python -c "import pyspark; print(pyspark.__version__)"
    ```

=== "Frontend"

    ```bash
    cd services/frontend
    npm install

    # Verify
    npm run type-check
    ```

=== "Airflow DAGs"

    ```bash
    cd services/airflow
    pip install -r requirements.txt

    # Verify DAG syntax
    python -c "import airflow; print(airflow.__version__)"
    ```

---

## IDE Configuration

### VS Code Recommended Extensions

Create `.vscode/extensions.json` (already included in repo):

```json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "charliermarsh.ruff",
    "ms-python.mypy-type-checker",
    "ms-toolsai.jupyter",
    "bradlc.vscode-tailwindcss",
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "ms-azuretools.vscode-docker",
    "redhat.vscode-yaml",
    "bierner.markdown-mermaid"
  ]
}
```

### VS Code Settings

```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.analysis.typeCheckingMode": "basic",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode",
    "editor.formatOnSave": true
  },
  "editor.rulers": [100],
  "files.exclude": {
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/node_modules": true
  }
}
```

### Launch Configurations

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Backend API",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": ["src.main:app", "--reload", "--port", "8000"],
      "cwd": "${workspaceFolder}/services/backend",
      "envFile": "${workspaceFolder}/.env"
    },
    {
      "name": "ML Service",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": ["src.main:app", "--reload", "--port", "8001"],
      "cwd": "${workspaceFolder}/services/ml-service",
      "envFile": "${workspaceFolder}/.env"
    },
    {
      "name": "Spark Job (Local)",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/services/spark-jobs/src/streaming_pipeline.py",
      "args": ["--master", "local[2]"],
      "envFile": "${workspaceFolder}/.env"
    }
  ]
}
```

---

## Running Individual Services Outside Docker

For faster iteration and debugging, run services directly on your machine while infrastructure runs in Docker.

```bash
# Start only infrastructure in Docker
docker compose --profile infra up -d
# This starts: Kafka, MinIO, Redis, PostgreSQL (for Airflow)

# Run backend locally (with hot-reload)
cd services/backend
uvicorn src.main:app --reload --port 8000

# Run ML service locally
cd services/ml-service
uvicorn src.main:app --reload --port 8001

# Run frontend locally
cd services/frontend
npm run dev

# Run Spark job locally (connects to Docker Kafka/MinIO)
cd services/spark-jobs
python src/streaming_pipeline.py --master local[2]
```

### Environment Variables for Local Development

```bash
# .env.local (used when running services outside Docker)
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
REDIS_URL=redis://localhost:6379
AIRFLOW_DB_URL=postgresql://airflow:airflow@localhost:5432/airflow
OLLAMA_BASE_URL=http://localhost:11434
ML_SERVICE_URL=http://localhost:8001
```

---

## Hot-Reload Configuration

| Service | Hot-Reload Method | Trigger |
|---------|-------------------|---------|
| Backend API | Uvicorn `--reload` | Python file changes |
| ML Service | Uvicorn `--reload` | Python file changes |
| Frontend | Vite HMR | TypeScript/CSS changes |
| Spark Jobs | Manual restart | Submit new job |
| Airflow DAGs | Auto-scan (30s) | DAG file changes |

---

## Database Migrations

```bash
# Airflow uses its own migration system
docker exec airflow-scheduler airflow db migrate

# For application database (if using Alembic)
cd services/backend
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "add alert priority column"
```

---

## Pre-commit Hooks Setup

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run against all files (first time)
pre-commit run --all-files
```

The `.pre-commit-config.yaml` includes:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [types-requests]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: [--maxkb=500]
```

!!! tip "Bypassing Hooks"
    In rare cases (generated files, emergency fixes), skip hooks with:
    ```bash
    git commit --no-verify -m "emergency: fix production issue"
    ```
    Use sparingly — hooks exist for a reason.
