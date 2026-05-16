import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import clsx from 'clsx';
import type { FraudAlert } from '../types';

interface NotificationBellProps {
  alerts: FraudAlert[];
}

export default function NotificationBell({ alerts }: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  const ref = useRef<HTMLDivElement>(null);

  // Critical/high unresolved alerts
  const criticalAlerts = alerts.filter(
    (a) =>
      (a.severity === 'critical' || a.severity === 'high') &&
      a.status !== 'resolved' &&
      a.status !== 'false_positive',
  );
  const unreadCount = criticalAlerts.filter((a) => !readIds.has(a.alert_id)).length;
  const recentAlerts = criticalAlerts.slice(0, 5);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClick);
      return () => document.removeEventListener('mousedown', handleClick);
    }
  }, [open]);

  const markAllRead = () => {
    setReadIds(new Set(criticalAlerts.map((a) => a.alert_id)));
    setOpen(false);
  };

  const formatTime = (ts: string) => {
    const d = new Date(ts);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH}h ago`;
    return `${Math.floor(diffH / 24)}d ago`;
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
        aria-label="Notifications"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center w-4 h-4 text-[10px] font-bold text-white bg-red-500 rounded-full">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-2 w-80 bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-50">
          <div className="px-3 py-2 border-b border-gray-700">
            <h3 className="text-sm font-medium text-white">Notifications</h3>
          </div>

          {recentAlerts.length === 0 ? (
            <div className="px-3 py-6 text-center text-sm text-gray-500">
              No critical alerts
            </div>
          ) : (
            <ul className="max-h-72 overflow-y-auto divide-y divide-gray-800">
              {recentAlerts.map((alert) => (
                <li key={alert.alert_id} className="px-3 py-2.5 hover:bg-gray-800/50 transition-colors">
                  <div className="flex items-start gap-2">
                    <span
                      className={clsx(
                        'mt-0.5 flex-shrink-0 text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded',
                        alert.severity === 'critical' && 'bg-red-500/20 text-red-400',
                        alert.severity === 'high' && 'bg-orange-500/20 text-orange-400',
                      )}
                    >
                      {alert.severity}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-gray-200 truncate">
                        {alert.currency}{alert.amount.toLocaleString()} — {alert.merchant_name}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {formatTime(alert.created_at || alert.timestamp)}
                      </p>
                    </div>
                    <Link
                      to={`/alerts/${alert.alert_id}`}
                      className="flex-shrink-0 text-xs text-blue-400 hover:text-blue-300"
                      onClick={() => setOpen(false)}
                    >
                      View
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {recentAlerts.length > 0 && (
            <div className="px-3 py-2 border-t border-gray-700">
              <button
                onClick={markAllRead}
                className="w-full text-xs text-center text-gray-400 hover:text-white transition-colors"
              >
                Mark all read
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
