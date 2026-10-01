import { useRef, useState } from "react";
import type { Position, Spark, Tone } from "../api";

/** Small area chart for a weekly count (e.g. EV roles posted per week). */
export function SparkChart({ sp }: { sp: Spark }) {
  const v = sp.v, hi = Math.max(...v), lo = Math.min(...v) > 50 ? Math.floor(Math.min(...v) * 0.98) : 0;
  const X = (i: number) => 16 + (175 * i) / (v.length - 1), Y = (x: number) => 56 - (46 * (x - lo)) / (hi - lo || 1);
  const pts = v.map((x, i) => `${X(i).toFixed(1)},${Y(x).toFixed(1)}`);
  return (
    <svg className="chart" viewBox="0 0 200 70" width="100%" role="img" aria-label={sp.t}>
      <line x1="10" y1="56" x2="195" y2="56" stroke="var(--rule)" strokeWidth="1" />
      <line x1="10" y1="10" x2="195" y2="10" stroke="var(--rule)" strokeWidth=".6" strokeDasharray="2 3" />
      <text x="0" y="13">{hi}</text><text x="0" y="59">{lo}</text>
      <path d={`M${pts.join(" L")} L${X(v.length - 1)},56 L16,56 Z`} fill="currentColor" opacity=".15" />
      <path d={`M${pts.join(" L")}`} fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx={X(v.length - 1)} cy={Y(v[v.length - 1])} r="3.5" fill="currentColor" />
      <text x="12" y="68">{sp.a}</text><text x="195" y="68" textAnchor="end">{sp.b}</text>
    </svg>
  );
}

/** Four quarterly bars (e.g. export confidence in earnings calls). */
export function ToneChart({ t }: { t: Tone }) {
  const q = ["Q2", "Q3", "Q4", "Q1"];
  return (
    <svg className="chart" viewBox="0 0 200 70" width="100%" role="img" aria-label={t.t}>
      <line x1="10" y1="56" x2="195" y2="56" stroke="var(--rule)" strokeWidth="1" />
      {t.v.map((x, i) => {
        const h = x * 0.5, xx = 22 + 45 * i;
        const fill = x >= 65 ? "currentColor" : x >= 45 ? "var(--high)" : "var(--crit)";
        return (
          <g key={i}>
            <rect x={xx} y={56 - h} width="30" height={h} fill={fill} opacity={x >= 65 ? 0.55 : 1} />
            <text x={xx + 8} y={53 - h}>{x}</text><text x={xx + 4} y="67">{q[i]}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** Five yearly bars for the health check (revenue, margin). */
export function HBars({ vals, years, fmt }: { vals: number[]; years: string[]; fmt: (x: number) => string }) {
  const mx = Math.max(...vals.map(Math.abs)) || 1;
  return (
    <div className="hbars">
      {vals.map((v, i) => (
        <div key={i}><span>{fmt(v)}</span><i className={v < 0 ? "neg" : ""} style={{ height: Math.max(3, (Math.abs(v) / mx) * 62) }} /><span>{years[i]}</span></div>
      ))}
    </div>
  );
}

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

/** Indexed share-price chart: RPG company (or sector index) against one rival. */
export function MarketChart({ a, b, labels, event, listed }: { a: number[]; b: number[]; labels: string[]; event: { at: number; label: string }; listed: boolean }) {
  const all = a.concat(b);
  let lo = Math.min(...all), hi = Math.max(...all);
  const step = hi - lo > 80 ? 40 : hi - lo > 40 ? 20 : hi - lo > 16 ? 10 : 5;
  lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
  const L = 40, R = 630, T = 16, B = 230;
  const X = (i: number) => L + ((R - L) * i) / (a.length - 1), Y = (v: number) => B - ((B - T) * (v - lo)) / (hi - lo);
  const path = (s: number[]) => s.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + "," + Y(v).toFixed(1)).join(" ");
  const ticks: number[] = []; for (let v = lo; v <= hi + 0.001; v += step) ticks.push(v);
  const ei = Math.round(event.at * (b.length - 1)), ex = X(ei), ey = Y(b[ei]), up = ey > T + 30, ty = up ? ey - 22 : ey + 28;
  return (
    <svg className="fin-chart" viewBox="0 0 640 260" width="100%" role="img" aria-label="Indexed share price comparison">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={L} x2={R} y1={Y(v)} y2={Y(v)} stroke="var(--rule)" strokeWidth={v === 100 ? 1.2 : 0.6} strokeDasharray={v === 100 ? undefined : "2 4"} />
          <text x={L - 6} y={Y(v) + 3} textAnchor="end">{v}</text>
        </g>
      ))}
      {labels.map((t, i) => <text key={t} x={L + ((R - L) * i) / (labels.length - 1)} y={B + 18} textAnchor={i === 0 ? "start" : i === labels.length - 1 ? "end" : "middle"}>{t}</text>)}
      <path d={path(b)} fill="none" stroke="var(--l2)" strokeWidth="2" />
      <path d={path(a)} fill="none" stroke="var(--accent)" strokeWidth="2.4" strokeDasharray={listed ? undefined : "6 4"} />
      <circle cx={X(a.length - 1)} cy={Y(a[a.length - 1])} r="4" fill="var(--accent)" />
      <circle cx={X(b.length - 1)} cy={Y(b[b.length - 1])} r="4" fill="var(--l2)" />
      <line x1={ex} x2={ex} y1={ey} y2={up ? ty + 4 : ty - 12} stroke="var(--l2)" strokeWidth="1" />
      <circle cx={ex} cy={ey} r="3.5" fill="var(--surface)" stroke="var(--l2)" strokeWidth="1.5" />
      <text className="lbl-ev" x={Math.min(Math.max(ex, L + 60), R - 60)} y={ty} textAnchor="middle">{event.label}</text>
    </svg>
  );
}

/** Owners, directors (and their other boards) and subsidiaries around a target. */
export function OwnershipGraph({ g }: { g: { name: string; score: number; owners: [string, number, string][]; directors: [string, string, string[]][]; subs: string[] } }) {
  const W0 = 1000, H0 = 470, cx = 430, cy = 250;
  const col: Record<string, string> = { family: "#1E7F55", pe: "#6A4C9C", public: "#8A968F", person: "#2C64A8", link: "#B7372B", sub: "#A5661A" };
  const spread = (n: number, gap: number, c: number) => Array.from({ length: n }, (_, i) => c + (i - (n - 1) / 2) * gap);
  type N = { x: number; y: number; label: string; sub: string; kind: string; from?: number };
  const nodes: N[] = [], edges: [number, string][] = [];
  spread(g.owners.length, 86, cy).forEach((y, i) => { const o = g.owners[i]; nodes.push({ x: 130, y, label: o[0], sub: `owns ${o[1]}%`, kind: o[2] }); edges.push([nodes.length - 1, `${o[1]}%`]); });
  const dys = spread(g.directors.length, 96, cy);
  g.directors.forEach((d, i) => {
    const di = nodes.length; nodes.push({ x: 680, y: dys[i], label: d[0], sub: d[1], kind: "person" }); edges.push([di, "director"]);
    spread(d[2].length, 44, dys[i]).forEach((y, j) => nodes.push({ x: 890, y, label: d[2][j], sub: "also on this board", kind: "link", from: di }));
  });
  spread(g.subs.length, 240, cx).forEach((x, i) => { nodes.push({ x, y: 60, label: g.subs[i], sub: "subsidiary", kind: "sub" }); edges.push([nodes.length - 1, "owns"]); });
  const F = "Arial,sans-serif";
  const links = g.directors.filter((d) => d[2].length);
  return (
    <>
      <div className="graphwrap">
        <svg viewBox={`0 0 ${W0} ${H0}`} role="img" aria-label={`Ownership and relationship map for ${g.name}`}>
          {edges.map(([i, l], k) => {
            const n = nodes[i], mx = cx + (n.x - cx) * 0.62, my = cy + (n.y - cy) * 0.62;
            return (
              <g key={k}>
                <line x1={cx} y1={cy} x2={n.x} y2={n.y} stroke="#8A968F" strokeWidth="1.4" />
                <rect x={mx - 30} y={my - 9} width="60" height="16" rx="3" fill="#FFFFFF" />
                <text x={mx} y={my + 3} textAnchor="middle" fontSize="10.5" fill="#56635C" fontFamily={F}>{l}</text>
              </g>
            );
          })}
          {nodes.map((n, k) => n.kind === "link" && n.from !== undefined
            ? <line key={"l" + k} x1={nodes[n.from].x} y1={nodes[n.from].y} x2={n.x} y2={n.y} stroke="#B7372B" strokeWidth="1.5" strokeDasharray="5 4" /> : null)}
          <rect x={cx - 115} y={cy - 27} width="230" height="54" rx="8" fill="#FBE3EA" stroke="#B4234F" strokeWidth="2" />
          <text x={cx} y={cy - 4} textAnchor="middle" fontSize="13" fontWeight="700" fill="#15201B" fontFamily={F}>{g.name.length > 32 ? g.name.slice(0, 30) + "…" : g.name}</text>
          <text x={cx} y={cy + 14} textAnchor="middle" fontSize="11" fill="#56635C" fontFamily={F}>Target · score {g.score}</text>
          {nodes.map((n, k) => {
            const w = n.kind === "link" ? 180 : 200, c = col[n.kind], lab = n.label.length > 28 ? n.label.slice(0, 26) + "…" : n.label;
            return (
              <g key={"n" + k}>
                <rect x={n.x - w / 2} y={n.y - 20} width={w} height="40" rx={n.kind === "person" ? 20 : 6} fill="#FFFFFF" stroke={c} strokeWidth="1.8" />
                <text x={n.x} y={n.y - 3} textAnchor="middle" fontSize="11.5" fontWeight="600" fill="#15201B" fontFamily={F}>{lab}</text>
                <text x={n.x} y={n.y + 12} textAnchor="middle" fontSize="10.5" fill={c} fontFamily={F}>{n.sub}</text>
              </g>
            );
          })}
        </svg>
      </div>
      {links.length > 0 && <div className="callout"><b>Links found</b><p>{links.map((d) => `${d[0]} (${d[1]}) also sits on: ${d[2].join(", ")}.`).join(" ")}</p></div>}
      <div className="gl">
        <span><i style={{ background: "#1E7F55" }} />Family / promoter</span><span><i style={{ background: "#6A4C9C" }} />PE / investor</span>
        <span><i style={{ background: "#8A968F" }} />Public / others</span><span><i style={{ background: "#2C64A8" }} />Director</span>
        <span><i style={{ background: "#B7372B" }} />Other board (possible link)</span><span><i style={{ background: "#A5661A" }} />Subsidiary</span>
      </div>
      <p className="sub" style={{ fontSize: 12 }}>Built from MCA data, filings and annual reports. Links extracted by an LLM are confirmed by an analyst before use.</p>
    </>
  );
}
