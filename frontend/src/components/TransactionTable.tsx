import { useState } from 'react';
import { Search, ChevronUp, ChevronDown, Download } from 'lucide-react';
import clsx from 'clsx';
import { useTransactions } from '../hooks/useApi';
import { formatCurrency, formatDate, scoreColor } from '../utils/formatters';
import type { FilterParams } from '../types';

export default function TransactionTable() {
  const [filters, setFilters] = useState<FilterParams>({
    page: 1,
    page_size: 50,
    sort_by: 'timestamp',
    sort_order: 'desc',
  });
  const [searchQuery, setSearchQuery] = useState('');
  const { data, isLoading } = useTransactions({ ...filters, search: searchQuery });

  const handleSort = (column: string) => {
    setFilters((prev) => ({
      ...prev,
      sort_by: column,
      sort_order: prev.sort_by === column && prev.sort_order === 'desc' ? 'asc' : 'desc',
    }));
  };

  const SortIcon = ({ column }: { column: string }) => {
    if (filters.sort_by !== column) return null;
    return filters.sort_order === 'desc' ? (
      <ChevronDown className="w-3 h-3" />
    ) : (
      <ChevronUp className="w-3 h-3" />
    );
  };

  const columns = [
    { key: 'timestamp', label: 'Time' },
    { key: 'amount', label: 'Amount' },
    { key: 'customer_name', label: 'Customer' },
    { key: 'merchant_name', label: 'Merchant' },
    { key: 'fraud_score', label: 'Score' },
    { key: 'status', label: 'Status' },
  ];

  const handleExportCSV = () => {
    if (!data?.data) return;
    const headers = ['Transaction ID', 'Timestamp', 'Amount', 'Customer', 'Merchant', 'Score', 'Status'];
    const rows = data.data.map((t) => [
      t.transaction_id,
      t.timestamp,
      t.amount,
      t.customer_name,
      t.merchant_name,
      t.fraud_score,
      t.status,
    ]);
    const csv = [headers, ...rows].map((row) => row.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transactions-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <h2 className="text-sm font-semibold text-white">Transactions</h2>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search by customer, merchant..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 w-64"
            />
          </div>
          <button
            onClick={handleExportCSV}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-300 hover:bg-gray-700 transition-colors"
          >
            <Download className="w-4 h-4" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-300"
                >
                  <div className="flex items-center gap-1">
                    {col.label}
                    <SortIcon column={col.key} />
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {isLoading ? (
              [...Array(10)].map((_, i) => (
                <tr key={i}>
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-3">
                      <div className="h-4 bg-gray-800 rounded animate-pulse" />
                    </td>
                  ))}
                </tr>
              ))
            ) : data?.data?.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-gray-600">
                  No transactions found
                </td>
              </tr>
            ) : (
              data?.data?.map((txn) => (
                <tr
                  key={txn.transaction_id}
                  className="hover:bg-gray-800/50 transition-colors cursor-pointer"
                >
                  <td className="px-4 py-3 text-gray-400">{formatDate(txn.timestamp)}</td>
                  <td className="px-4 py-3 text-white font-medium">
                    {formatCurrency(txn.amount, txn.currency)}
                  </td>
                  <td className="px-4 py-3 text-gray-300">{txn.customer_name}</td>
                  <td className="px-4 py-3 text-gray-300">{txn.merchant_name}</td>
                  <td className={clsx('px-4 py-3 font-mono font-bold', scoreColor(txn.fraud_score))}>
                    {(txn.fraud_score * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={clsx(
                        'text-xs px-2 py-0.5 rounded-full border',
                        txn.status === 'approved' && 'bg-green-500/10 border-green-500/30 text-green-400',
                        txn.status === 'declined' && 'bg-red-500/10 border-red-500/30 text-red-400',
                        txn.status === 'flagged' && 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400',
                        txn.status === 'pending' && 'bg-gray-500/10 border-gray-500/30 text-gray-400',
                      )}
                    >
                      {txn.status}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-800">
          <span className="text-xs text-gray-500">
            Page {data.page} of {data.total_pages} ({data.total} total)
          </span>
          <div className="flex gap-1">
            <button
              disabled={data.page <= 1}
              onClick={() => setFilters((p) => ({ ...p, page: (p.page || 1) - 1 }))}
              className="px-3 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              disabled={data.page >= data.total_pages}
              onClick={() => setFilters((p) => ({ ...p, page: (p.page || 1) + 1 }))}
              className="px-3 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
