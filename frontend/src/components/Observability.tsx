import { useQuery } from '@tanstack/react-query';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import clsx from 'clsx';
import {
  fetchKafkaTopics,
  fetchKafkaThroughputHistory,
  fetchSparkState,
  fetchMinioState,
  fetchNessieState,
  fetchMlState,
  fetchSystemState,
} from '../services/api';
import { formatNumber } from '../utils/formatters';

function bytesToHuman(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={clsx(
        'inline-block w-2 h-2 rounded-full mr-2',
        ok ? 'bg-green-400' : 'bg-red-400',
      )}
    />
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-sm font-semibold text-white">{title}</h2>
        {subtitle && <span className="text-xs text-gray-500">{subtitle}</span>}
      </div>
      {children}
    </div>
  );
}

function SystemHealth() {
  const { data, isLoading } = useQuery({
    queryKey: ['observability-system'],
    queryFn: fetchSystemState,
    refetchInterval: 5_000,
  });
  if (isLoading || !data) return <Card title="System Health"><div className="h-32 animate-pulse bg-gray-800 rounded" /></Card>;
  const services = Object.entries(data.services);
  return (
    <Card title="System Health" subtitle={new Date(data.timestamp).toLocaleTimeString()}>
      <div className="grid grid-cols-2 gap-3">
        {services.map(([name, info]) => {
          const ok = info.status === 'healthy';
          return (
            <div key={name} className="flex items-center justify-between p-2 bg-gray-950 rounded">
              <span className="text-sm text-gray-300 capitalize">
                <StatusDot ok={ok} />
                {name}
              </span>
              <span className={clsx('text-xs', ok ? 'text-green-400' : 'text-red-400')}>
                {info.status}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function KafkaTopicsCard() {
  const { data, isLoading } = useQuery({
    queryKey: ['observability-kafka-topics'],
    queryFn: fetchKafkaTopics,
    refetchInterval: 5_000,
  });
  return (
    <Card title="Kafka Topics" subtitle="end offsets">
      {isLoading || !data ? (
        <div className="h-32 animate-pulse bg-gray-800 rounded" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left py-1">Topic</th>
                <th className="text-right py-1">Partitions</th>
                <th className="text-right py-1">Messages</th>
              </tr>
            </thead>
            <tbody>
              {data.map((t) => (
                <tr key={t.topic} className="border-b border-gray-800/50">
                  <td className="py-1 text-gray-300 font-mono">{t.topic}</td>
                  <td className="py-1 text-right text-gray-400">{t.partitions}</td>
                  <td className="py-1 text-right text-blue-300">{formatNumber(t.messages)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function KafkaThroughputCard() {
  const { data } = useQuery({
    queryKey: ['observability-kafka-throughput'],
    queryFn: fetchKafkaThroughputHistory,
    refetchInterval: 5_000,
  });
  const series = (data ?? []).map((p) => ({
    time: new Date(p.timestamp).toLocaleTimeString(),
    rate: p.total_per_sec,
  }));
  return (
    <Card title="Kafka Throughput" subtitle="msgs/sec, last 5 min">
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={series}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="time" stroke="#6b7280" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8 }}
            labelStyle={{ color: '#9ca3af' }}
          />
          <Area type="monotone" dataKey="rate" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.18} strokeWidth={2} name="msgs/sec" />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}

function SparkCard() {
  const { data, isLoading } = useQuery({
    queryKey: ['observability-spark'],
    queryFn: fetchSparkState,
    refetchInterval: 5_000,
  });
  return (
    <Card title="Spark Cluster" subtitle={data ? `status: ${data.status}` : ''}>
      {isLoading || !data ? (
        <div className="h-32 animate-pulse bg-gray-800 rounded" />
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 mb-3">
            <Stat label="Workers" value={`${data.alive_workers}/${data.workers}`} />
            <Stat label="Cores" value={`${data.cores_used}/${data.cores_total}`} />
            <Stat label="Active apps" value={String(data.active_apps)} />
          </div>
          {data.apps.length === 0 ? (
            <p className="text-xs text-gray-500">No active applications.</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left py-1">Name</th>
                  <th className="text-right py-1">State</th>
                  <th className="text-right py-1">Cores</th>
                </tr>
              </thead>
              <tbody>
                {data.apps.map((a) => (
                  <tr key={a.id} className="border-b border-gray-800/50">
                    <td className="py-1 text-gray-300 truncate max-w-[180px]">{a.name}</td>
                    <td className="py-1 text-right text-gray-400">{a.state}</td>
                    <td className="py-1 text-right text-blue-300">{a.cores}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </Card>
  );
}

function MinioCard() {
  const { data, isLoading } = useQuery({
    queryKey: ['observability-minio'],
    queryFn: fetchMinioState,
    refetchInterval: 10_000,
  });
  return (
    <Card title="MinIO Buckets" subtitle={data?.reachable ? 'online' : 'unreachable'}>
      {isLoading || !data ? (
        <div className="h-32 animate-pulse bg-gray-800 rounded" />
      ) : data.buckets.length === 0 ? (
        <p className="text-xs text-gray-500">No buckets yet.</p>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left py-1">Bucket</th>
              <th className="text-right py-1">Objects</th>
              <th className="text-right py-1">Size</th>
            </tr>
          </thead>
          <tbody>
            {data.buckets.map((b) => (
              <tr key={b.name} className="border-b border-gray-800/50">
                <td className="py-1 text-gray-300 font-mono">{b.name}</td>
                <td className="py-1 text-right text-gray-400">{formatNumber(b.objects)}</td>
                <td className="py-1 text-right text-blue-300">{bytesToHuman(b.size_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function NessieCard() {
  const { data, isLoading } = useQuery({
    queryKey: ['observability-nessie'],
    queryFn: fetchNessieState,
    refetchInterval: 10_000,
  });
  return (
    <Card title="Nessie / Iceberg Catalog" subtitle={data?.reachable ? 'online' : 'unreachable'}>
      {isLoading || !data ? (
        <div className="h-32 animate-pulse bg-gray-800 rounded" />
      ) : data.tables.length === 0 ? (
        <p className="text-xs text-gray-500">
          No tables yet (namespaces: {data.namespaces.length || 0}).
        </p>
      ) : (
        <ul className="space-y-1 text-xs">
          {data.tables.map((t) => (
            <li key={t.name} className="flex justify-between border-b border-gray-800/50 py-1">
              <span className="text-gray-300 font-mono">{t.name}</span>
              <span className="text-gray-500">{t.type}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function MlCard() {
  const { data, isLoading } = useQuery({
    queryKey: ['observability-ml'],
    queryFn: fetchMlState,
    refetchInterval: 5_000,
  });
  return (
    <Card title="ML Service" subtitle={data?.reachable ? 'online' : 'unreachable'}>
      {isLoading || !data ? (
        <div className="h-32 animate-pulse bg-gray-800 rounded" />
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Predictions" value={formatNumber(data.predictions_total)} />
          <Stat label="Fraud ratio" value={`${(data.fraud_ratio * 100).toFixed(1)}%`} />
          <Stat label="Latency p50" value={`${data.latency_p50_ms.toFixed(1)} ms`} />
          <Stat label="Latency p95" value={`${data.latency_p95_ms.toFixed(1)} ms`} />
        </div>
      )}
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-950 rounded p-2">
      <p className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-base font-semibold text-white mt-0.5">{value}</p>
    </div>
  );
}

export default function Observability() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-white">Observability</h1>
        <p className="text-sm text-gray-500">
          Live metrics from Kafka, Spark, MinIO, Nessie and the ML service. Refreshes every few seconds.
        </p>
      </div>
      <SystemHealth />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <KafkaThroughputCard />
        <KafkaTopicsCard />
        <SparkCard />
        <MlCard />
        <MinioCard />
        <NessieCard />
      </div>
    </div>
  );
}