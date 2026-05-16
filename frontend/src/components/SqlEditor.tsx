import { useState, useCallback, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  Play,
  Database,
  Table2,
  ChevronRight,
  ChevronDown,
  Loader2,
  AlertCircle,
  Clock,
  Rows3,
  Download,
  Save,
  History,
  Bookmark,
  X,
} from 'lucide-react';
import clsx from 'clsx';
import {
  fetchIcebergTables,
  fetchTableSchema,
  executeSQL,
} from '../services/api';
import type { IcebergTableInfo, SqlQueryResult } from '../services/api';

// ---------------------------------------------------------------------------
// LocalStorage helpers
// ---------------------------------------------------------------------------

interface SavedQuery {
  name: string;
  sql: string;
  savedAt: string;
}

interface HistoryEntry {
  sql: string;
  timestamp: string;
  rowCount?: number;
}

const HISTORY_KEY = 'sql-editor-history';
const SAVED_KEY = 'sql-editor-saved';
const MAX_HISTORY = 20;

function getHistory(): HistoryEntry[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  } catch {
    return [];
  }
}

function addToHistory(entry: HistoryEntry) {
  const history = getHistory();
  history.unshift(entry);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, MAX_HISTORY)));
}

function getSavedQueries(): SavedQuery[] {
  try {
    return JSON.parse(localStorage.getItem(SAVED_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveQuery(query: SavedQuery) {
  const saved = getSavedQueries();
  saved.unshift(query);
  localStorage.setItem(SAVED_KEY, JSON.stringify(saved));
}

function deleteSavedQuery(index: number) {
  const saved = getSavedQueries();
  saved.splice(index, 1);
  localStorage.setItem(SAVED_KEY, JSON.stringify(saved));
}

// ---------------------------------------------------------------------------
// Export helpers
// ---------------------------------------------------------------------------

function downloadFile(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportCSV(result: SqlQueryResult) {
  const header = result.columns.join(',');
  const rows = result.rows.map((row) =>
    row.map((cell) => {
      const str = cell === null ? '' : String(cell);
      return str.includes(',') || str.includes('"') || str.includes('\n')
        ? `"${str.replace(/"/g, '""')}"`
        : str;
    }).join(','),
  );
  downloadFile([header, ...rows].join('\n'), 'query_results.csv', 'text/csv');
}

function exportJSON(result: SqlQueryResult) {
  const objects = result.rows.map((row) =>
    Object.fromEntries(result.columns.map((col, i) => [col, row[i]])),
  );
  downloadFile(JSON.stringify(objects, null, 2), 'query_results.json', 'application/json');
}

// ---------------------------------------------------------------------------
// Table Tree Sidebar
// ---------------------------------------------------------------------------

function NamespaceNode({
  namespace,
  tables,
  onSelectTable,
}: {
  namespace: string;
  tables: IcebergTableInfo[];
  onSelectTable: (table: IcebergTableInfo) => void;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 w-full px-2 py-1.5 text-sm text-gray-300 hover:bg-gray-800 rounded transition-colors"
      >
        {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Database className="w-3.5 h-3.5 text-blue-400" />
        <span className="font-medium">{namespace}</span>
        <span className="ml-auto text-xs text-gray-500">{tables.length}</span>
      </button>
      {expanded && (
        <div className="ml-4">
          {tables.map((t) => (
            <TableNode key={t.full_name} table={t} onSelect={onSelectTable} />
          ))}
        </div>
      )}
    </div>
  );
}

function TableNode({
  table,
  onSelect,
}: {
  table: IcebergTableInfo;
  onSelect: (table: IcebergTableInfo) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const { data: schema, isLoading } = useQuery({
    queryKey: ['table-schema', table.namespace, table.name],
    queryFn: () => fetchTableSchema(table.namespace, table.name),
    enabled: expanded,
  });

  return (
    <div>
      <div className="flex items-center">
        <button
          onClick={() => setExpanded(!expanded)}
          className="p-0.5 text-gray-500 hover:text-gray-300"
        >
          {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        </button>
        <button
          onClick={() => onSelect(table)}
          className="flex items-center gap-1.5 flex-1 px-1 py-1 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors truncate"
          title={`Click to query ${table.full_name}`}
        >
          <Table2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
          <span className="truncate">{table.name}</span>
        </button>
      </div>
      {expanded && (
        <div className="ml-6 border-l border-gray-800 pl-2">
          {isLoading && (
            <div className="flex items-center gap-1 py-1 text-xs text-gray-500">
              <Loader2 className="w-3 h-3 animate-spin" />
              Loading...
            </div>
          )}
          {schema?.columns.map((col) => (
            <div
              key={col.name}
              className="flex items-center justify-between py-0.5 text-xs text-gray-500"
            >
              <span className="truncate">{col.name}</span>
              <span className="text-gray-600 ml-2 flex-shrink-0">{col.type}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Results Table
// ---------------------------------------------------------------------------

function ResultsTable({ result }: { result: SqlQueryResult }) {
  return (
    <div className="overflow-auto flex-1">
      <table className="w-full text-sm border-collapse">
        <thead className="sticky top-0 bg-gray-900 z-10">
          <tr>
            {result.columns.map((col) => (
              <th
                key={col}
                className="text-left px-3 py-2 text-xs font-medium text-gray-400 border-b border-gray-800 whitespace-nowrap"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, i) => (
            <tr
              key={i}
              className={clsx(
                'hover:bg-gray-800/50 transition-colors',
                i % 2 === 0 ? 'bg-gray-950' : 'bg-gray-900/30',
              )}
            >
              {row.map((cell, j) => (
                <td
                  key={j}
                  className="px-3 py-1.5 text-gray-300 border-b border-gray-800/50 whitespace-nowrap max-w-[300px] truncate"
                  title={String(cell ?? 'NULL')}
                >
                  {cell === null ? (
                    <span className="text-gray-600 italic">NULL</span>
                  ) : (
                    String(cell)
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function SqlEditor() {
  const [sql, setSql] = useState('');
  const [result, setResult] = useState<SqlQueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>(getHistory);
  const [saved, setSaved] = useState<SavedQuery[]>(getSavedQueries);
  const [showHistory, setShowHistory] = useState(false);
  const [showSaved, setShowSaved] = useState(true);

  const { data: tables, isLoading: tablesLoading } = useQuery({
    queryKey: ['iceberg-tables'],
    queryFn: fetchIcebergTables,
    refetchInterval: 30_000,
  });

  const mutation = useMutation({
    mutationFn: (query: string) => executeSQL(query),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      const entry: HistoryEntry = { sql: sql.trim(), timestamp: new Date().toISOString(), rowCount: data.row_count };
      addToHistory(entry);
      setHistory(getHistory());
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || err.message);
      setResult(null);
      addToHistory({ sql: sql.trim(), timestamp: new Date().toISOString() });
      setHistory(getHistory());
    },
  });

  const handleRun = useCallback(() => {
    if (!sql.trim()) return;
    mutation.mutate(sql);
  }, [sql, mutation]);

  const handleTableSelect = useCallback((table: IcebergTableInfo) => {
    setSql(`SELECT *\nFROM ${table.name}\nLIMIT 100`);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        handleRun();
      }
    },
    [handleRun],
  );

  const handleSave = useCallback(() => {
    if (!sql.trim()) return;
    const name = window.prompt('Query name:');
    if (!name) return;
    const q: SavedQuery = { name, sql: sql.trim(), savedAt: new Date().toISOString() };
    saveQuery(q);
    setSaved(getSavedQueries());
  }, [sql]);

  const handleDeleteSaved = useCallback((index: number) => {
    deleteSavedQuery(index);
    setSaved(getSavedQueries());
  }, []);

  // Group tables by namespace
  const grouped = (tables || []).reduce<Record<string, IcebergTableInfo[]>>((acc, t) => {
    (acc[t.namespace] ||= []).push(t);
    return acc;
  }, {});

  return (
    <div className="flex h-full gap-4">
      {/* Left sidebar — table browser + saved + history */}
      <div className="w-64 flex-shrink-0 bg-gray-900 border border-gray-800 rounded-xl p-3 overflow-y-auto flex flex-col gap-4">
        {/* Tables */}
        <div>
          <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Database className="w-4 h-4 text-blue-400" />
            Iceberg Tables
          </h2>
          {tablesLoading ? (
            <div className="flex items-center gap-2 text-xs text-gray-500 py-4 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading tables...
            </div>
          ) : Object.keys(grouped).length === 0 ? (
            <p className="text-xs text-gray-500 text-center py-4">
              No tables found. Ensure Nessie catalog is running.
            </p>
          ) : (
            <div className="space-y-1">
              {Object.entries(grouped)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([ns, tbls]) => (
                  <NamespaceNode
                    key={ns}
                    namespace={ns}
                    tables={tbls}
                    onSelectTable={handleTableSelect}
                  />
                ))}
            </div>
          )}
        </div>

        {/* Saved Queries */}
        {saved.length > 0 && (
          <div>
            <button
              onClick={() => setShowSaved(!showSaved)}
              className="flex items-center gap-1 text-sm font-semibold text-white mb-2 w-full"
            >
              {showSaved ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
              <Bookmark className="w-3.5 h-3.5 text-yellow-400" />
              Saved Queries
              <span className="ml-auto text-xs text-gray-500">{saved.length}</span>
            </button>
            {showSaved && (
              <div className="space-y-1">
                {saved.map((q, i) => (
                  <div key={i} className="flex items-center gap-1 group">
                    <button
                      onClick={() => setSql(q.sql)}
                      className="flex-1 text-left text-xs text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-gray-800 truncate transition-colors"
                      title={q.sql}
                    >
                      {q.name}
                    </button>
                    <button
                      onClick={() => handleDeleteSaved(i)}
                      className="opacity-0 group-hover:opacity-100 p-0.5 text-gray-600 hover:text-red-400 transition-opacity"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Query History */}
        {history.length > 0 && (
          <div>
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="flex items-center gap-1 text-sm font-semibold text-white mb-2 w-full"
            >
              {showHistory ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
              <History className="w-3.5 h-3.5 text-gray-400" />
              History
              <span className="ml-auto text-xs text-gray-500">{history.length}</span>
            </button>
            {showHistory && (
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {history.map((h, i) => (
                  <button
                    key={i}
                    onClick={() => setSql(h.sql)}
                    className="w-full text-left text-xs text-gray-500 hover:text-white px-2 py-1 rounded hover:bg-gray-800 truncate transition-colors"
                    title={h.sql}
                  >
                    <span className="block truncate">{h.sql.split('\n')[0]}</span>
                    <span className="text-[10px] text-gray-600">
                      {new Date(h.timestamp).toLocaleTimeString()}
                      {h.rowCount !== undefined && ` · ${h.rowCount} rows`}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Main area — editor + results */}
      <div className="flex-1 flex flex-col gap-4 min-w-0">
        {/* SQL Editor */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-white">Query Editor</h2>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Ctrl+Enter to run</span>
              <button
                onClick={handleSave}
                disabled={!sql.trim()}
                className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs text-gray-400 hover:text-white hover:bg-gray-800 transition-colors disabled:opacity-40"
                title="Save query"
              >
                <Save className="w-3.5 h-3.5" />
                Save
              </button>
              <button
                onClick={handleRun}
                disabled={mutation.isPending || !sql.trim()}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                  mutation.isPending || !sql.trim()
                    ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                    : 'bg-blue-600 text-white hover:bg-blue-500',
                )}
              >
                {mutation.isPending ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Play className="w-3.5 h-3.5" />
                )}
                Run
              </button>
            </div>
          </div>
          <textarea
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="SELECT * FROM raw_transactions LIMIT 100"
            className="w-full h-36 bg-gray-950 border border-gray-800 rounded-lg p-3 text-sm text-gray-200 font-mono resize-y focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder-gray-600 leading-relaxed"
            spellCheck={false}
          />
        </div>

        {/* Results */}
        <div className="flex-1 bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col min-h-0">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-white">Results</h2>
            <div className="flex items-center gap-3">
              {result && result.rows.length > 0 && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => exportCSV(result)}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors"
                  >
                    <Download className="w-3 h-3" />
                    CSV
                  </button>
                  <button
                    onClick={() => exportJSON(result)}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors"
                  >
                    <Download className="w-3 h-3" />
                    JSON
                  </button>
                </div>
              )}
              {result && (
                <div className="flex items-center gap-3 text-xs text-gray-500">
                  <span className="flex items-center gap-1">
                    <Rows3 className="w-3 h-3" />
                    {result.row_count} row{result.row_count !== 1 ? 's' : ''}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {result.execution_time_ms.toFixed(0)}ms
                  </span>
                </div>
              )}
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg mb-3">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-300">{error}</p>
            </div>
          )}

          {mutation.isPending && (
            <div className="flex-1 flex items-center justify-center">
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Loader2 className="w-5 h-5 animate-spin" />
                Executing query...
              </div>
            </div>
          )}

          {!result && !error && !mutation.isPending && (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-sm text-gray-600">
                Write a SQL query and click Run to see results
              </p>
            </div>
          )}

          {result && result.rows.length === 0 && (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-sm text-gray-500">Query returned 0 rows</p>
            </div>
          )}

          {result && result.rows.length > 0 && <ResultsTable result={result} />}
        </div>
      </div>
    </div>
  );
}
