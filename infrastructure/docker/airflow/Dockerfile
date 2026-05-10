# ============================================================
# Airflow — Dockerfile with Spark + Kafka providers
# Base: apache/airflow:2.8-python3.11 (ARM64 compatible)
# ============================================================
FROM apache/airflow:2.8-python3.11

USER root

# System dependencies for Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        default-jdk-headless \
        procps \
        curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java

USER airflow

# Airflow providers and dependencies
RUN pip install --no-cache-dir \
    apache-airflow-providers-apache-spark==4.7.1 \
    apache-airflow-providers-apache-kafka==1.3.1 \
    apache-airflow-providers-amazon==8.16.0 \
    great-expectations==0.18.8 \
    boto3==1.34.0 \
    kafka-python==2.0.2 \
    pandas==2.1.4 \
    pyarrow==14.0.2 \
    requests==2.31.0 \
    psycopg2-binary==2.9.9
