import { useRef, useState } from "react";
import type { Position } from "../api";

/** Impact × urgency positioning chart for a company's opportunities and threats. */
export function PositionChart({ co, items, onHover, onOpen }: { co: string; items: Position[]; onHover: (id: string | null) => void; onOpen: (caseId: string) => void }) {
  const W = 640, H = 380, L = 52, R = 620, T = 22, B = 330;
  const X = (v: number) => L + ((R - L) * v) / 100, Y = (v: number) => B - ((B - T) * v) / 100;
  const wrap = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ p: Position; x: number; y: number } | null>(null);
  const placed: [number, number][] = [];
  const show = (p: Position, el: Element) => {
    const r = el.getBoundingClientRect(), w = wrap.current!.getBoundingClientRect();
    let x = r.left - w.left + r.width / 2 + 14;
    const y = r.top - w.top - 10;
    if (x + 240 > w.width) x = r.left - w.left - 254;
    setTip({ p, x: Math.max(4, x), y: Math.max(4, y) });
    onHover(p.id);
  };
  const hide = () => { setTip(null); onHover(null); };
  const grid = [0, 25, 50, 75, 100];
  return (
    <div className="panel poschart">
      <div className="intro">
        <div>
          <h5 style={{ margin: 0 }}>Where the opportunities and threats sit</h5>
          <p className="sub" style={{ fontSize: 12.5, margin: "2px 0 0" }}>Impact on {co} against how soon each one plays out. Filled marks drive a recommended move.</p>
        </div>
        <div className="plegend">
          <span><svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5.5" fill="var(--ch-o)" /></svg>Opportunity</span>
          <span><svg width="14" height="14" aria-hidden="true"><rect x="3" y="3" width="8" height="8" transform="rotate(45 7 7)" fill="var(--ch-t)" /></svg>Threat</span>
          <span><svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="var(--surface)" stroke="var(--muted)" strokeWidth="1.8" /></svg>Hollow = not acted on</span>
        </div>
      </div>
      <div className="pchart" ref={wrap}>
        <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`Opportunity and threat positioning for ${co}`}>
          <rect x={L} y={T} width={R - L} height={B - T} fill="var(--surface)" />
          <rect x={X(50)} y={T} width={R - X(50)} height={Y(50) - T} fill="var(--accent-soft)" opacity=".55" />
          {grid.map((v) => (
            <g key={v}>
              <line x1={L} x2={R} y1={Y(v)} y2={Y(v)} stroke="var(--rule)" strokeWidth={v === 50 ? 1.2 : 0.6} strokeDasharray={v === 50 ? "4 4" : undefined} />
              <line y1={T} y2={B} x1={X(v)} x2={X(v)} stroke="var(--rule)" strokeWidth={v === 50 ? 1.2 : 0.6} strokeDasharray={v === 50 ? "4 4" : undefined} />
            </g>
          ))}
          <text x={R - 8} y={T + 16} textAnchor="end" className="qlab">ACT NOW</text>
          <text x={L + 8} y={T + 16} className="qlab">PLAN FOR IT</text>
          <text x={R - 8} y={B - 8} textAnchor="end" className="qlab">WATCH CLOSELY</text>
          <text x={L + 8} y={B - 8} className="qlab">KEEP AN EYE ON</text>
          <text x={L} y={B + 20} className="ax">Later</text>
          <text x={R} y={B + 20} className="ax" textAnchor="end">Now</text>
          <text x={(L + R) / 2} y={B + 38} className="axt" textAnchor="middle">Urgency · how soon it plays out →</text>
          <text x={L - 8} y={B} className="ax" textAnchor="end">Low</text>
          <text x={L - 8} y={T + 8} className="ax" textAnchor="end">High</text>
          <text transform={`translate(16 ${(T + B) / 2}) rotate(-90)`} className="axt" textAnchor="middle">Impact on {co} →</text>
          {items.map((p) => {
            const cx = X(p.urgency), cy = Y(p.impact), col = p.q === "O" ? "var(--ch-o)" : "var(--ch-t)", fill = p.used ? col : "var(--surface)";
            let lx = cx + 13, anchor: "start" | "end" = "start";
            if (placed.some((q) => Math.abs(q[0] - cx) < 46 && Math.abs(q[1] - cy) < 16) || cx > R - 40) { lx = cx - 13; anchor = "end"; }
            placed.push([cx, cy]);
            return (
              <g key={p.id} className="pt" tabIndex={0} role="img"
                aria-label={`${p.id}: ${p.text}. Impact ${p.impact}, urgency ${p.urgency}. ${p.move ? "Drives: " + p.move : "Not acted on this week."}`}
                onMouseEnter={(e) => show(p, e.currentTarget)} onMouseLeave={hide} onFocus={(e) => show(p, e.currentTarget)} onBlur={hide}
                onClick={() => p.case_id && onOpen(p.case_id)}>
                <circle cx={cx} cy={cy} r="16" fill="transparent" />
                {p.q === "O"
                  ? <circle cx={cx} cy={cy} r="8" fill={fill} stroke={col} strokeWidth="2" />
                  : <rect x={cx - 7} y={cy - 7} width="14" height="14" transform={`rotate(45 ${cx} ${cy})`} fill={fill} stroke={col} strokeWidth="2" />}
                <text x={lx} y={cy + 4} textAnchor={anchor} className="plab">{p.id}</text>
              </g>
            );
          })}
        </svg>
        {tip && (
          <div className="ptip" style={{ left: tip.x, top: tip.y }}>
            <b>{tip.p.id} · {tip.p.q === "O" ? "Opportunity" : "Threat"}</b>
            <p>{tip.p.text}</p>
            <span>Impact <b>{tip.p.impact}</b> · Urgency <b>{tip.p.urgency}</b></span>
            <span>{tip.p.move ? "Drives: " + tip.p.move : "Not acted on this week"}</span>
          </div>
        )}
      </div>
      <details className="ptable">
        <summary>View as table</summary>
        <div style={{ overflowX: "auto" }}>
          <table className="tbl">
            <thead><tr><th>Item</th><th>Impact</th><th>Urgency</th><th>Drives</th></tr></thead>
            <tbody>{items.map((p) => <tr key={p.id}><td><b className="mono">{p.id}</b> {p.text}</td><td className="mono">{p.impact}</td><td className="mono">{p.urgency}</td><td>{p.move ?? <span className="sub">Not acted on</span>}</td></tr>)}</tbody>
          </table>
        </div>
      </details>
    </div>
  );
}


const REL_COLOUR: Record<string, string> = {
  shareholder: "#7C3AED", promoter: "#047857", parent: "#1D4ED8", subsidiary: "#EA580C", "joint venture": "#0D9488",
  partner: "#2563EB", customer: "#B45309", supplier: "#64748B", director: "#475569", other: "#94A3B8",
};

/** The target in the middle, the companies and people linked to it around it; an RPG company or a
 * watched company among them is drawn with a red ring. */
export function ConnectionsGraph({ center, items }: { center: string; items: { name: string; relation: string; detail: string; link: string | null }[] }) {
  const W = 760, H = 420, cx = W / 2, cy = H / 2, R = Math.min(170, 90 + items.length * 8);
  const short = (t: string, n: number) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
  const nodes = items.map((x, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / items.length;
    return { ...x, x: cx + Math.cos(a) * R * 1.55, y: cy + Math.sin(a) * R };
  });
  const rels = [...new Set(items.map((x) => x.relation))];
  return (
    <div className="chartbox">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Companies and people linked to ${center}`} style={{ width: "100%", height: "auto" }}>
        {nodes.map((n, i) => <line key={"l" + i} x1={cx} y1={cy} x2={n.x} y2={n.y} stroke={REL_COLOUR[n.relation] || "#94A3B8"} strokeWidth="1.6" opacity="0.7" />)}
        {nodes.map((n, i) => {
          const mx = (cx + n.x) / 2, my = (cy + n.y) / 2;
          return <g key={"r" + i}><rect x={mx - 38} y={my - 9} width="76" height="16" rx="6" fill="var(--surface, #fff)" opacity="0.92" />
            <text x={mx} y={my + 3} textAnchor="middle" fontSize="10" fill={REL_COLOUR[n.relation] || "#475569"}>{n.relation}</text></g>;
        })}
        <rect x={cx - 105} y={cy - 22} width="210" height="44" rx="12" fill="var(--accent-soft, #EEF2FF)" stroke="var(--accent, #4F46E5)" strokeWidth="2" />
        <text x={cx} y={cy + 5} textAnchor="middle" fontSize="13" fontWeight="700" fill="currentColor">{short(center, 30)}</text>
        {nodes.map((n, i) => (
          <g key={"n" + i}>
            <title>{`${n.name} · ${n.relation}${n.detail ? ` · ${n.detail}` : ""}${n.link ? ` · ${n.link}` : ""}`}</title>
            <rect x={n.x - 80} y={n.y - 18} width="160" height="36" rx="10" fill="var(--surface, #fff)"
              stroke={n.link ? "#BE123C" : REL_COLOUR[n.relation] || "#94A3B8"} strokeWidth={n.link ? 3 : 1.6} />
            <text x={n.x} y={n.y - 2} textAnchor="middle" fontSize="11.5" fontWeight="600" fill="currentColor">{short(n.name, 24)}</text>
            <text x={n.x} y={n.y + 12} textAnchor="middle" fontSize="10" fill="var(--faint, #64748B)">{short(n.detail || n.relation, 28)}</text>
          </g>
        ))}
      </svg>
      <div className="gl" style={{ display: "flex", flexWrap: "wrap", gap: 12, fontSize: 12 }}>
        {rels.map((r) => <span key={r}><i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: REL_COLOUR[r] || "#94A3B8", marginRight: 4 }} />{r}</span>)}
        {items.some((x) => x.link) && <span><i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, border: "2px solid #BE123C", marginRight: 4 }} />an RPG or watched company</span>}
      </div>
    </div>
  );
}
