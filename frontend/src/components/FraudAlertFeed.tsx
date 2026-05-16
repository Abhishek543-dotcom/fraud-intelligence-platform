import { useRef, useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Wifi, WifiOff, Pause, Play, ExternalLink } from 'lucide-react';
import clsx from 'clsx';
import { formatCurrency, formatTimestamp, severityColor, severityBg } from '../utils/formatters';
import type { FraudAlert, ConnectionState } from '../types';

interface FraudAlertFeedProps {
  alerts: FraudAlert[];
  connectionState: ConnectionState;
  isPaused?: boolean;
  onPause?: () => void;
  onResume?: () => void;
  fullPage?: boolean;
}

export default function FraudAlertFeed({
  alerts,
  connectionState,
  isPaused = false,
  onPause,
  onResume,
  fullPage = false,
}: FraudAlertFeedProps) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isPaused && listRef.current) {
      listRef.current.scrollTop = 0;
    }
  }, [alerts, isPaused]);

  const handleTogglePause = () => {
    if (isPaused) {
      onResume?.();
    } else {
      onPause?.();
    }
  };

  const statusIcon = connectionState === 'connected' ? (
    <Wifi className="w-3 h-3 text-green-400" />
  ) : (
    <WifiOff className="w-3 h-3 text-red-400" />
  );

  return (
    <div className={clsx('card flex flex-col', fullPage ? 'h-[calc(100vh-6rem)]' : 'h-[420px]')}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="card-header mb-0">Live Fraud Alerts</span>
          {statusIcon}
          <span className="text-xs text-gray-500">({alerts.length})</span>
        </div>
        <button
          onClick={handleTogglePause}
          className="p-1 hover:bg-gray-800 rounded transition-colors"
          title={isPaused ? 'Resume auto-scroll' : 'Pause auto-scroll'}
        >
          {isPaused ? <Play className="w-3 h-3 text-gray-400" /> : <Pause className="w-3 h-3 text-gray-400" />}
        </button>
      </div>

      <div
        ref={listRef}
        className="flex-1 overflow-y-auto space-y-2"
      >
        {alerts.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm">
            Waiting for alerts...
          </div>
        ) : (
          alerts.map((alert) => (
            <AlertCard key={alert.alert_id} alert={alert} />
          ))
        )}
      </div>
    </div>
  );
}

function AlertCard({ alert }: { alert: FraudAlert }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={clsx(
        'border rounded-lg p-3 transition-colors',
        severityBg(alert.severity),
      )}
    >
      <div className="flex items-center justify-between cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center gap-2">
          <span className={clsx('text-xs font-bold px-1.5 py-0.5 rounded', severityColor(alert.severity))}>
            {alert.severity.toUpperCase()}
          </span>
          <span className="text-xs text-gray-400 font-mono">{alert.transaction_id.slice(0, 12)}</span>
        </div>
        <span className="text-xs text-gray-500">{formatTimestamp(alert.timestamp)}</span>
      </div>
      <div className="flex items-center justify-between mt-2">
        <span className="text-sm font-medium text-white">{formatCurrency(alert.amount)}</span>
        <span className="text-sm text-gray-400">{alert.merchant_name}</span>
        <span className="text-xs font-mono text-gray-300">
          Score: {(alert.fraud_score * 100).toFixed(0)}%
        </span>
      </div>
      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-700 text-xs space-y-1">
          <div className="flex justify-between">
            <span className="text-gray-500">Customer:</span>
            <span className="font-mono">{alert.customer_id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Category:</span>
            <span>{alert.category}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Status:</span>
            <span>{alert.status}</span>
          </div>
          {alert.description && (
            <p className="text-gray-400 mt-1">{alert.description}</p>
          )}
          <Link
            to={`/alerts/${alert.alert_id}`}
            className="flex items-center gap-1 mt-2 text-blue-400 hover:text-blue-300 transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            View Details
          </Link>
        </div>
      )}
    </div>
  );
}
