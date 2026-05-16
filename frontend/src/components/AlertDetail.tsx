import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Shield,
  User,
  Clock,
  MapPin,
  CreditCard,
  Send,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ArrowUpCircle,
  Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import {
  fetchAlert,
  fetchAlertCase,
  assignAlert,
  addAlertNote,
  updateAlertStatus,
} from '../services/api';

const ANALYSTS = ['Analyst 1', 'Analyst 2', 'Senior Investigator', 'Team Lead'];

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400 border-red-500/30',
  high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  low: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
};

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-red-500/20 text-red-400',
  investigating: 'bg-yellow-500/20 text-yellow-400',
  resolved: 'bg-green-500/20 text-green-400',
  false_positive: 'bg-gray-500/20 text-gray-400',
};

interface CaseNote {
  text: string;
  timestamp: string;
  author?: string;
}

interface StatusHistoryEntry {
  status: string;
  timestamp: string;
}

interface AlertCase {
  assigned_to: string | null;
  notes: CaseNote[];
  status_history: StatusHistoryEntry[];
}

export default function AlertDetail() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [noteText, setNoteText] = useState('');

  const { data: alert, isLoading: alertLoading } = useQuery({
    queryKey: ['alert', id],
    queryFn: () => fetchAlert(id!),
    enabled: !!id,
  });

  const { data: caseData, isLoading: caseLoading } = useQuery({
    queryKey: ['alertCase', id],
    queryFn: () => fetchAlertCase(id!),
    enabled: !!id,
  });

  const assignMutation = useMutation({
    mutationFn: (assignedTo: string) => assignAlert(id!, assignedTo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alertCase', id] });
    },
  });

  const noteMutation = useMutation({
    mutationFn: (text: string) => addAlertNote(id!, text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alertCase', id] });
      setNoteText('');
    },
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => updateAlertStatus(id!, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert', id] });
      queryClient.invalidateQueries({ queryKey: ['alertCase', id] });
    },
  });

  if (alertLoading || caseLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 animate-spin text-blue-400" />
      </div>
    );
  }

  if (!alert) {
    return (
      <div className="text-center text-gray-400 py-20">
        <p>Alert not found.</p>
        <Link to="/alerts" className="text-blue-400 hover:underline mt-2 inline-block">
          Back to alerts
        </Link>
      </div>
    );
  }

  const alertCase: AlertCase = caseData || { assigned_to: null, notes: [], status_history: [] };
  const features = alert.features || {};

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Back link */}
      <Link to="/alerts" className="inline-flex items-center gap-2 text-gray-400 hover:text-white text-sm">
        <ArrowLeft className="w-4 h-4" />
        Back to Alerts
      </Link>

      {/* Header */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <Shield className="w-8 h-8 text-red-400" />
            <div>
              <h1 className="text-xl font-bold text-white">Alert {alert.alert_id}</h1>
              <p className="text-gray-400 text-sm mt-1">Transaction {alert.transaction_id}</p>
            </div>
            <span
              className={clsx(
                'px-3 py-1 rounded-full text-xs font-medium border',
                SEVERITY_COLORS[alert.severity] || SEVERITY_COLORS.medium,
              )}
            >
              {alert.severity.toUpperCase()}
            </span>
            <span
              className={clsx(
                'px-3 py-1 rounded-full text-xs font-medium',
                STATUS_COLORS[alert.status] || STATUS_COLORS.open,
              )}
            >
              {alert.status.replace('_', ' ').toUpperCase()}
            </span>
          </div>
          <div className="text-right text-sm text-gray-400">
            <div className="flex items-center gap-1 justify-end">
              <Clock className="w-3.5 h-3.5" />
              {new Date(alert.timestamp).toLocaleString()}
            </div>
          </div>
        </div>

        {/* Key metrics row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6">
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-500 uppercase">Amount</p>
            <p className="text-lg font-bold text-white">${alert.amount.toLocaleString()}</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-500 uppercase">Fraud Score</p>
            <p className="text-lg font-bold text-red-400">{(alert.fraud_score * 100).toFixed(1)}%</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-500 uppercase">Customer</p>
            <p className="text-sm font-medium text-white flex items-center gap-1">
              <User className="w-3.5 h-3.5 text-gray-500" />
              {alert.customer_name}
            </p>
            <p className="text-xs text-gray-500">{alert.customer_id}</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-500 uppercase">Location</p>
            <p className="text-sm font-medium text-white flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5 text-gray-500" />
              {alert.country}
            </p>
            <p className="text-xs text-gray-500 flex items-center gap-1">
              <CreditCard className="w-3 h-3" />
              {alert.channel} &middot; {alert.merchant_name}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: Assignment + Actions + Features */}
        <div className="lg:col-span-1 space-y-6">
          {/* Case Assignment */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
              Case Assignment
            </h2>
            <select
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={alertCase.assigned_to || ''}
              onChange={(e) => assignMutation.mutate(e.target.value)}
              disabled={assignMutation.isPending}
            >
              <option value="">Unassigned</option>
              {ANALYSTS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            {assignMutation.isPending && (
              <p className="text-xs text-gray-500 mt-1">Assigning...</p>
            )}
          </div>

          {/* Status Actions */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
              Actions
            </h2>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => statusMutation.mutate('resolved')}
                disabled={statusMutation.isPending}
                className="flex items-center justify-center gap-1.5 px-3 py-2 bg-green-500/10 hover:bg-green-500/20 text-green-400 text-xs font-medium rounded-lg border border-green-500/20 transition-colors"
              >
                <CheckCircle className="w-3.5 h-3.5" />
                True Positive
              </button>
              <button
                onClick={() => statusMutation.mutate('false_positive')}
                disabled={statusMutation.isPending}
                className="flex items-center justify-center gap-1.5 px-3 py-2 bg-gray-500/10 hover:bg-gray-500/20 text-gray-400 text-xs font-medium rounded-lg border border-gray-500/20 transition-colors"
              >
                <XCircle className="w-3.5 h-3.5" />
                False Positive
              </button>
              <button
                onClick={() => statusMutation.mutate('investigating')}
                disabled={statusMutation.isPending}
                className="flex items-center justify-center gap-1.5 px-3 py-2 bg-yellow-500/10 hover:bg-yellow-500/20 text-yellow-400 text-xs font-medium rounded-lg border border-yellow-500/20 transition-colors"
              >
                <AlertTriangle className="w-3.5 h-3.5" />
                Escalate
              </button>
              <button
                onClick={() => statusMutation.mutate('resolved')}
                disabled={statusMutation.isPending}
                className="flex items-center justify-center gap-1.5 px-3 py-2 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 text-xs font-medium rounded-lg border border-blue-500/20 transition-colors"
              >
                <ArrowUpCircle className="w-3.5 h-3.5" />
                Resolve
              </button>
            </div>
          </div>

          {/* Feature Breakdown */}
          {Object.keys(features).length > 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
                Feature Breakdown
              </h2>
              <div className="space-y-3">
                {Object.entries(features).map(([key, value]) => {
                  const normalized = Math.min(Math.abs(value) / 5, 1);
                  return (
                    <div key={key}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-400">{key}</span>
                        <span className="text-white font-mono">{value.toFixed(3)}</span>
                      </div>
                      <div className="w-full bg-gray-800 rounded-full h-1.5">
                        <div
                          className={clsx(
                            'h-1.5 rounded-full',
                            normalized > 0.7 ? 'bg-red-500' : normalized > 0.4 ? 'bg-yellow-500' : 'bg-blue-500',
                          )}
                          style={{ width: `${normalized * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Right column: Notes + Timeline */}
        <div className="lg:col-span-2 space-y-6">
          {/* Investigation Notes */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
              Investigation Notes
            </h2>
            <div className="flex gap-2 mb-4">
              <textarea
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                rows={3}
                placeholder="Add an investigation note..."
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.metaKey && noteText.trim()) {
                    noteMutation.mutate(noteText.trim());
                  }
                }}
              />
              <button
                onClick={() => noteText.trim() && noteMutation.mutate(noteText.trim())}
                disabled={!noteText.trim() || noteMutation.isPending}
                className="self-end px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded-lg transition-colors flex items-center gap-1.5"
              >
                {noteMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                Add
              </button>
            </div>

            {alertCase.notes.length === 0 ? (
              <p className="text-gray-500 text-sm">No notes yet.</p>
            ) : (
              <div className="space-y-3 max-h-80 overflow-y-auto">
                {[...alertCase.notes].reverse().map((note, i) => (
                  <div key={i} className="bg-gray-800/50 rounded-lg p-3">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-xs text-gray-400">{note.author || 'Analyst'}</span>
                      <span className="text-xs text-gray-500">
                        {new Date(note.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-sm text-gray-200 whitespace-pre-wrap">{note.text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Timeline */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
              Status Timeline
            </h2>
            {alertCase.status_history.length === 0 ? (
              <p className="text-gray-500 text-sm">No status changes recorded.</p>
            ) : (
              <div className="relative pl-6 space-y-4">
                <div className="absolute left-2 top-1 bottom-1 w-px bg-gray-700" />
                {alertCase.status_history.map((entry, i) => (
                  <div key={i} className="relative">
                    <div
                      className={clsx(
                        'absolute -left-4 top-1 w-3 h-3 rounded-full border-2 border-gray-900',
                        entry.status === 'resolved'
                          ? 'bg-green-500'
                          : entry.status === 'false_positive'
                          ? 'bg-gray-500'
                          : entry.status === 'investigating'
                          ? 'bg-yellow-500'
                          : 'bg-red-500',
                      )}
                    />
                    <div>
                      <span
                        className={clsx(
                          'text-xs font-medium px-2 py-0.5 rounded',
                          STATUS_COLORS[entry.status] || STATUS_COLORS.open,
                        )}
                      >
                        {entry.status.replace('_', ' ').toUpperCase()}
                      </span>
                      <p className="text-xs text-gray-500 mt-1">
                        {new Date(entry.timestamp).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
