import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  AlertTriangle,
  ArrowLeftRight,
  MessageSquare,
  Brain,
  Shield,
  Activity,
  Database,
} from 'lucide-react';
import clsx from 'clsx';
import type { ConnectionState } from '../types';

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/alerts', label: 'Alerts', icon: AlertTriangle },
  { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
  { to: '/observability', label: 'Observability', icon: Activity },
  { to: '/investigations', label: 'Investigations', icon: MessageSquare },
  { to: '/models', label: 'Models', icon: Brain },
  { to: '/sql', label: 'SQL Editor', icon: Database },
];

interface LayoutProps {
  children: React.ReactNode;
  connectionState: ConnectionState;
  alertCount: number;
}

export default function Layout({ children, connectionState, alertCount }: LayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center gap-2 min-w-0">
            <Shield className="w-8 h-8 text-blue-400 flex-shrink-0" />
            <div className="min-w-0">
              <h1 className="text-sm font-bold text-white truncate">Fraud Intelligence</h1>
              <p className="text-xs text-gray-500 truncate">Real-Time Platform</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-blue-500/10 text-blue-400 font-medium'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800',
                )
              }
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              <span className="truncate">{label}</span>
              {label === 'Alerts' && alertCount > 0 && (
                <span className="ml-auto bg-red-500/20 text-red-400 text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0">
                  {alertCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-gray-800">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span
              className={clsx(
                'w-2 h-2 rounded-full flex-shrink-0',
                connectionState === 'connected' && 'bg-green-400 animate-pulse-live',
                connectionState === 'connecting' && 'bg-yellow-400 animate-pulse',
                connectionState === 'disconnected' && 'bg-red-400',
              )}
            />
            <span className="capitalize truncate">{connectionState}</span>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 min-w-0 overflow-y-auto bg-gray-950 p-6">{children}</main>
    </div>
  );
}
