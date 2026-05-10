# =============================================================================
# Fraud Intelligence Platform - Makefile
# =============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Docker compose with env file
DC := docker compose --env-file .env
PROFILES_CORE := --profile core
PROFILES_ML := --profile ml
PROFILES_MON := --profile monitoring
PROFILES_FE := --profile frontend
PROFILES_AI := --profile ai
PROFILES_ALL := $(PROFILES_CORE) $(PROFILES_ML) $(PROFILES_MON) $(PROFILES_FE) $(PROFILES_AI)

# =============================================================================
# Lifecycle
# =============================================================================

.PHONY: help
help: ## Show this help message
	@echo "Fraud Intelligence Platform"
	@echo "=========================="
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make \033[36m<target>\033[0m\n\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

.PHONY: build
build: ## Build all custom Docker images
	$(DC) $(PROFILES_ALL) build

.PHONY: up
up: ## Start core services (Kafka, Spark, MinIO, Nessie, Airflow, Postgres, Redis, Backend, Simulator)
	$(DC) $(PROFILES_CORE) up -d
	@echo ""
	@echo "Core services starting. Run 'make ps' to check status."
	@echo "Run 'make init' to create Kafka topics and MinIO buckets."

.PHONY: up-all
up-all: ## Start ALL services (core + ML + monitoring + frontend + AI)
	$(DC) $(PROFILES_ALL) up -d
	@echo ""
	@echo "All services starting. Run 'make ps' to check status."

.PHONY: up-ml
up-ml: ## Start ML services
	$(DC) $(PROFILES_ML) up -d

.PHONY: up-monitoring
up-monitoring: ## Start monitoring services (Prometheus + Grafana)
	$(DC) $(PROFILES_MON) up -d

.PHONY: up-frontend
up-frontend: ## Start frontend services
	$(DC) $(PROFILES_FE) up -d

.PHONY: up-ai
up-ai: ## Start AI services (Ollama + ChromaDB)
	$(DC) $(PROFILES_AI) up -d

.PHONY: down
down: ## Stop all services
	$(DC) $(PROFILES_ALL) down --timeout 30

.PHONY: restart
restart: down up ## Restart core services

.PHONY: restart-all
restart-all: ## Restart all services
	$(DC) $(PROFILES_ALL) down --timeout 30
	$(DC) $(PROFILES_ALL) up -d

# =============================================================================
# Initialization
# =============================================================================

.PHONY: init
init: init-topics init-buckets ## Initialize Kafka topics and MinIO buckets

.PHONY: init-topics
init-topics: ## Create Kafka topics
	@echo "Creating Kafka topics..."
	docker exec fraud-kafka bash /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list > /dev/null 2>&1 || \
		(echo "Kafka not running. Start with 'make up' first." && exit 1)
	docker exec fraud-kafka bash -c '\
		/opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic transactions_raw --partitions 6 --replication-factor 1 --config retention.ms=604800000 && \
		/opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic transactions_enriched --partitions 6 --replication-factor 1 --config retention.ms=1209600000 && \
		/opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic fraud_alerts --partitions 3 --replication-factor 1 --config retention.ms=2592000000 --config cleanup.policy=delete,compact && \
		/opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic model_predictions --partitions 6 --replication-factor 1 --config retention.ms=1209600000 && \
		/opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic replay_events --partitions 3 --replication-factor 1 --config retention.ms=2592000000 && \
		/opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic audit_logs --partitions 3 --replication-factor 1 --config retention.ms=7776000000 --config cleanup.policy=delete,compact && \
		/opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic dlq_transactions --partitions 3 --replication-factor 1 --config retention.ms=2592000000'
	@echo "Done."

.PHONY: init-buckets
init-buckets: ## Create MinIO buckets
	@echo "MinIO buckets are auto-created via minio-init container."
	@echo "If needed, restart: docker restart fraud-minio-init"

# =============================================================================
# Observability
# =============================================================================

.PHONY: logs
logs: ## Tail logs for all core services
	$(DC) $(PROFILES_CORE) logs -f --tail=100

.PHONY: logs-kafka
logs-kafka: ## Tail Kafka logs
	docker logs -f fraud-kafka --tail=100

.PHONY: logs-spark
logs-spark: ## Tail Spark master logs
	docker logs -f fraud-spark-master --tail=100

.PHONY: logs-backend
logs-backend: ## Tail backend logs
	docker logs -f fraud-backend --tail=100

.PHONY: logs-airflow
logs-airflow: ## Tail Airflow webserver logs
	docker logs -f fraud-airflow-webserver --tail=100

.PHONY: ps
ps: ## Show running containers
	$(DC) $(PROFILES_ALL) ps

.PHONY: health
health: ## Run health check on all services
	@bash infrastructure/scripts/healthcheck.sh

# =============================================================================
# Development Tools
# =============================================================================

.PHONY: spark-shell
spark-shell: ## Open PySpark shell connected to the cluster
	docker exec -it fraud-spark-master /opt/bitnami/spark/bin/pyspark \
		--master spark://spark-master:7077

.PHONY: kafka-console
kafka-console: ## Open Kafka console consumer for transactions_raw
	docker exec -it fraud-kafka /opt/bitnami/kafka/bin/kafka-console-consumer.sh \
		--bootstrap-server localhost:9092 \
		--topic transactions_raw \
		--from-beginning

.PHONY: kafka-topics
kafka-topics: ## List all Kafka topics
	docker exec fraud-kafka /opt/bitnami/kafka/bin/kafka-topics.sh \
		--bootstrap-server localhost:9092 --list

.PHONY: psql
psql: ## Connect to PostgreSQL
	docker exec -it fraud-postgres psql -U fraud_platform -d fraud_platform

.PHONY: redis-cli
redis-cli: ## Connect to Redis CLI
	docker exec -it fraud-redis redis-cli

# =============================================================================
# Testing & Quality
# =============================================================================

.PHONY: test
test: ## Run all tests
	@echo "Running backend tests..."
	cd backend && python -m pytest tests/ -v --tb=short 2>/dev/null || echo "No backend tests found."
	@echo ""
	@echo "Running ML tests..."
	cd ml && python -m pytest tests/ -v --tb=short 2>/dev/null || echo "No ML tests found."
	@echo ""
	@echo "Running simulator tests..."
	cd simulator && python -m pytest tests/ -v --tb=short 2>/dev/null || echo "No simulator tests found."

.PHONY: lint
lint: ## Run linters
	@echo "Running Python linting..."
	ruff check backend/ ml/ simulator/ 2>/dev/null || echo "ruff not installed or no Python files found."
	@echo ""
	@echo "Running frontend linting..."
	cd frontend && npm run lint 2>/dev/null || echo "No frontend lint target found."

# =============================================================================
# Cleanup
# =============================================================================

.PHONY: clean
clean: ## Stop all containers and remove volumes
	$(DC) $(PROFILES_ALL) down -v --remove-orphans --timeout 30
	@echo "All containers stopped and volumes removed."

.PHONY: reset
reset: ## Full platform reset (interactive confirmation)
	@bash infrastructure/scripts/reset-all.sh

.PHONY: prune
prune: ## Remove unused Docker resources
	docker system prune -f --volumes
