import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import MetricsPanel from './components/MetricsPanel';
import FraudAlertFeed from './components/FraudAlertFeed';
import GeoHeatmap from './components/GeoHeatmap';
import TransactionTable from './components/TransactionTable';
import ModelPerformance from './components/ModelPerformance';
import InvestigationChat from './components/InvestigationChat';
import KafkaThroughput from './components/KafkaThroughput';
import AlertSeverityChart from './components/AlertSeverityChart';
import Observability from './components/Observability';
import SqlEditor from './components/SqlEditor';
import { useFraudAlerts } from './hooks/useFraudAlerts';
import { useWebSocket } from './hooks/useWebSocket';
import type { ConnectionState } from './types';
import { useState } from 'react';

function Dashboard({
  connectionState,
  alerts,
  isPaused,
  onPause,
  onResume,
}: {
  connectionState: ConnectionState;
  alerts: ReturnType<typeof useFraudAlerts>['alerts'];
  isPaused: boolean;
  onPause: () => void;
  onResume: () => void;
}) {
  return (
    <div className="space-y-6">
      <MetricsPanel />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <FraudAlertFeed
          alerts={alerts}
          isPaused={isPaused}
          onPause={onPause}
          onResume={onResume}
          connectionState={connectionState}
        />
        <GeoHeatmap alerts={alerts} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <KafkaThroughput />
        <AlertSeverityChart alerts={alerts} />
      </div>
    </div>
  );
}

export default function App() {
  const fraudAlerts = useFraudAlerts();
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');

  useWebSocket({
    onMessage: fraudAlerts.handleMessage,
    onConnect: () => setConnectionState('connected'),
    onDisconnect: () => setConnectionState('disconnected'),
  });

  return (
    <Layout connectionState={connectionState} alertCount={fraudAlerts.alerts.length}>
      <Routes>
        <Route
          path="/"
          element={
            <Dashboard
              connectionState={connectionState}
              alerts={fraudAlerts.alerts}
              isPaused={fraudAlerts.isPaused}
              onPause={fraudAlerts.pause}
              onResume={fraudAlerts.resume}
            />
          }
        />
        <Route
          path="/alerts"
          element={
            <FraudAlertFeed
              alerts={fraudAlerts.alerts}
              isPaused={fraudAlerts.isPaused}
              onPause={fraudAlerts.pause}
              onResume={fraudAlerts.resume}
              connectionState={connectionState}
              fullPage
            />
          }
        />
        <Route path="/transactions" element={<TransactionTable />} />
        <Route path="/observability" element={<Observability />} />
        <Route path="/investigations" element={<InvestigationChat />} />
        <Route path="/models" element={<ModelPerformance />} />
        <Route path="/sql" element={<SqlEditor />} />
      </Routes>
    </Layout>
  );
}
