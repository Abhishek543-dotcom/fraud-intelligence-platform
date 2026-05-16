import { useState, useMemo } from 'react';
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
  Cell,
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { useModelMetrics } from '../hooks/useApi';
import { fetchModelVersions } from '../services/api';
import type { ModelVersion } from '../services/api';

const MODEL_TABS = ['All Models', 'XGBoost', 'Random Forest', 'Isolation Forest', 'Ensemble'] as const;
type ModelTab = (typeof MODEL_TABS)[number];

const TAB_TO_TYPE: Record<string, string> = {
  'XGBoost': 'xgboost',
  'Random Forest': 'random_forest',
  'Isolation Forest': 'isolation_forest',
  'Ensemble': 'ensemble',
};

const MODEL_COLORS: Record<string, string> = {
  xgboost: '#22c55e',
  random_forest: '#3b82f6',
  isolation_forest: '#a855f7',
  ensemble: '#eab308',
};

function MetricCell({ value, isBest }: { value: string; isBest: boolean }) {
  return (
    <td className={`px-3 py-2 text-sm text-right ${isBest ? 'text-green-400 font-bold' : 'text-gray-300'}`}>
      {value}
    </td>
  );
}

function ComparisonTable({ versions }: { versions: ModelVersion[] }) {
  const metrics = ['Precision', 'Recall', 'F1 Score', 'AUC-ROC', 'Latency (ms)'] as const;
  const keys: Record<string, keyof ModelVersion['metrics']> = {
    'Precision': 'precision',
    'Recall': 'recall',
    'F1 Score': 'f1_score',
    'AUC-ROC': 'auc_roc',
    'Latency (ms)': 'avg_latency_ms',
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 overflow-x-auto">
      <h2 className="text-sm font-semibold text-white mb-3">Model Comparison</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-700">
            <th className="text-left px-3 py-2 text-gray-400 font-medium">Metric</th>
            {versions.map((v) => (
              <th key={v.model_type} className="text-right px-3 py-2 text-gray-400 font-medium">
                <span style={{ color: MODEL_COLORS[v.model_type] || '#9ca3af' }}>
                  {v.model_type.replace('_', ' ')}
                </span>
                {v.status === 'active' && (
                  <span className="ml-2 text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded-full border border-green-500/30">
                    ACTIVE
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => {
            const key = keys[metric];
            const values = versions.map((v) => v.metrics[key]);
            // For latency, lower is better; for others, higher is better
            const bestVal = metric === 'Latency (ms)' ? Math.min(...values) : Math.max(...values);
            return (
              <tr key={metric} className="border-b border-gray-800/50">
                <td className="px-3 py-2 text-sm text-gray-400">{metric}</td>
                {versions.map((v) => {
                  const val = v.metrics[key];
                  const isPercent = metric !== 'Latency (ms)';
                  const display = isPercent ? `${(val * 100).toFixed(1)}%` : `${val.toFixed(0)}`;
                  return (
                    <MetricCell key={v.model_type} value={display} isBest={val === bestVal} />
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AucComparisonChart({ versions }: { versions: ModelVersion[] }) {
  const data = versions.map((v) => ({
    model: v.model_type.replace('_', ' '),
    auc_roc: +(v.metrics.auc_roc * 100).toFixed(1),
    color: MODEL_COLORS[v.model_type] || '#9ca3af',
  }));

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <h2 className="text-sm font-semibold text-white mb-4">AUC-ROC Comparison</h2>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="model" stroke="#6b7280" tick={{ fontSize: 11 }} />
          <YAxis domain={[80, 100]} stroke="#6b7280" tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
            labelStyle={{ color: '#9ca3af' }}
            formatter={(value: number) => [`${value}%`, 'AUC-ROC']}
          />
          <Bar dataKey="auc_roc" radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={index} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function ModelPerformance() {
  const [activeTab, setActiveTab] = useState<ModelTab>('All Models');
  const { data: metrics, isLoading } = useModelMetrics();
  const { data: modelVersions } = useQuery({
    queryKey: ['modelVersions'],
    queryFn: fetchModelVersions,
  });

  // Derive model versions from existing metrics if the /ml/models endpoint isn't available
  const versions: ModelVersion[] = useMemo(() => {
    if (modelVersions && modelVersions.length > 0) return modelVersions;
    // Synthesize from existing metrics data to avoid blank state
    if (!metrics || metrics.length === 0) return [];
    const typeMap = new Map<string, ModelVersion>();
    for (const m of metrics) {
      const modelType = m.model_version.toLowerCase().includes('xgboost')
        ? 'xgboost'
        : m.model_version.toLowerCase().includes('random')
          ? 'random_forest'
          : m.model_version.toLowerCase().includes('isolation')
            ? 'isolation_forest'
            : 'ensemble';
      if (!typeMap.has(modelType)) {
        typeMap.set(modelType, {
          model_type: modelType,
          version: m.model_version,
          status: typeMap.size === 0 ? 'active' : 'staged',
          metrics: {
            precision: m.precision,
            recall: m.recall,
            f1_score: m.f1_score,
            auc_roc: m.auc_roc,
            avg_latency_ms: m.avg_latency_ms,
          },
          timestamp: m.timestamp,
        });
      }
    }
    return Array.from(typeMap.values());
  }, [modelVersions, metrics]);

  const activeModel = versions.find((v) => v.status === 'active');

  // Filter metrics for individual model tabs
  const filteredMetrics = useMemo(() => {
    if (activeTab === 'All Models' || !metrics) return metrics;
    const typeKey = TAB_TO_TYPE[activeTab];
    if (!typeKey) return metrics;
    return metrics.filter(
      (m) => m.model_version.toLowerCase().replace(/[\s-]/g, '_').includes(typeKey),
    );
  }, [activeTab, metrics]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 h-80 animate-pulse" />
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 h-80 animate-pulse" />
      </div>
    );
  }

  const chartData = (filteredMetrics || []).map((m) => ({
    version: m.model_version,
    precision: +(m.precision * 100).toFixed(1),
    recall: +(m.recall * 100).toFixed(1),
    f1: +(m.f1_score * 100).toFixed(1),
    auc: +(m.auc_roc * 100).toFixed(1),
    latency: m.avg_latency_ms,
    predictions: m.total_predictions,
  }));

  const confusionData = filteredMetrics?.[0]
    ? [
        { name: 'True Positives', value: filteredMetrics[0].true_positives, fill: '#22c55e' },
        { name: 'False Positives', value: filteredMetrics[0].false_positives, fill: '#ef4444' },
        { name: 'True Negatives', value: filteredMetrics[0].true_negatives, fill: '#3b82f6' },
        { name: 'False Negatives', value: filteredMetrics[0].false_negatives, fill: '#f59e0b' },
      ]
    : [];

  return (
    <div className="space-y-6">
      {/* Model Selector Tabs */}
      <div className="flex items-center gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1">
        {MODEL_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm rounded-lg transition-colors ${
              activeTab === tab
                ? 'bg-gray-700 text-white font-medium'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Active Model Badge */}
      {activeModel && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-white">Active Production Model</h2>
              <span className="text-xs bg-green-500/20 text-green-400 px-2.5 py-1 rounded-full border border-green-500/30 font-medium">
                ACTIVE
              </span>
            </div>
            <span className="text-xs bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full border border-blue-500/30">
              {activeModel.version}
            </span>
          </div>
          <div className="grid grid-cols-5 gap-4 mt-3">
            <div>
              <p className="text-xs text-gray-500">Type</p>
              <p className="text-sm font-medium text-white">{activeModel.model_type.replace('_', ' ')}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Precision</p>
              <p className="text-lg font-bold text-green-400">{(activeModel.metrics.precision * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Recall</p>
              <p className="text-lg font-bold text-blue-400">{(activeModel.metrics.recall * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">F1 Score</p>
              <p className="text-lg font-bold text-purple-400">{(activeModel.metrics.f1_score * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">AUC-ROC</p>
              <p className="text-lg font-bold text-yellow-400">{(activeModel.metrics.auc_roc * 100).toFixed(1)}%</p>
            </div>
          </div>
        </div>
      )}

      {/* Comparison view (All Models tab) */}
      {activeTab === 'All Models' && versions.length > 0 && (
        <>
          <ComparisonTable versions={versions} />
          <AucComparisonChart versions={versions} />
        </>
      )}

      {/* Precision / Recall over versions */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-white mb-4">
          {activeTab === 'All Models' ? 'Model Performance Over Versions' : `${activeTab} Performance Over Versions`}
        </h2>
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
        <h2 className="text-sm font-semibold text-white mb-4">
          Confusion Matrix ({activeTab === 'All Models' ? 'Latest Model' : activeTab})
        </h2>
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
