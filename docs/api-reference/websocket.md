# WebSocket API

Real-time event streaming via WebSocket for the Fraud Intelligence Platform dashboard.

---

## Connection

### URL

```
ws://localhost:8000/ws/alerts
```

### Authentication

Pass a JWT token as a query parameter for authenticated connections:

```
ws://localhost:8000/ws/alerts?token=<jwt_token>
```

!!! info
    In local development mode, authentication is optional. The connection will succeed without a token.

### Connection Example (JavaScript)

```javascript
const WS_URL = 'ws://localhost:8000/ws/alerts';

class FraudAlertWebSocket {
  constructor(url, options = {}) {
    this.url = url;
    this.maxRetries = options.maxRetries || 10;
    this.retryCount = 0;
    this.baseDelay = options.baseDelay || 1000;
    this.maxDelay = options.maxDelay || 30000;
    this.handlers = new Map();
    this.connect();
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.retryCount = 0;

      // Subscribe to specific alert types
      this.ws.send(JSON.stringify({
        type: 'subscribe',
        channels: ['alerts', 'metrics'],
      }));
    };

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.dispatch(message);
    };

    this.ws.onclose = (event) => {
      console.log(`WebSocket closed: ${event.code} ${event.reason}`);
      if (event.code !== 1000) {
        this.reconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  reconnect() {
    if (this.retryCount >= this.maxRetries) {
      console.error('Max reconnection attempts reached');
      return;
    }

    const delay = Math.min(
      this.baseDelay * Math.pow(2, this.retryCount),
      this.maxDelay
    );
    const jitter = delay * 0.1 * Math.random();

    console.log(`Reconnecting in ${delay + jitter}ms (attempt ${this.retryCount + 1})`);

    setTimeout(() => {
      this.retryCount++;
      this.connect();
    }, delay + jitter);
  }

  on(type, handler) {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, []);
    }
    this.handlers.get(type).push(handler);
  }

  dispatch(message) {
    const handlers = this.handlers.get(message.type) || [];
    handlers.forEach(handler => handler(message));

    // Also dispatch to wildcard handlers
    const wildcardHandlers = this.handlers.get('*') || [];
    wildcardHandlers.forEach(handler => handler(message));
  }

  close() {
    this.maxRetries = 0; // Prevent reconnection
    this.ws.close(1000, 'Client closing');
  }
}

// Usage
const ws = new FraudAlertWebSocket(WS_URL);

ws.on('alert', (message) => {
  console.log('New fraud alert:', message.data);
  // Update UI with new alert
});

ws.on('metric', (message) => {
  console.log('Metric update:', message.data);
  // Update dashboard metrics
});

ws.on('heartbeat', (message) => {
  // Connection is alive
});
```

---

## Message Types

All messages follow a discriminated union pattern with a `type` field:

```json
{
  "type": "<message_type>",
  "data": { ... },
  "timestamp": "2024-06-15T14:32:10.123Z",
  "sequence": 12345
}
```

### Alert Message

Sent when a new fraud alert is generated.

```json
{
  "type": "alert",
  "data": {
    "alert_id": "alert_a1b2c3",
    "transaction_id": "txn_d4e5f6",
    "fraud_score": 0.95,
    "severity": "critical",
    "alert_type": "ml_prediction",
    "amount": 9999.99,
    "merchant": "SuspiciousStore",
    "merchant_category": "electronics",
    "customer_id": "cust_042",
    "triggered_rules": ["high_amount", "velocity_exceeded", "unusual_hour"],
    "top_features": [
      {"feature": "velocity_1h", "importance": 0.32, "value": 8},
      {"feature": "amount_deviation", "importance": 0.28, "value": 4.8}
    ]
  },
  "timestamp": "2024-06-15T03:22:46.789Z",
  "sequence": 42
}
```

### Metric Message

Periodic system metric updates (every 5 seconds by default).

```json
{
  "type": "metric",
  "data": {
    "metric_name": "pipeline_stats",
    "transactions_per_second": 45.2,
    "alerts_per_minute": 3.1,
    "avg_fraud_score": 0.34,
    "active_alerts": 142,
    "kafka_consumer_lag": 23,
    "spark_batch_duration_ms": 2340,
    "model_inference_avg_ms": 12,
    "total_transactions_today": 54320,
    "total_alerts_today": 42,
    "false_positive_rate": 0.22,
    "system": {
      "cpu_usage": 0.45,
      "memory_usage": 0.72,
      "disk_usage": 0.38
    }
  },
  "timestamp": "2024-06-15T14:32:10.000Z",
  "sequence": 12345
}
```

### Heartbeat Message

Sent every 30 seconds to keep the connection alive.

```json
{
  "type": "heartbeat",
  "data": {
    "server_time": "2024-06-15T14:32:30.000Z",
    "uptime_seconds": 84230,
    "connected_clients": 3
  },
  "timestamp": "2024-06-15T14:32:30.000Z",
  "sequence": 12346
}
```

---

## Message Schemas

### TypeScript Type Definitions

```typescript
// Base message type
interface BaseMessage {
  type: string;
  timestamp: string;  // ISO 8601
  sequence: number;   // Monotonically increasing
}

// Alert message
interface AlertMessage extends BaseMessage {
  type: 'alert';
  data: {
    alert_id: string;
    transaction_id: string;
    fraud_score: number;       // 0.0 - 1.0
    severity: 'low' | 'medium' | 'high' | 'critical';
    alert_type: 'ml_prediction' | 'rule_based' | 'hybrid';
    amount: number;
    merchant: string;
    merchant_category: string;
    customer_id: string;
    triggered_rules: string[];
    top_features: Array<{
      feature: string;
      importance: number;
      value: number;
    }>;
  };
}

// Metric message
interface MetricMessage extends BaseMessage {
  type: 'metric';
  data: {
    metric_name: string;
    transactions_per_second: number;
    alerts_per_minute: number;
    avg_fraud_score: number;
    active_alerts: number;
    kafka_consumer_lag: number;
    spark_batch_duration_ms: number;
    model_inference_avg_ms: number;
    total_transactions_today: number;
    total_alerts_today: number;
    false_positive_rate: number;
    system: {
      cpu_usage: number;
      memory_usage: number;
      disk_usage: number;
    };
  };
}

// Heartbeat message
interface HeartbeatMessage extends BaseMessage {
  type: 'heartbeat';
  data: {
    server_time: string;
    uptime_seconds: number;
    connected_clients: number;
  };
}

// Union type
type WebSocketMessage = AlertMessage | MetricMessage | HeartbeatMessage;
```

---

## Subscription Management

Clients can subscribe to specific channels after connecting:

### Subscribe

```json
{
  "type": "subscribe",
  "channels": ["alerts", "metrics"]
}
```

### Unsubscribe

```json
{
  "type": "unsubscribe",
  "channels": ["metrics"]
}
```

### Filter Alerts

Subscribe to alerts matching specific criteria:

```json
{
  "type": "subscribe",
  "channels": ["alerts"],
  "filters": {
    "min_score": 0.8,
    "severity": ["high", "critical"]
  }
}
```

---

## Reconnection Strategy

The client should implement exponential backoff with jitter:

```
delay = min(base_delay * 2^attempt + random_jitter, max_delay)
```

| Attempt | Base Delay | Actual Delay (approx) |
|---------|------------|----------------------|
| 1 | 1s | 1-1.1s |
| 2 | 2s | 2-2.2s |
| 3 | 4s | 4-4.4s |
| 4 | 8s | 8-8.8s |
| 5 | 16s | 16-17.6s |
| 6+ | 30s (max) | 30-33s |

!!! warning "Reconnection Best Practices"
    - Always implement exponential backoff to avoid thundering herd
    - Add random jitter (±10%) to prevent synchronized reconnections
    - Set a maximum retry limit (default: 10 attempts)
    - Show connection status to the user in the UI
    - Buffer UI updates during disconnection, apply on reconnect

---

## Rate Limiting

| Limit | Value | Scope |
|-------|-------|-------|
| Messages from server | 10 msg/sec per client | Per WebSocket connection |
| Subscriptions | 5 channels max | Per client |
| Client commands | 2 msg/sec | Inbound rate limit |

If the server is rate-limiting, it sends:

```json
{
  "type": "error",
  "data": {
    "code": "RATE_LIMITED",
    "message": "Message rate exceeded. Max 2 messages/second.",
    "retry_after_ms": 1000
  }
}
```

---

## Error Handling

### WebSocket Close Codes

| Code | Meaning | Client Action |
|------|---------|---------------|
| `1000` | Normal closure | Don't reconnect |
| `1001` | Server going away | Reconnect with backoff |
| `1006` | Abnormal closure | Reconnect with backoff |
| `1008` | Policy violation | Check authentication |
| `1011` | Server error | Reconnect with backoff |
| `4000` | Invalid token | Re-authenticate |
| `4001` | Token expired | Refresh token, reconnect |
| `4002` | Subscription limit | Reduce subscriptions |

### Error Message Format

```json
{
  "type": "error",
  "data": {
    "code": "INVALID_SUBSCRIPTION",
    "message": "Channel 'unknown_channel' does not exist",
    "details": {
      "available_channels": ["alerts", "metrics"]
    }
  },
  "timestamp": "2024-06-15T14:32:10.000Z"
}
```

---

## Testing WebSocket Connections

### Using wscat

```bash
# Install wscat
npm install -g wscat

# Connect
wscat -c ws://localhost:8000/ws/alerts

# Send subscription
> {"type": "subscribe", "channels": ["alerts", "metrics"]}

# You should see metric messages every 5 seconds
# and alert messages when fraud is detected
```

### Using Python

```python
import asyncio
import websockets
import json

async def listen():
    uri = "ws://localhost:8000/ws/alerts"
    async with websockets.connect(uri) as ws:
        # Subscribe
        await ws.send(json.dumps({
            "type": "subscribe",
            "channels": ["alerts", "metrics"],
        }))

        # Listen for messages
        async for message in ws:
            data = json.loads(message)
            if data["type"] == "alert":
                print(f"ALERT: score={data['data']['fraud_score']:.2f} "
                      f"amount=${data['data']['amount']:.2f}")
            elif data["type"] == "metric":
                print(f"TPS: {data['data']['transactions_per_second']:.1f}")

asyncio.run(listen())
```
