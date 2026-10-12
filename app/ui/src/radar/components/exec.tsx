// The executive dashboard's charts — the weekly trend, the severity donut, the SWOT radar, the ripple
// network and the detail drawer — after the team's Executive Dashboard design (D3 for scales, shapes and
// the force layout), drawn with the radar's theme colours so they read in light and dark, and fed by the
// radar's own data: public signals, opportunity scores, the live SWOTs and the theses' ripple effects.
import { useEffect, useMemo, useRef, type ReactNode } from "react";
import * as d3 from "d3";
import { X } from "lucide-react";

/* ---------- Weekly trend: signal volume per week, clickable bars ---------- */
export interface TrendPoint { label: string; value: number; highlighted?: boolean; id?: number }

export function WeeklyTrendChart({ points, height = 180, onSelect }: { points: TrendPoint[]; height?: number; onSelect?: (id: number) => void }) {
  const width = 480;
  const margin = { top: 14, right: 10, bottom: 28, left: 28 };
  const innerH = height - margin.top - margin.bottom;
  const { bars, yTicks, y } = useMemo(() => {
    const innerW = width - margin.left - margin.right;
    const xScale = d3.scaleBand<string>().domain(points.map((p) => p.label)).range([0, innerW]).padding(0.35);
    const maxY = Math.max(1, d3.max(points, (p) => p.value) ?? 1);
    const yScale = d3.scaleLinear().domain([0, maxY]).nice().range([innerH, 0]);
    return {
      y: yScale, yTicks: yScale.ticks(4),
      bars: points.map((p) => ({ ...p, bx: xScale(p.label) ?? 0, bw: xScale.bandwidth(), by: yScale(p.value), bh: innerH - yScale(p.value) })),
    };
  }, [points, height]);
  if (points.length === 0) return <p className="sub">No signal history yet.</p>;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" style={{ maxHeight: height }} role="img" aria-label="Public signals per week">
      <g transform={`translate(${margin.left},${margin.top})`}>
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={0} x2={width - margin.left - margin.right} y1={y(t)} y2={y(t)} stroke="var(--rule)" />
            <text x={-6} y={y(t)} dy={3} textAnchor="end" fontSize={9} fill="var(--faint)">{t}</text>
          </g>
        ))}
        {bars.map((b, i) => (
          <g key={b.id ?? i} onClick={() => b.id !== undefined && onSelect?.(b.id)} style={{ cursor: b.id !== undefined && onSelect ? "pointer" : "default" }}>
            <title>{`Week of ${b.label}: ${b.value} public signal${b.value === 1 ? "" : "s"}`}</title>
            <rect x={b.bx} y={b.by} width={b.bw} height={Math.max(b.bh, 1)} rx={3} fill={b.highlighted ? "var(--accent)" : "var(--accent-soft)"}
              stroke={b.highlighted ? "none" : "var(--accent)"} strokeOpacity={0.35} />
            <rect x={b.bx} y={0} width={b.bw} height={innerH} fill="transparent" />
            <text x={b.bx + b.bw / 2} y={innerH + 16} textAnchor="middle" fontSize={9} fill="var(--faint)">{b.label}</text>
            {b.value > 0 && <text x={b.bx + b.bw / 2} y={b.by - 4} textAnchor="middle" fontSize={10} fontWeight={600} fill="var(--accent-700)">{b.value}</text>}
          </g>
        ))}
      </g>
    </svg>
  );
}

/* ---------- Severity donut: open M&A signals by opportunity-score band ---------- */
export interface SeverityCounts { low: number; elevated: number; high: number }
const SEV_COLOR = { low: "var(--opp)", elevated: "var(--high)", high: "var(--crit)" };
const SEV_LABEL = { low: "Low (under 40)", elevated: "Elevated (40–69)", high: "High (70+)" };

export function SeverityDonut({ counts, size = 150, onSelect, unit = "open signals" }: {
  counts: SeverityCounts; size?: number; onSelect?: (band: keyof SeverityCounts) => void; unit?: string;
}) {
  const total = counts.low + counts.elevated + counts.high;
  const radius = size / 2;
  const arcs = useMemo(() => {
    const data = (["low", "elevated", "high"] as const).map((k) => ({ key: k, value: counts[k] }));
    const pie = d3.pie<{ key: string; value: number }>().value((d) => d.value).sort(null).padAngle(0.02);
    const arcGen = d3.arc<d3.PieArcDatum<{ key: string; value: number }>>().innerRadius(radius * 0.6).outerRadius(radius - 2).cornerRadius(2);
    return pie(data).map((d) => ({ ...d, path: arcGen(d) || "" }));
  }, [counts, radius]);
  return (
    <div className="exec-donut">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${total} ${unit} by score band`}>
        <g transform={`translate(${radius},${radius})`}>
          {total === 0 ? <circle r={radius - 2} fill="none" stroke="var(--rule)" strokeWidth={2} strokeDasharray="4 4" />
            : arcs.map((a) => a.data.value > 0 && (
              <path key={a.data.key} d={a.path} fill={SEV_COLOR[a.data.key as keyof SeverityCounts]} style={{ cursor: onSelect ? "pointer" : "default" }}
                onClick={() => onSelect?.(a.data.key as keyof SeverityCounts)}>
                <title>{`${SEV_LABEL[a.data.key as keyof SeverityCounts]}: ${a.data.value} ${unit}`}</title>
              </path>
            ))}
          <text textAnchor="middle" dy={-2} fontSize={20} fontWeight={700} fill="var(--ink)">{total}</text>
          <text textAnchor="middle" dy={14} fontSize={9} fill="var(--faint)">{unit}</text>
        </g>
      </svg>
      <div className="exec-legend">
        {(["high", "elevated", "low"] as const).map((k) => (
          <button key={k} type="button" onClick={() => onSelect?.(k)} disabled={!onSelect}>
            <span className="dot" style={{ background: SEV_COLOR[k] }} /><span className="sub">{SEV_LABEL[k]}</span><b>{counts[k]}</b>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ---------- SWOT radar: the shape of a company's SWOT, item counts per quadrant ---------- */
export interface SwotCounts { S: number; O: number; W: number; T: number }
// Top Strengths, right Opportunities, bottom Threats, left Weaknesses: each axis opposite its counterpart.
const AXES: { key: keyof SwotCounts; label: string; angle: number; color: string }[] = [
  { key: "S", label: "Strengths", angle: -90, color: "var(--opp)" },
  { key: "O", label: "Opportunities", angle: 0, color: "var(--watch)" },
  { key: "T", label: "Threats", angle: 90, color: "var(--crit)" },
  { key: "W", label: "Weaknesses", angle: 180, color: "var(--high)" },
];
const toXY = (angleDeg: number, r: number) => { const rad = (angleDeg * Math.PI) / 180; return { x: Math.cos(rad) * r, y: Math.sin(rad) * r }; };

export function SwotRadarChart({ counts, size = 132, onAxisClick }: { counts: SwotCounts; size?: number; onAxisClick?: (k: keyof SwotCounts) => void }) {
  const radius = size / 2 - 18;
  const maxVal = Math.max(3, counts.S, counts.O, counts.W, counts.T);
  const scale = useMemo(() => d3.scaleLinear().domain([0, maxVal]).range([0, radius]), [maxVal, radius]);
  const rings = scale.ticks(maxVal <= 4 ? maxVal : 3).filter((t) => t > 0);
  const points = AXES.map((a) => ({ ...a, value: counts[a.key], ...toXY(a.angle, scale(counts[a.key])) }));
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} style={{ flexShrink: 0 }} role="img"
      aria-label={`SWOT: ${counts.S} strengths, ${counts.W} weaknesses, ${counts.O} opportunities, ${counts.T} threats`}>
      <g transform={`translate(${size / 2},${size / 2})`}>
        {rings.map((t) => <circle key={t} r={scale(t)} fill="none" stroke="var(--rule)" strokeWidth={1} />)}
        {AXES.map((a) => { const p = toXY(a.angle, radius); return <line key={a.key} x1={0} y1={0} x2={p.x} y2={p.y} stroke="var(--rule)" strokeWidth={1} />; })}
        <polygon points={points.map((p) => `${p.x},${p.y}`).join(" ")} fill="var(--accent)" fillOpacity={0.18} stroke="var(--accent)" strokeWidth={1.5} />
        {points.map((p) => (
          <circle key={p.key} cx={p.x} cy={p.y} r={4} fill={p.color} stroke="var(--surface)" strokeWidth={1.5} style={{ cursor: onAxisClick ? "pointer" : "default" }} onClick={() => onAxisClick?.(p.key)}>
            <title>{`${p.label}: ${p.value} item${p.value === 1 ? "" : "s"}`}</title>
          </circle>
        ))}
        {AXES.map((a) => { const p = toXY(a.angle, radius + 13); return <text key={a.key} x={p.x} y={p.y} textAnchor="middle" dominantBaseline="middle" fontSize={8.5} fontWeight={600} fill="var(--muted)">{a.label[0]}</text>; })}
      </g>
    </svg>
  );
}

/* ---------- Ripple network: a target in the middle, the other RPG companies around it ---------- */
export interface RippleEffect { company: string; effect: "opportunity" | "neutral" | "risk"; reasoning: string }
const RIPPLE_COLOR: Record<string, string> = { opportunity: "var(--opp)", neutral: "var(--faint)", risk: "var(--crit)" };

interface Node extends d3.SimulationNodeDatum { id: string; kind: "center" | "acquirer" | "ripple"; effect?: string; reasoning?: string }
interface Link extends d3.SimulationLinkDatum<Node> { effect: string }

/** The acquisition thesis's ripple effect as a network: the target, the RPG company that would buy it,
 * and each other RPG company coloured by whether the deal is an opportunity, neutral or a risk for it.
 * Drag a node to rearrange; hover for the thesis's reasoning. */
export function RippleGraph({ center, acquirer, effects, height = 300 }: { center: string; acquirer: string; effects: RippleEffect[]; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || effects.length === 0) return;
    const width = el.clientWidth || 520;
    el.innerHTML = "";
    const nodes: Node[] = [{ id: center, kind: "center" }, { id: acquirer, kind: "acquirer" },
      ...effects.map((e) => ({ id: e.company, kind: "ripple" as const, effect: e.effect, reasoning: e.reasoning }))];
    const links: Link[] = [{ source: acquirer, target: center, effect: "acquirer" },
      ...effects.map((e) => ({ source: center, target: e.company, effect: e.effect }))];
    const svg = d3.select(el).append("svg").attr("width", width).attr("height", height).attr("viewBox", [0, 0, width, height])
      .attr("style", "max-width: 100%; height: auto;").attr("role", "img").attr("aria-label", `Ripple effect of ${acquirer} acquiring ${center}`);
    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink<Node, Link>(links).id((d) => d.id).distance(115))
      .force("charge", d3.forceManyBody().strength(-280))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(46));
    const link = svg.append("g").selectAll("line").data(links).join("line")
      .attr("stroke", (d) => (d.effect === "acquirer" ? "var(--accent)" : RIPPLE_COLOR[d.effect] || "var(--rule)"))
      .attr("stroke-width", (d) => (d.effect === "acquirer" ? 2.5 : 1.5)).attr("stroke-dasharray", (d) => (d.effect === "neutral" ? "4 3" : null))
      .attr("stroke-opacity", 0.7);
    const node = svg.append("g").selectAll<SVGGElement, Node>("g").data(nodes).join("g").attr("cursor", "grab")
      .call(d3.drag<SVGGElement, Node>()
        .on("start", (ev, d) => { if (!ev.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
        .on("end", (ev, d) => { if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
    node.append("circle").attr("r", (d) => (d.kind === "center" ? 30 : d.kind === "acquirer" ? 26 : 21))
      .attr("fill", (d) => (d.kind === "center" ? "var(--accent)" : d.kind === "acquirer" ? "var(--accent-700)" : RIPPLE_COLOR[d.effect || ""] || "var(--faint)"))
      .attr("fill-opacity", (d) => (d.kind === "ripple" && d.effect === "neutral" ? 0.45 : 1))
      .attr("stroke", "var(--surface)").attr("stroke-width", 2);
    node.append("title").text((d) => d.kind === "center" ? `${d.id}: the target` : d.kind === "acquirer" ? `${d.id}: would acquire it`
      : `${d.id}: ${d.effect}. ${d.reasoning || ""}`);
    node.append("text").attr("text-anchor", "middle").attr("dy", (d) => (d.kind === "center" ? 46 : 36))
      .attr("font-size", 11).attr("font-weight", 600).attr("fill", "var(--ink)")
      .text((d) => (d.id.length > 20 ? d.id.slice(0, 18) + "…" : d.id));
    sim.on("tick", () => {
      link.attr("x1", (d) => (d.source as Node).x!).attr("y1", (d) => (d.source as Node).y!)
        .attr("x2", (d) => (d.target as Node).x!).attr("y2", (d) => (d.target as Node).y!);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });
    return () => { sim.stop(); };
  }, [center, acquirer, effects, height]);
  if (effects.length === 0) return <p className="sub">This thesis has no ripple effects.</p>;
  return <div ref={ref} style={{ width: "100%" }} />;
}

/* ---------- Detail drawer: the records behind a number ---------- */
export function DetailDrawer({ open, onClose, title, basis, children }: { open: boolean; onClose: () => void; title: string; basis?: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="exec-drawer" role="dialog" aria-modal="true" aria-label={title}>
      <div className="exec-drawer-back" onClick={onClose} />
      <div className="exec-drawer-panel">
        <div className="exec-drawer-head">
          <div><h5 style={{ margin: 0 }}>{title}</h5>{basis && <p className="sub" style={{ fontSize: 11.5, margin: "2px 0 0" }}>{basis}</p>}</div>
          <button type="button" className="info-x" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="exec-drawer-body">{children}</div>
      </div>
    </div>
  );
}
