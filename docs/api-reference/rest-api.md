# REST API Reference

Complete REST API documentation for the Fraud Intelligence Platform.

**Base URL:** `http://localhost:8000/api`

!!! info "Authentication"
    Local development uses no authentication by default. In production, all endpoints require a JWT bearer token in the `Authorization` header.

---

## Transactions API

### List Transactions

Retrieve a paginated list of transactions with optional filtering.

```
GET /api/transactions
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number |
| `limit` | integer | 50 | Items per page (max 200) |
| `status` | string | — | Filter by status: `pending`, `approved`, `declined`, `flagged` |
| `min_amount` | float | — | Minimum transaction amount |
| `max_amount` | float | — | Maximum transaction amount |
| `start_date` | string (ISO 8601) | — | Filter transactions after this date |
| `end_date` | string (ISO 8601) | — | Filter transactions before this date |
| `merchant` | string | — | Filter by merchant name (partial match) |
| `sort_by` | string | `timestamp` | Sort field: `timestamp`, `amount`, `status` |
| `sort_order` | string | `desc` | Sort direction: `asc`, `desc` |

**Response:**

```json
{
  "data": [
    {
      "transaction_id": "txn_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "amount": 249.99,
      "currency": "USD",
      "merchant": "TechStore Online",
      "merchant_category": "electronics",
      "customer_id": "cust_001",
      "status": "approved",
      "is_international": false,
      "timestamp": "2024-06-15T14:32:10Z",
      "fraud_score": 0.12,
      "processing_time_ms": 45
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total_count": 15432,
    "total_pages": 309
  }
}
```

```bash
curl -s 'http://localhost:8000/api/transactions?limit=10&status=flagged&min_amount=1000' | jq .
```

---

### Get Transaction Detail

```
GET /api/transactions/{transaction_id}
```

**Response:**

```json
{
  "transaction_id": "txn_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "amount": 9999.99,
  "currency": "USD",
  "merchant": "LuxuryGoods Inc",
  "merchant_category": "jewelry",
  "customer_id": "cust_042",
  "card_type": "credit",
  "card_brand": "visa",
  "status": "flagged",
  "is_international": true,
  "origin_country": "US",
  "destination_country": "NG",
  "timestamp": "2024-06-15T03:22:45Z",
  "fraud_score": 0.94,
  "features": {
    "velocity_1h": 8,
    "velocity_24h": 12,
    "avg_amount_30d": 152.30,
    "amount_deviation": 5.2,
    "merchant_risk_score": 0.78,
    "hour_of_day": 3,
    "is_weekend": false
  },
  "alerts": [
    {
      "alert_id": "alert_001",
      "type": "ml_prediction",
      "severity": "high",
      "created_at": "2024-06-15T03:22:46Z"
    }
  ]
}
```

```bash
curl -s http://localhost:8000/api/transactions/txn_a1b2c3d4-e5f6-7890-abcd-ef1234567890 | jq .
```

**Status Codes:**

| Code | Description |
|------|-------------|
| `200` | Transaction found |
| `404` | Transaction not found |

---

### Advanced Search

```
GET /api/transactions/search
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Free-text search across merchant name, customer ID |
| `customer_id` | string | Exact customer ID match |
| `card_brand` | string | Card brand filter: `visa`, `mastercard`, `amex` |
| `country` | string | Origin or destination country code |
| `fraud_score_min` | float | Minimum fraud score (0.0-1.0) |

```bash
curl -s 'http://localhost:8000/api/transactions/search?q=electronics&fraud_score_min=0.8' | jq .
```

---

### Transaction Statistics

```
GET /api/transactions/stats
```

**Response:**

```json
{
  "total_count": 125430,
  "total_volume": 12543000.50,
  "avg_amount": 100.00,
  "fraud_rate": 0.023,
  "status_breakdown": {
    "approved": 120500,
    "declined": 2100,
    "flagged": 2830
  },
  "hourly_volume": [
    {"hour": 0, "count": 3200, "amount": 320000.00},
    {"hour": 1, "count": 2800, "amount": 280000.00}
  ],
  "top_merchants": [
    {"merchant": "Amazon", "count": 5200, "fraud_rate": 0.01},
    {"merchant": "Walmart", "count": 3400, "fraud_rate": 0.008}
  ],
  "period": {"start": "2024-06-15T00:00:00Z", "end": "2024-06-15T23:59:59Z"}
}
```

---

## Fraud Alerts API

### List Alerts

```
GET /api/alerts
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | — | `pending`, `investigating`, `confirmed_fraud`, `false_positive`, `dismissed` |
| `severity` | string | — | `low`, `medium`, `high`, `critical` |
| `min_score` | float | — | Minimum fraud score |
| `limit` | integer | 50 | Items per page |
| `page` | integer | 1 | Page number |

**Response:**

```json
{
  "data": [
    {
      "alert_id": "alert_a1b2c3",
      "transaction_id": "txn_d4e5f6",
      "fraud_score": 0.95,
      "severity": "critical",
      "status": "pending",
      "alert_type": "ml_prediction",
      "triggered_rules": ["high_amount", "velocity_exceeded", "unusual_hour"],
      "created_at": "2024-06-15T03:22:46Z",
      "updated_at": "2024-06-15T03:22:46Z"
    }
  ],
  "pagination": {"page": 1, "limit": 50, "total_count": 284}
}
```

```bash
curl -s 'http://localhost:8000/api/alerts?status=pending&severity=critical' | jq .
```

---

### Get Alert Detail

```
GET /api/alerts/{alert_id}
```

**Response:** Includes full transaction details, feature values, model explanation, and audit trail.

```json
{
  "alert_id": "alert_a1b2c3",
  "transaction": { "...full transaction object..." },
  "fraud_score": 0.95,
  "severity": "critical",
  "status": "pending",
  "model_version": "v2.4.0",
  "feature_importance": {
    "amount_deviation": 0.35,
    "velocity_1h": 0.25,
    "merchant_risk_score": 0.20,
    "unusual_hour": 0.12,
    "is_international": 0.08
  },
  "triggered_rules": [
    {"rule": "high_amount", "threshold": 10000, "actual": 9999.99},
    {"rule": "velocity_exceeded", "threshold": 5, "actual": 8}
  ],
  "audit_trail": [
    {"action": "created", "timestamp": "2024-06-15T03:22:46Z", "actor": "system"},
    {"action": "assigned", "timestamp": "2024-06-15T03:25:00Z", "actor": "analyst_01"}
  ]
}
```

---

### Update Alert Status

```
PUT /api/alerts/{alert_id}/status
```

**Request Body:**

```json
{
  "status": "confirmed_fraud",
  "notes": "Verified with customer - unauthorized transaction",
  "analyst_id": "analyst_01"
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| `200` | Status updated successfully |
| `400` | Invalid status transition |
| `404` | Alert not found |

```bash
curl -X PUT http://localhost:8000/api/alerts/alert_a1b2c3/status \
  -H "Content-Type: application/json" \
  -d '{"status": "confirmed_fraud", "notes": "Unauthorized", "analyst_id": "analyst_01"}'
```

---

### Alert Statistics

```
GET /api/alerts/stats
```

**Response:**

```json
{
  "total_count": 2830,
  "by_status": {
    "pending": 142,
    "investigating": 38,
    "confirmed_fraud": 1850,
    "false_positive": 620,
    "dismissed": 180
  },
  "by_severity": {"low": 800, "medium": 1200, "high": 600, "critical": 230},
  "avg_resolution_time_minutes": 45.2,
  "false_positive_rate": 0.219,
  "today": {"new_alerts": 42, "resolved": 35}
}
```

---

## ML Predictions API

### Score Single Transaction

```
POST /api/ml/predict
```

**Request Body:**

```json
{
  "amount": 5000.00,
  "merchant_category": "electronics",
  "hour_of_day": 3,
  "is_international": true,
  "velocity_1h": 8,
  "velocity_24h": 15,
  "avg_amount_30d": 150.00,
  "customer_age_days": 30
}
```

**Response:**

```json
{
  "fraud_probability": 0.87,
  "risk_level": "high",
  "model_version": "v2.4.0",
  "inference_time_ms": 12,
  "top_features": [
    {"feature": "velocity_1h", "importance": 0.32, "value": 8},
    {"feature": "amount_deviation", "importance": 0.28, "value": 4.8},
    {"feature": "hour_of_day", "importance": 0.15, "value": 3}
  ]
}
```

```bash
curl -X POST http://localhost:8001/api/ml/predict \
  -H "Content-Type: application/json" \
  -d '{"amount": 5000, "merchant_category": "electronics", "hour_of_day": 3, "is_international": true}'
```

---

### Batch Scoring

```
POST /api/ml/predict/batch
```

**Request Body:**

```json
{
  "transactions": [
    {"amount": 50, "merchant_category": "grocery", "hour_of_day": 12},
    {"amount": 9999, "merchant_category": "electronics", "hour_of_day": 2}
  ]
}
```

**Response:**

```json
{
  "predictions": [
    {"index": 0, "fraud_probability": 0.03, "risk_level": "low"},
    {"index": 1, "fraud_probability": 0.89, "risk_level": "high"}
  ],
  "batch_size": 2,
  "total_inference_time_ms": 18,
  "model_version": "v2.4.0"
}
```

---

### Active Model Info

```
GET /api/ml/model/info
```

```json
{
  "model_name": "fraud_detector",
  "version": "v2.4.0",
  "algorithm": "xgboost",
  "training_date": "2024-06-10T02:00:00Z",
  "training_samples": 125000,
  "metrics": {
    "auc_roc": 0.974,
    "auc_pr": 0.891,
    "precision_at_90_recall": 0.85,
    "f1_score": 0.88
  },
  "feature_count": 24,
  "status": "active"
}
```

---

### Hot-Reload Model

```
POST /api/ml/model/reload
```

Loads the latest model version from the registry without service restart.

```bash
curl -X POST http://localhost:8001/api/ml/model/reload
```

---

## Investigation Copilot API

### Investigate (Ask Question)

```
POST /api/copilot/investigate
```

**Request Body:**

```json
{
  "question": "What are the common patterns in fraud alerts from the last 24 hours?",
  "context": {
    "time_window": "24h",
    "include_transactions": true
  }
}
```

**Response:**

```json
{
  "answer": "Based on analysis of 42 fraud alerts in the last 24 hours, the primary patterns are: (1) High-velocity card-not-present transactions at electronics merchants between 1-4 AM, accounting for 60% of alerts...",
  "sources": [
    {"type": "alert", "id": "alert_001", "relevance": 0.95},
    {"type": "transaction", "id": "txn_042", "relevance": 0.88}
  ],
  "model": "llama3.2:3b",
  "response_time_ms": 2400
}
```

---

### Explain Alert

```
POST /api/copilot/explain/{transaction_id}
```

```json
{
  "explanation": "This transaction was flagged because: (1) The amount of $9,999.99 is 65x higher than the customer's 30-day average of $152.30. (2) The transaction occurred at 3:22 AM, outside the customer's normal activity hours. (3) This is the 8th transaction in the last hour, well above the velocity threshold of 5.",
  "risk_factors": ["amount_anomaly", "temporal_anomaly", "velocity_anomaly"],
  "recommended_action": "Escalate for manual review - high confidence of account compromise"
}
```

---

### Generate Investigation Report

```
POST /api/copilot/report/{case_id}
```

Generates a structured investigation report for a fraud case.

---

### Natural Language Fraud Search

```
POST /api/copilot/search
```

**Request:** `{"query": "Show me international transactions over $5000 from new accounts"}`

Translates natural language to structured queries and returns matching transactions.

---

### Check LLM Health

```
GET /api/copilot/health
```

```json
{
  "status": "healthy",
  "model": "llama3.2:3b",
  "ollama_url": "http://ollama:11434",
  "model_loaded": true,
  "avg_response_time_ms": 1800
}
```

---

## System API

### Health Check

```
GET /api/health
```

Returns composite health status of all platform services. See [Operations Guide](../runbook/operations.md) for response format.

### Prometheus Metrics

```
GET /api/metrics
```

Exposes metrics in Prometheus format for scraping:

```
# HELP fraud_transactions_total Total transactions processed
# TYPE fraud_transactions_total counter
fraud_transactions_total{status="approved"} 120500
fraud_transactions_total{status="flagged"} 2830

# HELP fraud_alert_resolution_seconds Alert resolution time
# TYPE fraud_alert_resolution_seconds histogram
fraud_alert_resolution_seconds_bucket{le="60"} 150
fraud_alert_resolution_seconds_bucket{le="300"} 420

# HELP fraud_model_inference_seconds ML model inference time
# TYPE fraud_model_inference_seconds histogram
fraud_model_inference_seconds_bucket{le="0.01"} 8500
fraud_model_inference_seconds_bucket{le="0.05"} 12000
```
