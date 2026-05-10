import { useQuery } from '@tanstack/react-query';
import {
  fetchTransactions,
  fetchAlerts,
  fetchDashboardMetrics,
  fetchModelMetrics,
  fetchAlertStats,
} from '../services/api';
import type { FilterParams } from '../types';

export function useTransactions(params: FilterParams = {}) {
  return useQuery({
    queryKey: ['transactions', params],
    queryFn: () => fetchTransactions(params),
    refetchInterval: 30_000,
  });
}

export function useAlerts(params: FilterParams = {}) {
  return useQuery({
    queryKey: ['alerts', params],
    queryFn: () => fetchAlerts(params),
    refetchInterval: 15_000,
  });
}

export function useDashboardMetrics() {
  return useQuery({
    queryKey: ['dashboard-metrics'],
    queryFn: fetchDashboardMetrics,
    refetchInterval: 30_000,
  });
}

export function useModelMetrics() {
  return useQuery({
    queryKey: ['model-metrics'],
    queryFn: fetchModelMetrics,
    refetchInterval: 60_000,
  });
}

export function useAlertStats() {
  return useQuery({
    queryKey: ['alert-stats'],
    queryFn: fetchAlertStats,
    refetchInterval: 30_000,
  });
}
