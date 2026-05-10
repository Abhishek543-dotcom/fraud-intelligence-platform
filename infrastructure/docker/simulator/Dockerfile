# ============================================================
# Transaction Simulator — generates realistic fraud data
# Base: python:3.11-slim (ARM64 compatible)
# ============================================================
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt* ./
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; else \
    pip install --no-cache-dir \
        kafka-python==2.0.2 \
        faker==22.0.0 \
        numpy==1.26.3 \
        pandas==2.1.4 \
        structlog==24.1.0 \
        pydantic==2.5.3 \
        pydantic-settings==2.1.0; \
    fi

COPY . .

CMD ["python", "-m", "simulator.main"]
