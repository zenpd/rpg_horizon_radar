import { useMemo } from "react";
import * as d3 from "d3";

export interface SwotCounts { S: number; O: number; W: number; T: number }

// Top = Strengths, right = Opportunities, bottom = Threats, left = Weaknesses — so each axis
// sits opposite its internal/external-positive/negative counterpart (S vs T, O vs W). A shape
// that leans upward is reading as more positive than negative for this subsidiary, purely from
// how many evidenced SWOT items exist in each quadrant — no scoring or fabrication involved.
const AXES: { key: keyof SwotCounts; label: string; angle: number; color: string }[] = [
  { key: "S", label: "Strengths", angle: -90, color: "#10b981" },
  { key: "O", label: "Opportunities", angle: 0, color: "#3b82f6" },
  { key: "T", label: "Threats", angle: 90, color: "#f43f5e" },
  { key: "W", label: "Weaknesses", angle: 180, color: "#f59e0b" },
];

const toXY = (angleDeg: number, r: number) => {
  const rad = (angleDeg * Math.PI) / 180;
  return [Math.cos(rad) * r, Math.sin(rad) * r] as const;
};

/** A 4-axis radar of how many evidenced SWOT items each subsidiary has, per quadrant —
 * the "shape" of its week, at a glance. D3 supplies the scale only; React owns the SVG. */
export default function SwotRadarChart({ counts, size = 132, onAxisClick }: { counts: SwotCounts; size?: number; onAxisClick?: (k: keyof SwotCounts) => void }) {
  const radius = size / 2 - 18;
  const maxVal = Math.max(3, counts.S, counts.O, counts.W, counts.T);

  const scale = useMemo(() => d3.scaleLinear().domain([0, maxVal]).range([0, radius]), [maxVal, radius]);
  const rings = scale.ticks(maxVal <= 4 ? maxVal : 3).filter((t) => t > 0);

  const points = AXES.map((a) => ({ ...a, value: counts[a.key], ...pointFor(a.angle, scale(counts[a.key])) }));
  const polygon = points.map((p) => `${p.x},${p.y}`).join(" ");

  function pointFor(angle: number, r: number) {
    const [x, y] = toXY(angle, r);
    return { x, y };
  }

  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} className="flex-shrink-0">
      <g transform={`translate(${size / 2},${size / 2})`}>
        {rings.map((t) => (
          <circle key={t} r={scale(t)} fill="none" stroke="#e5e7eb" strokeWidth={1} />
        ))}
        {AXES.map((a) => {
          const [x, y] = toXY(a.angle, radius);
          return <line key={a.key} x1={0} y1={0} x2={x} y2={y} stroke="#e5e7eb" strokeWidth={1} />;
        })}
        <polygon points={polygon} fill="#4f46e5" fillOpacity={0.18} stroke="#4f46e5" strokeWidth={1.5} />
        {points.map((p) => (
          <circle
            key={p.key}
            cx={p.x}
            cy={p.y}
            r={3.5}
            fill={p.color}
            style={{ cursor: onAxisClick ? "pointer" : "default" }}
            onClick={() => onAxisClick?.(p.key)}
          >
            <title>{`${p.label}: ${p.value} evidenced item${p.value === 1 ? "" : "s"}`}</title>
          </circle>
        ))}
        {AXES.map((a) => {
          const [x, y] = toXY(a.angle, radius + 13);
          return (
            <text key={a.key} x={x} y={y} textAnchor="middle" dominantBaseline="middle" fontSize={8.5} fontWeight={600} fill="#64748b">
              {a.label[0]}
            </text>
          );
        })}
      </g>
    </svg>
  );
}
