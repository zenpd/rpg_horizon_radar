import { useMemo } from "react";
import * as d3 from "d3";

export interface TrendPoint { label: string; value: number; highlighted?: boolean; id?: number }

interface WeeklyTrendChartProps {
  points: TrendPoint[];
  height?: number;
  onSelect?: (id: number) => void;
}

/** A small bar chart of signal volume per digest week — D3 for scales/shape, React for the SVG.
 * No continuous simulation here, so there's no DOM-ownership conflict to avoid. Bars are
 * clickable (when an `id` is attached) so an exec can jump straight to that week's digest. */
export default function WeeklyTrendChart({ points, height = 180, onSelect }: WeeklyTrendChartProps) {
  const width = 480;
  const margin = { top: 10, right: 10, bottom: 28, left: 28 };

  const { bars, yTicks, x, y } = useMemo(() => {
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;
    const xScale = d3.scaleBand<string>().domain(points.map((p) => p.label)).range([0, innerW]).padding(0.35);
    const maxY = Math.max(1, d3.max(points, (p) => p.value) ?? 1);
    const yScale = d3.scaleLinear().domain([0, maxY]).nice().range([innerH, 0]);
    return {
      x: xScale, y: yScale,
      yTicks: yScale.ticks(4),
      bars: points.map((p) => ({
        ...p,
        bx: xScale(p.label) ?? 0, bw: xScale.bandwidth(),
        by: yScale(p.value), bh: innerH - yScale(p.value),
      })),
    };
  }, [points, height]);

  const innerH = height - margin.top - margin.bottom;

  if (points.length === 0) return <p className="text-xs text-gray-400">No digest history yet.</p>;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" style={{ maxHeight: height }}>
      <g transform={`translate(${margin.left},${margin.top})`}>
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={0} x2={width - margin.left - margin.right} y1={y(t)} y2={y(t)} stroke="#f1f5f9" />
            <text x={-6} y={y(t)} dy={3} textAnchor="end" fontSize={9} fill="#94a3b8">{t}</text>
          </g>
        ))}
        {bars.map((b, i) => (
          <g
            key={b.id ?? i}
            onClick={() => b.id !== undefined && onSelect?.(b.id)}
            style={{ cursor: b.id !== undefined && onSelect ? "pointer" : "default" }}
          >
            <title>{`Week of ${b.label}: ${b.value} signal${b.value === 1 ? "" : "s"} reached the digest`}</title>
            <rect x={b.bx} y={b.by} width={b.bw} height={Math.max(b.bh, 1)} rx={3}
              fill={b.highlighted ? "#4f46e5" : "#c7d2fe"} />
            <rect x={b.bx} y={0} width={b.bw} height={innerH} fill="transparent" />
            <text x={b.bx + b.bw / 2} y={innerH + 16} textAnchor="middle" fontSize={9} fill="#64748b">{b.label}</text>
            {b.value > 0 && <text x={b.bx + b.bw / 2} y={b.by - 4} textAnchor="middle" fontSize={10} fontWeight={600} fill="#4338ca">{b.value}</text>}
          </g>
        ))}
      </g>
    </svg>
  );
}
