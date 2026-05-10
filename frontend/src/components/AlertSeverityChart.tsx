import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend,
} from 'recharts';
import type { FraudAlert } from '../types';

interface AlertSeverityChartProps {
  alerts: FraudAlert[];
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#f87171',
  high: '#fb923c',
  medium: '#facc15',
  low: '#4ade80',
};

export default function AlertSeverityChart({ alerts }: AlertSeverityChartProps) {
  const severityCounts = alerts.reduce<Record<string, number>>((acc, alert) => {
    acc[alert.severity] = (acc[alert.severity] || 0) + 1;
    return acc;
  }, {});

  const pieData = Object.entries(severityCounts).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value,
    color: SEVERITY_COLORS[name] ?? '#9ca3af',
  }));

  // If no alerts yet, show placeholder data
  const displayData = pieData.length > 0 ? pieData : [
    { name: 'Critical', value: 12, color: '#f87171' },
    { name: 'High', value: 28, color: '#fb923c' },
    { name: 'Medium', value: 45, color: '#facc15' },
    { name: 'Low', value: 15, color: '#4ade80' },
  ];

  // Category breakdown
  const categoryCounts = alerts.reduce<Record<string, number>>((acc, alert) => {
    const cat = alert.category || 'Unknown';
    acc[cat] = (acc[cat] || 0) + 1;
    return acc;
  }, {});

  const topCategories = Object.entries(categoryCounts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  return (
    <div className="card">
      <span className="card-header">Alert Severity Distribution</span>
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={displayData}
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={90}
                paddingAngle={3}
                dataKey="value"
              >
                {displayData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: '#111827',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                }}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {topCategories.length > 0 && (
          <div className="w-48 space-y-2 pt-4">
            <div className="text-xs text-gray-500 uppercase tracking-wider mb-2">Top Categories</div>
            {topCategories.map(([cat, count]) => {
              const pct = alerts.length > 0 ? (count / alerts.length) * 100 : 0;
              return (
                <div key={cat}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-400">{cat}</span>
                    <span className="text-gray-500">{count}</span>
                  </div>
                  <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
