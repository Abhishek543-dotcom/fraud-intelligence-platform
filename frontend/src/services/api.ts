import axios from 'axios';
import type {
  PaginatedResponse,
  Transaction,
  FraudAlert,
  DashboardMetrics,
  ModelMetrics,
  FilterParams,
  APIResponse,
} from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '';

const client = axios.create({
  baseURL: `${API_BASE}/api`,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message;
    console.error('[API Error]', message);
    return Promise.reject(error);
  },
);

export async function fetchTransactions(
  params: FilterParams = {},
): Promise<PaginatedResponse<Transaction>> {
  const { data } = await client.get('/transactions', { params });
  return data;
}

export async function fetchTransaction(id: string): Promise<Transaction> {
  const { data } = await client.get<APIResponse<Transaction>>(`/transactions/${id}`);
  return data.data;
}

export async function fetchTransactionStats(): Promise<DashboardMetrics> {
  const { data } = await client.get<APIResponse<DashboardMetrics>>('/transactions/stats');
  return data.data;
}

export async function fetchAlerts(
  params: FilterParams = {},
): Promise<PaginatedResponse<FraudAlert>> {
  const { data } = await client.get('/alerts', { params });
  return data;
}

export async function fetchAlert(id: string): Promise<FraudAlert> {
  const { data } = await client.get<APIResponse<FraudAlert>>(`/alerts/${id}`);
  return data.data;
}

export async function updateAlertStatus(
  id: string,
  status: string,
): Promise<FraudAlert> {
  const { data } = await client.put<APIResponse<FraudAlert>>(`/alerts/${id}/status`, {
    status,
  });
  return data.data;
}

export async function fetchAlertStats(): Promise<Record<string, number>> {
  const { data } = await client.get('/alerts/stats');
  return data.data;
}

export async function fetchModelMetrics(): Promise<ModelMetrics[]> {
  const { data } = await client.get<APIResponse<ModelMetrics[]>>('/ml/metrics');
  return data.data;
}

export async function fetchDashboardMetrics(): Promise<DashboardMetrics> {
  const { data } = await client.get<APIResponse<DashboardMetrics>>('/metrics/dashboard');
  return data.data;
}

export interface KafkaTopicInfo {
  topic: string;
  partitions: number;
  messages: number;
}
export interface ThroughputPoint {
  timestamp: string;
  total_per_sec: number;
  topics: Record<string, number>;
}
export interface SparkAppInfo {
  id: string;
  name: string;
  state: string;
  cores: number;
  duration: number;
}
export interface SparkState {
  status: string;
  workers: number;
  alive_workers: number;
  cores_total: number;
  cores_used: number;
  memory_mb: number;
  active_apps: number;
  completed_apps: number;
  apps: SparkAppInfo[];
}
export interface MinioBucket {
  name: string;
  objects: number;
  size_bytes: number;
}
export interface MinioState {
  reachable: boolean;
  buckets: MinioBucket[];
}
export interface NessieState {
  reachable: boolean;
  tables: { name: string; type: string }[];
  namespaces: string[];
}
export interface MlState {
  reachable: boolean;
  predictions_total: number;
  fraud_ratio: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
}
export interface ServiceStatus {
  status: string;
  [key: string]: unknown;
}
export interface SystemState {
  services: Record<string, ServiceStatus>;
  timestamp: string;
}

export async function fetchKafkaTopics(): Promise<KafkaTopicInfo[]> {
  const { data } = await client.get<APIResponse<{ topics: KafkaTopicInfo[] }>>(
    '/metrics/kafka/topics',
  );
  return data.data.topics;
}

export async function fetchKafkaThroughputHistory(): Promise<ThroughputPoint[]> {
  const { data } = await client.get<APIResponse<{ points: ThroughputPoint[] }>>(
    '/metrics/kafka/throughput-history',
  );
  return data.data.points;
}

export async function fetchSparkState(): Promise<SparkState> {
  const { data } = await client.get<APIResponse<SparkState>>('/metrics/spark/master');
  return data.data;
}

export async function fetchMinioState(): Promise<MinioState> {
  const { data } = await client.get<APIResponse<MinioState>>('/metrics/minio/buckets');
  return data.data;
}

export async function fetchNessieState(): Promise<NessieState> {
  const { data } = await client.get<APIResponse<NessieState>>('/metrics/nessie/tables');
  return data.data;
}

export async function fetchMlState(): Promise<MlState> {
  const { data } = await client.get<APIResponse<MlState>>('/metrics/ml/health');
  return data.data;
}

export async function fetchSystemState(): Promise<SystemState> {
  const { data } = await client.get<APIResponse<SystemState>>('/metrics/system');
  return data.data;
}

export async function sendInvestigationMessage(
  message: string,
  context?: Record<string, string>,
): Promise<ReadableStream<Uint8Array> | null> {
  const response = await fetch(`${API_BASE}/api/investigation/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context }),
  });
  return response.body;
}

export default client;
