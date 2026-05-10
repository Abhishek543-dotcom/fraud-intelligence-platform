import { TrendingUp, TrendingDown, AlertTriangle, DollarSign, Activity, Target } from 'lucide-react';
import clsx from 'clsx';
import { useDashboardMetrics } from '../hooks/useApi';
import { formatNumber, formatCurrency, formatPercent, formatLatency } from '../utils/formatters';

interface MetricCardProps {
  label: string;
  value: string;
  trend: number;
  icon: React.ReactNode;
  color: string;
}

function MetricCard({ label, value, trend, icon, color }: MetricCardProps) {
  const isPositiveTrend = trend >= 0;
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
          <p className={clsx('text-2xl font-bold mt-1', color)}>{value}</p>
        </div>
        <div className={clsx('p-2 rounded-lg', color.replace('text-', 'bg-') + '/10')}>
          {icon}
        </div>
      </div>
      <div className="flex items-center gap-1 mt-3 text-xs">
        {isPositiveTrend ? (
          <TrendingUp className="w-3 h-3 text-green-400" />
        ) : (
          <TrendingDown className="w-3 h-3 text-red-400" />
        )}
        <span className={isPositiveTrend ? 'text-green-400' : 'text-red-400'}>
          {formatPercent(Math.abs(trend))}
        </span>
        <span className="text-gray-500">vs prev 24h</span>
      </div>
    </div>
  );
}

export default function MetricsPanel() {
  const { data: metrics, isLoading } = useDashboardMetrics();

  if (isLoading || !metrics) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-gray-900 border border-gray-800 rounded-xl p-4 h-28 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <MetricCard
        label="Transactions (24h)"
        value={formatNumber(metrics.total_transactions_24h)}
        trend={metrics.total_transactions_trend}
        icon={<Activity className="w-5 h-5 text-blue-400" />}
        color="text-blue-400"
      />
      <MetricCard
        label="Fraud Detected"
        value={formatNumber(metrics.fraud_detected_24h)}
        trend={metrics.fraud_detected_trend}
        icon={<AlertTriangle className="w-5 h-5 text-red-400" />}
        color="text-red-400"
      />
      <MetricCard
        label="Amount Blocked"
        value={formatCurrency(metrics.amount_blocked_24h)}
        trend={metrics.amount_blocked_trend}
        icon={<DollarSign className="w-5 h-5 text-green-400" />}
        color="text-green-400"
      />
      <MetricCard
        label="False Positive Rate"
        value={formatPercent(metrics.false_positive_rate)}
        trend={metrics.false_positive_trend}
        icon={<Target className="w-5 h-5 text-yellow-400" />}
        color="text-yellow-400"
      />
    </div>
  );
}
