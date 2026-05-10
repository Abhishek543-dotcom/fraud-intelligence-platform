export interface Transaction {
  transaction_id: string;
  customer_id: string;
  merchant_id: string;
  amount: number;
  currency: string;
  timestamp: string;
  channel: 'online' | 'pos' | 'atm' | 'mobile';
  merchant_name: string;
  merchant_category: string;
  customer_name: string;
  location_lat: number;
  location_lon: number;
  country: string;
  is_fraud: boolean;
  fraud_score: number;
  status: 'pending' | 'approved' | 'declined' | 'flagged';
}

export interface FraudAlert {
  alert_id: string;
  transaction_id: string;
  customer_id: string;
  fraud_score: number;
  severity: 'critical' | 'high' | 'medium' | 'low';
  status: 'open' | 'investigating' | 'resolved' | 'false_positive';
  amount: number;
  currency: string;
  merchant_name: string;
  customer_name: string;
  location_lat: number;
  location_lon: number;
  country: string;
  channel: string;
  features: Record<string, number>;
  timestamp: string;
  created_at: string;
}

export interface Customer {
  customer_id: string;
  name: string;
  email: string;
  risk_score: number;
  total_transactions: number;
  flagged_transactions: number;
  account_age_days: number;
  country: string;
}

export interface Merchant {
  merchant_id: string;
  name: string;
  category: string;
  risk_score: number;
  country: string;
}

export interface MLPrediction {
  prediction_id: string;
  transaction_id: string;
  model_version: string;
  fraud_probability: number;
  is_fraud: boolean;
  features: Record<string, number>;
  explanation: string[];
  latency_ms: number;
  timestamp: string;
}

export interface Investigation {
  investigation_id: string;
  alert_id: string;
  status: 'open' | 'in_progress' | 'closed';
  assignee: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface ModelMetrics {
  model_version: string;
  precision: number;
  recall: number;
  f1_score: number;
  auc_roc: number;
  total_predictions: number;
  true_positives: number;
  false_positives: number;
  true_negatives: number;
  false_negatives: number;
  avg_latency_ms: number;
  timestamp: string;
}

export interface DashboardMetrics {
  total_transactions_24h: number;
  total_transactions_trend: number;
  fraud_detected_24h: number;
  fraud_detected_trend: number;
  amount_blocked_24h: number;
  amount_blocked_trend: number;
  false_positive_rate: number;
  false_positive_trend: number;
  avg_detection_time_ms: number;
  active_alerts: number;
}

export type WebSocketMessage =
  | { type: 'alert'; data: FraudAlert }
  | { type: 'metric'; data: DashboardMetrics }
  | { type: 'heartbeat'; timestamp: string };

export interface APIResponse<T> {
  data: T;
  status: string;
  message?: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface FilterParams {
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  search?: string;
  date_from?: string;
  date_to?: string;
  min_amount?: number;
  max_amount?: number;
  severity?: string;
  status?: string;
}

export type ConnectionState = 'connecting' | 'connected' | 'disconnected';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  references?: string[];
}
