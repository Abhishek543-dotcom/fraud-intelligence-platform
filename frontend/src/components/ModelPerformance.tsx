import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts';
import { useModelMetrics } from '../hooks/useApi';

export default function ModelPerformance() {
  const { data: metrics, isLoading } = useModelMetrics();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 h-80 animate-pulse" />
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 h-80 animate-pulse" />
      </div>
    );
  }

  const chartData = (metrics || []).map((m) => ({
    version: m.model_version,
    precision: +(m.precision * 100).toFixed(1),
    recall: +(m.recall * 100).toFixed(1),
    f1: +(m.f1_score * 100).toFixed(1),
    auc: +(m.auc_roc * 100).toFixed(1),
    latency: m.avg_latency_ms,
    predictions: m.total_predictions,
  }));

  const confusionData = metrics?.[0]
    ? [
        { name: 'True Positives', value: metrics[0].true_positives, fill: '#22c55e' },
        { name: 'False Positives', value: metrics[0].false_positives, fill: '#ef4444' },
        { name: 'True Negatives', value: metrics[0].true_negatives, fill: '#3b82f6' },
        { name: 'False Negatives', value: metrics[0].false_negatives, fill: '#f59e0b' },
      ]
    : [];

  return (
    <div className="space-y-6">
      {/* Current Model Info */}
      {metrics?.[0] && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-white">Current Model</h2>
            <span className="text-xs bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full border border-blue-500/30">
              {metrics[0].model_version}
            </span>
          </div>
          <div className="grid grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-gray-500">Precision</p>
              <p className="text-lg font-bold text-green-400">
                {(metrics[0].precision * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Recall</p>
              <p className="text-lg font-bold text-blue-400">
                {(metrics[0].recall * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">F1 Score</p>
              <p className="text-lg font-bold text-purple-400">
                {(metrics[0].f1_score * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">AUC-ROC</p>
              <p className="text-lg font-bold text-yellow-400">
                {(metrics[0].auc_roc * 100).toFixed(1)}%
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Precision / Recall over versions */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-white mb-4">Model Performance Over Versions</h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="version" stroke="#6b7280" tick={{ fontSize: 11 }} />
            <YAxis domain={[0, 100]} stroke="#6b7280" tick={{ fontSize: 11 }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
              labelStyle={{ color: '#9ca3af' }}
            />
            <Legend />
            <Line type="monotone" dataKey="precision" stroke="#22c55e" strokeWidth={2} dot={{ r: 3 }} />
            <Line type="monotone" dataKey="recall" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
            <Line type="monotone" dataKey="f1" stroke="#a855f7" strokeWidth={2} dot={{ r: 3 }} />
            <Line type="monotone" dataKey="auc" stroke="#eab308" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Confusion Matrix as Bar Chart */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-white mb-4">Confusion Matrix (Latest Model)</h2>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={confusionData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis type="number" stroke="#6b7280" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" stroke="#6b7280" tick={{ fontSize: 11 }} width={120} />
            <Tooltip
              contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
