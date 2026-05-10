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
import { fetchDashboardMetrics } from '../services/api';
import { useRef, useEffect, useState } from 'react';

interface ThroughputPoint {
  time: string;
  produced: number;
  consumed: number;
}

export default function KafkaThroughput() {
  const [dataPoints, setDataPoints] = useState<ThroughputPoint[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  // Simulate throughput data from metrics
  useEffect(() => {
    const generatePoint = (): ThroughputPoint => {
      const now = new Date();
      return {
        time: `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`,
        produced: Math.floor(Math.random() * 500 + 200),
        consumed: Math.floor(Math.random() * 480 + 180),
      };
    };

    // Seed initial data
    setDataPoints(Array.from({ length: 30 }, generatePoint));

    intervalRef.current = setInterval(() => {
      setDataPoints((prev) => {
        const next = [...prev, generatePoint()];
        return next.length > 60 ? next.slice(-60) : next;
      });
    }, 5000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-white">Kafka Throughput</h2>
        <span className="text-xs text-gray-500">msgs/sec</span>
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <AreaChart data={dataPoints}>
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
            name="Produced"
          />
          <Area
            type="monotone"
            dataKey="consumed"
            stroke="#22c55e"
            fill="#22c55e"
            fillOpacity={0.1}
            strokeWidth={2}
            name="Consumed"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
