import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { fetchKafkaThroughputHistory } from '../services/api';

export default function KafkaThroughput() {
  const { data } = useQuery({
    queryKey: ['kafka-throughput'],
    queryFn: fetchKafkaThroughputHistory,
    refetchInterval: 5_000,
  });

  const series = (data ?? []).map((p) => {
    const d = new Date(p.timestamp);
    return {
      time: `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`,
      produced: p.topics?.transactions_raw ?? 0,
      enriched: p.topics?.transactions_enriched ?? 0,
    };
  });

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-white">Kafka Throughput</h2>
        <span className="text-xs text-gray-500">msgs/sec</span>
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <AreaChart data={series}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="time" stroke="#6b7280" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#111827',
              border: '1px solid #374151',
              borderRadius: '8px',
            }}
            labelStyle={{ color: '#9ca3af' }}
          />
          <Area
            type="monotone"
            dataKey="produced"
            stroke="#3b82f6"
            fill="#3b82f6"
            fillOpacity={0.15}
            strokeWidth={2}
            name="transactions_raw"
          />
          <Area
            type="monotone"
            dataKey="enriched"
            stroke="#22c55e"
            fill="#22c55e"
            fillOpacity={0.1}
            strokeWidth={2}
            name="transactions_enriched"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
