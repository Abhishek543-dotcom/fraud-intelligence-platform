from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Kafka
    kafka_broker: str = "kafka:9092"

    # MinIO / S3
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"

    # PostgreSQL
    postgres_dsn: str = "postgresql://airflow:airflow_secret_2024@postgres:5432/airflow"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Nessie / Iceberg
    nessie_uri: str = "http://nessie:19120/api/v1"

    # Ollama
    ollama_host: str = "http://ollama:11434"
    ollama_model: str = "qwen2:0.5b"

    # ChromaDB
    chromadb_host: str = "chromadb"
    chromadb_port: int = 8000

    # Backend
    backend_port: int = 8888
    backend_workers: int = 2
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # WebSocket
    ws_max_connections: int = 100
    ws_heartbeat_interval: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
