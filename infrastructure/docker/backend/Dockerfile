# ============================================================
# Backend — FastAPI application
# Base: python:3.11-slim (ARM64 compatible)
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt* ./
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; else \
    pip install --no-cache-dir \
        fastapi==0.109.0 \
        uvicorn[standard]==0.27.0 \
        kafka-python==2.0.2 \
        aiokafka==0.10.0 \
        boto3==1.34.0 \
        redis==5.0.1 \
        httpx==0.26.0 \
        psycopg2-binary==2.9.9 \
        sqlalchemy==2.0.25 \
        pydantic==2.5.3 \
        pydantic-settings==2.1.0 \
        pandas==2.1.4 \
        pyarrow==14.0.2 \
        prometheus-client==0.19.0 \
        chromadb==0.4.22 \
        python-multipart==0.0.6 \
        python-jose[cryptography]==3.3.0 \
        passlib[bcrypt]==1.7.4 \
        structlog==24.1.0; \
    fi

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
