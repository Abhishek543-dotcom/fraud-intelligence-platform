import { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchLineage } from '../services/api';
import type { LineageNode, LineageEdge } from '../services/api';

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------

const NODE_W = 180;
const NODE_H = 50;
const COL_GAP = 250;
const ROW_GAP = 80;
const PAD_X = 60;
const PAD_Y = 40;

const COLUMN_ORDER: Record<string, number> = {
  source: 0,
  bronze: 1,
  silver: 2,
  gold: 3,
  service: 3,
  sink: 4,
};

const NODE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  source: { bg: '#581c87', border: '#7e22ce', text: '#d8b4fe' },
  bronze: { bg: '#78350f', border: '#b45309', text: '#fcd34d' },
  silver: { bg: '#1e293b', border: '#475569', text: '#cbd5e1' },
  gold: { bg: '#713f12', border: '#ca8a04', text: '#fef08a' },
  service: { bg: '#1e3a5f', border: '#2563eb', text: '#93c5fd' },
  sink: { bg: '#14532d', border: '#16a34a', text: '#86efac' },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface PositionedNode extends LineageNode {
  x: number;
  y: number;
}

function layoutNodes(nodes: LineageNode[]): PositionedNode[] {
  // Group by column
  const columns: Record<number, LineageNode[]> = {};
  for (const node of nodes) {
    const col = COLUMN_ORDER[node.type] ?? 3;
    (columns[col] ??= []).push(node);
  }

  const positioned: PositionedNode[] = [];
  for (const [colStr, colNodes] of Object.entries(columns)) {
    const col = Number(colStr);
    const x = PAD_X + col * (NODE_W + COL_GAP);
    colNodes.forEach((node, i) => {
      const y = PAD_Y + i * (NODE_H + ROW_GAP);
      positioned.push({ ...node, x, y });
    });
  }
  return positioned;
}

function bezierPath(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): string {
  const mx = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

function Tooltip({
  node,
  x,
  y,
}: {
  node: LineageNode;
  x: number;
  y: number;
}) {
  return (
    <foreignObject x={x} y={y - 70} width={220} height={60} style={{ overflow: 'visible' }}>
      <div className="bg-gray-900 border border-gray-700 rounded-lg shadow-xl p-2 text-xs">
        <p className="text-gray-300 font-medium mb-0.5">{node.label}</p>
        <p className="text-gray-500">{node.metadata.description}</p>
        {node.metadata.row_count != null && (
          <p className="text-gray-400 mt-0.5">
            Rows: {node.metadata.row_count.toLocaleString()}
          </p>
        )}
      </div>
    </foreignObject>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DataLineage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['lineage'],
    queryFn: fetchLineage,
    staleTime: 30_000,
  });

  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  const positioned = useMemo(
    () => (data ? layoutNodes(data.nodes) : []),
    [data],
  );

  const nodeMap = useMemo(() => {
    const map = new Map<string, PositionedNode>();
    for (const n of positioned) map.set(n.id, n);
    return map;
  }, [positioned]);

  const svgWidth = useMemo(() => {
    if (!positioned.length) return 900;
    return Math.max(...positioned.map((n) => n.x + NODE_W)) + PAD_X;
  }, [positioned]);

  const svgHeight = useMemo(() => {
    if (!positioned.length) return 500;
    return Math.max(...positioned.map((n) => n.y + NODE_H)) + PAD_Y + 40;
  }, [positioned]);

  const handleMouseEnter = useCallback((id: string) => setHoveredNodeId(id), []);
  const handleMouseLeave = useCallback(() => setHoveredNodeId(null), []);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold text-white">Data Lineage</h1>
          <p className="text-sm text-gray-500">Pipeline visualization loading...</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 h-96 animate-pulse" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold text-white">Data Lineage</h1>
          <p className="text-sm text-red-400">Failed to load lineage data.</p>
        </div>
      </div>
    );
  }

  const edges: LineageEdge[] = data.edges;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-white">Data Lineage</h1>
        <p className="text-sm text-gray-500">
          Bronze &rarr; Silver &rarr; Gold transformation pipeline
        </p>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs">
        {Object.entries(NODE_COLORS).map(([type, colors]) => (
          <div key={type} className="flex items-center gap-1.5">
            <span
              className="w-3 h-3 rounded"
              style={{ backgroundColor: colors.border }}
            />
            <span className="text-gray-400 capitalize">{type}</span>
          </div>
        ))}
      </div>

      {/* Graph */}
      <div className="bg-gray-950 border border-gray-800 rounded-xl overflow-auto">
        <svg
          width={svgWidth}
          height={svgHeight}
          className="min-w-full"
          style={{
            backgroundImage:
              'radial-gradient(circle, #374151 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        >
          {/* Arrow marker */}
          <defs>
            <marker
              id="arrowhead"
              markerWidth="8"
              markerHeight="6"
              refX="8"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 8 3, 0 6" fill="#6b7280" />
            </marker>
          </defs>

          {/* Edges */}
          {edges.map((edge, i) => {
            const src = nodeMap.get(edge.source);
            const tgt = nodeMap.get(edge.target);
            if (!src || !tgt) return null;

            const x1 = src.x + NODE_W;
            const y1 = src.y + NODE_H / 2;
            const x2 = tgt.x;
            const y2 = tgt.y + NODE_H / 2;

            const midX = (x1 + x2) / 2;
            const midY = (y1 + y2) / 2;

            return (
              <g key={i}>
                <path
                  d={bezierPath(x1, y1, x2, y2)}
                  fill="none"
                  stroke="#4b5563"
                  strokeWidth={1.5}
                  markerEnd="url(#arrowhead)"
                />
                <text
                  x={midX}
                  y={midY - 6}
                  textAnchor="middle"
                  className="text-[9px]"
                  fill="#6b7280"
                >
                  {edge.label}
                </text>
              </g>
            );
          })}

          {/* Nodes */}
          {positioned.map((node) => {
            const colors = NODE_COLORS[node.type] || NODE_COLORS.silver;
            return (
              <g
                key={node.id}
                onMouseEnter={() => handleMouseEnter(node.id)}
                onMouseLeave={handleMouseLeave}
                className="cursor-pointer"
              >
                <rect
                  x={node.x}
                  y={node.y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={8}
                  fill={colors.bg}
                  stroke={colors.border}
                  strokeWidth={hoveredNodeId === node.id ? 2.5 : 1.5}
                  opacity={hoveredNodeId && hoveredNodeId !== node.id ? 0.5 : 1}
                />
                <text
                  x={node.x + NODE_W / 2}
                  y={node.y + NODE_H / 2 - 4}
                  textAnchor="middle"
                  fill={colors.text}
                  className="text-xs font-medium"
                  style={{ pointerEvents: 'none' }}
                >
                  {node.label}
                </text>
                <text
                  x={node.x + NODE_W / 2}
                  y={node.y + NODE_H / 2 + 12}
                  textAnchor="middle"
                  fill="#6b7280"
                  className="text-[9px]"
                  style={{ pointerEvents: 'none' }}
                >
                  {node.type}
                  {node.metadata.row_count != null &&
                    ` \u00b7 ${node.metadata.row_count.toLocaleString()} rows`}
                </text>
              </g>
            );
          })}

          {/* Tooltip */}
          {hoveredNodeId && nodeMap.get(hoveredNodeId) && (
            <Tooltip
              node={nodeMap.get(hoveredNodeId)!}
              x={nodeMap.get(hoveredNodeId)!.x}
              y={nodeMap.get(hoveredNodeId)!.y}
            />
          )}
        </svg>
      </div>
    </div>
  );
}
