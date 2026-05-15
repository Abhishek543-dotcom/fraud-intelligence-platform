# ============================================================
# ML Service — fraud detection model serving
# Base: python:3.11-slim (ARM64 compatible)
# ============================================================
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt* ./
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; else \
    pip install --no-cache-dir \
        fastapi==0.109.0 \
        uvicorn[standard]==0.27.0 \
        kafka-python==2.0.2 \
        aiokafka==0.10.0 \
        boto3==1.34.0 \
        redis==5.0.1 \
        scikit-learn==1.4.0 \
        xgboost==2.0.3 \
        lightgbm==4.2.0 \
        pandas==2.1.4 \
        numpy==1.26.3 \
        pyarrow==14.0.2 \
        shap==0.44.1 \
        mlflow==2.10.0 \
        prometheus-client==0.19.0 \
        structlog==24.1.0 \
        pydantic==2.5.3 \
        joblib==1.3.2; \
    fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "inference.model_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
