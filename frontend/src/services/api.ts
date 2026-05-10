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
