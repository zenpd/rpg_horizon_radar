import { useMemo } from "react";
import * as d3 from "d3";

export interface SeverityCounts { low: number; elevated: number; high: number }

const COLOR = { low: "#10b981", elevated: "#f59e0b", high: "#f43f5e" }; // matches .score-low/-elevated/-high
const LABEL = { low: "Low", elevated: "Elevated", high: "High" };

/** Donut of live signals by severity band (same 0/50/75 thresholds as ScoreBadge.tsx). */
export default function SeverityDonut({ counts, size = 150, onSelect }: { counts: SeverityCounts; size?: number; onSelect?: (band: keyof SeverityCounts) => void }) {
  const total = counts.low + counts.elevated + counts.high;
  const radius = size / 2;

  const arcs = useMemo(() => {
    const data = (["low", "elevated", "high"] as const).map((k) => ({ key: k, value: counts[k] }));
    const pie = d3.pie<{ key: string; value: number }>().value((d) => d.value).sort(null);
    const arcGen = d3.arc<d3.PieArcDatum<{ key: string; value: number }>>().innerRadius(radius * 0.6).outerRadius(radius - 2);
    return pie(data).map((d) => ({ ...d, path: arcGen(d) || "" }));
  }, [counts, radius]);

  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <g transform={`translate(${radius},${radius})`}>
          {total === 0 ? (
            <circle r={radius - 2} fill="none" stroke="#e5e7eb" strokeWidth={2} strokeDasharray="4 4" />
          ) : (
            arcs.map((a) => a.data.value > 0 && (
              <path
                key={a.data.key}
                d={a.path}
                fill={COLOR[a.data.key as keyof typeof COLOR]}
                style={{ cursor: onSelect ? "pointer" : "default" }}
                onClick={() => onSelect?.(a.data.key as keyof SeverityCounts)}
              >
                <title>{`${LABEL[a.data.key as keyof typeof LABEL]} severity: ${a.data.value} live signal${a.data.value === 1 ? "" : "s"}`}</title>
              </path>
            ))
          )}
          <text textAnchor="middle" dy={-2} fontSize={20} fontWeight={700} fill="#111827">{total}</text>
          <text textAnchor="middle" dy={14} fontSize={9} fill="#9ca3af">live signals</text>
        </g>
      </svg>
      <div className="space-y-1.5">
        {(["high", "elevated", "low"] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => onSelect?.(k)}
            disabled={!onSelect}
            className="flex items-center gap-2 text-xs w-full text-left disabled:cursor-default enabled:hover:opacity-70"
          >
            <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: COLOR[k] }} />
            <span className="text-gray-600">{LABEL[k]}</span>
            <span className="font-semibold text-gray-900">{counts[k]}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
