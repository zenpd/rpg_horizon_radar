import { useEffect, useState, type ReactNode } from "react";
import { api, type Dashboard as OverviewData, type DashboardCard as OverviewCard } from "../api";
import { DetailDrawer, RippleGraph, SeverityDonut, SwotRadarChart, WeeklyTrendChart, type SeverityCounts, type TrendPoint } from "../components/exec";
import { useApp, type View } from "../state";

/* Each RPG company keeps one colour everywhere on this page (validated categorical palette, light and dark). */
const co = (i: number) => `var(--co-${i + 1})`;

/** Public signals per week, stacked by RPG company, with a hover tooltip and a table view. */
function WeeklySignals({ d, companies }: { d: OverviewData; companies: string[] }) {
  const [table, setTable] = useState(false);
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const W = 640, H = 220, L = 34, R = 630, T = 10, B = 190;
  const totals = d.weeks.map((w) => companies.reduce((a, c) => a + (w.counts[c] || 0), 0));
  const max = Math.max(4, ...totals);
  const step = Math.ceil(max / 4);
  const top = step * 4;
  const slot = (R - L) / d.weeks.length, bw = Math.min(46, slot * 0.6);
  const Y = (v: number) => B - ((B - T) * v) / top;
  const label = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  return (
    <div className="panel">
      <div className="card2-h">
        <div><h5 style={{ margin: 0 }}>Public signals per week, by subsidiary</h5>
          <p className="sub" style={{ fontSize: 12.5, margin: "2px 0 0" }}>News, filings, results, patents and hiring moves on the companies each RPG company watches, by week starting Monday; the current week is still filling.</p></div>
        <button className="btnx" onClick={() => setTable(!table)}>{table ? "Show as chart" : "Show as table"}</button>
      </div>
      {table ? (
        <div style={{ overflowX: "auto" }}>
          <table className="tbl mkt"><thead><tr><th>Week of</th>{companies.map((c) => <th key={c}>{c}</th>)}<th>Total</th></tr></thead>
            <tbody>{d.weeks.map((w, i) => <tr key={w.week}><td>{label(w.week)}</td>{companies.map((c) => <td key={c} className="num">{w.counts[c] || 0}</td>)}<td className="num"><b>{totals[i]}</b></td></tr>)}</tbody>
          </table>
        </div>
      ) : (
        <div style={{ position: "relative" }} onMouseLeave={() => setTip(null)}>
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Public signals per week, stacked by RPG company">
            {[0, 1, 2, 3, 4].map((k) => <g key={k}><line x1={L} x2={R} y1={Y(k * step)} y2={Y(k * step)} stroke="var(--rule)" /><text x={L - 6} y={Y(k * step) + 4} textAnchor="end" fontSize="10.5" fill="var(--faint)">{k * step}</text></g>)}
            {d.weeks.map((w, i) => {
              const x = L + slot * i + (slot - bw) / 2;
              let base = 0;
              return (
                <g key={w.week}>
                  {companies.map((c, j) => {
                    const v = w.counts[c] || 0;
                    if (!v) return null;
                    const y1 = Y(base), y2 = Y(base + v);
                    base += v;
                    return <rect key={c} x={x} y={y2 + 1} width={bw} height={Math.max(1, y1 - y2 - 2)} rx="2" fill={co(j)}
                      onMouseMove={(e) => { const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect(); setTip({ x: e.clientX - r.left + 12, y: e.clientY - r.top - 10, text: `${c}: ${v} signal${v === 1 ? "" : "s"}, week of ${label(w.week)}` }); }} />;
                  })}
                  {totals[i] > 0 && <text x={x + bw / 2} y={Y(totals[i]) - 5} textAnchor="middle" fontSize="10.5" fill="var(--muted)">{totals[i]}</text>}
                  <text x={x + bw / 2} y={B + 16} textAnchor="middle" fontSize="10.5" fill="var(--faint)">{label(w.week)}</text>
                </g>
              );
            })}
          </svg>
          {tip && <div className="viz-tip" style={{ left: tip.x, top: tip.y }}>{tip.text}</div>}
        </div>
      )}
      <div className="plegend" style={{ flexWrap: "wrap", gap: "4px 14px" }}>
        {companies.map((c, j) => <span key={c}><svg width="10" height="10" aria-hidden="true"><rect width="10" height="10" rx="2" fill={co(j)} /></svg>{c}</span>)}
      </div>
    </div>
  );
}

function Card({ c, i, onDeep, onOpen }: { c: OverviewCard; i: number; onDeep: (v: View) => void; onOpen: (id: string) => void }) {
  const m = c.market;
  return (
    <div className="card2 ov-card" style={{ borderTop: `3px solid ${co(i)}` }}>
      <div className="card2-h"><b className="rt" style={{ margin: 0 }}>{c.company}</b>
        <span className="sub" style={{ fontSize: 12 }}>{m.listed ? (m.close ? `₹${m.close.toLocaleString("en-IN")}${m.chg_30 !== null && m.chg_30 !== undefined ? ` · ${m.chg_30 > 0 ? "+" : ""}${m.chg_30.toFixed(1)}% in 30 days` : ""}` : "Price not fetched yet") : "Not listed"}</span>
      </div>
      <div className="ov-swotrow">
        <SwotRadarChart counts={c.swot} size={118} onAxisClick={() => onDeep("self")} />
        <div className="ov-swot" role="group" aria-label={`${c.company} SWOT item counts`}>
          {(["S", "W", "O", "T"] as const).map((q) => (
            <button key={q} type="button" className={`q${q}`} onClick={() => onDeep("self")} title={`${{ S: "Strengths", W: "Weaknesses", O: "Opportunities", T: "Threats" }[q]}: open Self analysis`}>
              <b>{c.swot[q]}</b><small>{{ S: "Strengths", W: "Weaknesses", O: "Opportunities", T: "Threats" }[q]}</small>
            </button>
          ))}
        </div>
      </div>
      <div className="kv small">
        <div><small>M&A signals</small><b>{c.open}</b></div>
        <div><small>Shortlisted</small><b>{c.shortlisted}</b></div>
        <div><small>New targets · 7 days</small><b>{c.new_targets}</b></div>
        <div><small>Competitors watched</small><b>{c.competitors}</b></div>
      </div>
      <p className="sub" style={{ fontSize: 13, margin: "2px 0" }}>
        {c.top ? <>Top signal: <a href="#" onClick={(e) => { e.preventDefault(); onOpen(c.top!.id); }}><b>{c.top.who}</b></a>{c.top.score !== null ? ` · opportunity score ${Math.round(c.top.score)}` : ""}</> : "No M&A signal yet."}
      </p>
      <p className="sub" style={{ fontSize: 13, margin: "2px 0" }}>
        {c.latest_finding ? <>Latest finding ({c.latest_finding.date}): <span className={`pill2 ${c.latest_finding.kind === "threat" ? "rip-risk" : "rip-opportunity"}`}>{c.latest_finding.kind}</span> {c.latest_finding.title}</> : "No daily findings in the last 7 days."}
      </p>
      <div className="btnrow" style={{ marginTop: "auto" }}>
        <button className="btnx pri" onClick={() => onDeep("signals")}>Deep dive</button>
        <button className="btnx" onClick={() => onDeep("finance")}>Finances</button>
      </div>
    </div>
  );
}

type Drill = { kind: "open" | "shortlisted" | "targets" | "findings" | "signals_week" } | { kind: "band"; band: keyof SeverityCounts } | { kind: "week"; index: number } | null;
const band = (score: number | null): keyof SeverityCounts => (score ?? 0) >= 70 ? "high" : (score ?? 0) >= 40 ? "elevated" : "low";
const short = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });

/** The ripple network for one M&A signal, chosen from those with a written thesis. */
function Ripples({ d, onOpen }: { d: OverviewData; onOpen: (co: string, id: string) => void }) {
  const [pick, setPick] = useState(0);
  const list = [...d.ripples].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  if (!list.length) return null;
  const r = list[Math.min(pick, list.length - 1)];
  return (
    <div className="panel">
      <div className="card2-h">
        <div><h5 style={{ margin: 0 }}>Ripple effect across the RPG companies</h5>
          <p className="sub" style={{ fontSize: 12.5, margin: "2px 0 0" }}>If {r.for} bought {r.who}: what it would mean for each other RPG company, from the acquisition thesis ({r.at}). Drag the circles; hover for the reasoning.</p></div>
        <label className="sub" style={{ fontSize: 12.5 }}>Signal <select value={pick} onChange={(e) => setPick(Number(e.target.value))}>
          {list.map((x, i) => <option key={`${x.for}-${x.case_id}`} value={i}>{x.who} · for {x.for}</option>)}
        </select></label>
      </div>
      <div className="cols even">
        <RippleGraph center={r.who} acquirer={r.for} effects={r.ripple} />
        <div>
          <p style={{ marginTop: 0 }}>{r.headline}</p>
          <ul className="cmp">{r.ripple.map((x) => (
            <li key={x.company}><span className={`pill2 rip-${x.effect}`}>{x.effect}</span> <b>{x.company}</b>: {x.reasoning}</li>
          ))}</ul>
          <button className="btnx" onClick={() => onOpen(r.for, r.case_id)}>Open the thesis</button>
        </div>
      </div>
      <div className="plegend" style={{ gap: "4px 14px", flexWrap: "wrap" }}>
        {([["var(--accent)", "Target"], ["var(--accent-700)", "Would acquire it"], ["var(--opp)", "Opportunity"], ["var(--faint)", "Neutral"], ["var(--crit)", "Risk"]] as const).map(([c, l]) => (
          <span key={l}><svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="5" fill={c} /></svg>{l}</span>
        ))}
      </div>
    </div>
  );
}

/** The executive dashboard: every RPG company at once; each card's Deep dive opens that company's tabs. */
export default function Overview() {
  const app = useApp();
  const [d, setD] = useState<OverviewData | null>(null);
  const [drill, setDrill] = useState<Drill>(null);
  useEffect(() => { api.dashboard().then(setD).catch((e) => app.toast(e.message)); }, [app.version]);
  if (!d) return <p className="sub">Loading…</p>;
  const companies = d.companies.map((c) => c.company);
  const deep = (c: string) => (v: View) => { setDrill(null); app.setScope(c); app.go(v); };
  const openCase = (c: string) => (id: string) => { setDrill(null); app.setScope(c); app.openSignal(id); };
  const k = d.kpis;
  const tiles: ["open" | "shortlisted" | "targets" | "signals_week" | "findings", number, string, string][] = [
    ["open", k.open, "Open M&A signals", "Companies an RPG company could buy, with public signals"],
    ["shortlisted", k.shortlisted, "Shortlisted", "Signals the team shortlisted"],
    ["targets", k.targets, "New targets · 7 days", "Found by Target Discovery or the Sector Scout"],
    ["signals_week", k.signals_week, "Public signals · 7 days", "On every watched company"],
    ["findings", k.findings, "Daily findings · 7 days", "Opportunities and threats in the news"],
  ];
  const sev: SeverityCounts = { low: 0, elevated: 0, high: 0 };
  d.lists.open.forEach((s) => { sev[band(s.score)] += 1; });
  const totals = d.weeks.map((w) => companies.reduce((a, c) => a + (w.counts[c] || 0), 0));
  const trend: TrendPoint[] = d.weeks.map((w, i) => ({ label: short(w.week), value: totals[i], id: i, highlighted: i === d.weeks.length - 2 }));
  const kpiOpen = (key: string) => drill && "kind" in drill && drill.kind === key;
  return (
    <>
      <div>
        <span className="crumb"><b>Executive dashboard</b> · all subsidiaries</span>
        <h4>The RPG companies at a glance</h4>
        <p className="sub">Every subsidiary on one page, from the radar's own data. Click any number, bar or slice for the records behind it; pick a card's <b>Deep dive</b> — or a company in the box above any other tab — to work on one company.</p>
      </div>
      <div className="ov-kpis">
        {tiles.map(([key, n, label, sub]) => (
          <button key={key} type="button" className={`ov-kpi${kpiOpen(key) ? " on" : ""}`} onClick={() => setDrill({ kind: key })}>
            <b>{n}</b><span>{label}</span><small>{sub}</small>
          </button>
        ))}
      </div>

      <div className="cols even">
        <div className="panel">
          <h5 style={{ margin: 0 }}>Signal volume by week</h5>
          <p className="sub" style={{ fontSize: 12.5, margin: "2px 0 6px" }}>Public signals on every watched company, all subsidiaries; last full week highlighted. Click a bar for its breakdown.</p>
          <WeeklyTrendChart points={trend} onSelect={(i) => setDrill({ kind: "week", index: i })} />
        </div>
        <div className="panel">
          <h5 style={{ margin: 0 }}>Open M&A signals by opportunity score</h5>
          <p className="sub" style={{ fontSize: 12.5, margin: "2px 0 6px" }}>Rule-based score bands across all subsidiaries. Click a slice or a band for its signals.</p>
          <SeverityDonut counts={sev} onSelect={(b) => setDrill({ kind: "band", band: b })} />
        </div>
      </div>

      <WeeklySignals d={d} companies={companies} />

      <div className="cards ov-cards">{d.companies.map((c, i) => <Card key={c.company} c={c} i={i} onDeep={deep(c.company)} onOpen={openCase(c.company)} />)}</div>

      <Ripples d={d} onOpen={(c, id) => openCase(c)(id)} />

      <div className="panel">
        <h5>M&A news across every opportunity</h5>
        <p className="sub" style={{ fontSize: 12.5, marginTop: 0 }}>Deals, fund raises, stake sales, pledges, distress, leadership and legal moves on the companies the RPG companies watch, newest first.</p>
        {d.news.length ? (
          <ul className="ov-news">{d.news.map((n, i) => (
            <li key={i}>
              <span className="sub mono">{n.date}</span>
              <span className="pill2" style={{ borderLeft: `3px solid ${co(Math.max(0, companies.indexOf(n.for)))}` }}>{n.for}</span>
              <b>{n.company}</b> · <span className="sub">{n.label}</span>{" "}
              {n.url ? <a href={n.url} target="_blank" rel="noreferrer">{n.text.length > 150 ? n.text.slice(0, 148) + "…" : n.text}</a> : n.text}
              {n.case_id && <> <a href="#" className="sw-link" onClick={(e) => { e.preventDefault(); openCase(n.for)(n.case_id!); }}>thesis</a></>}
            </li>
          ))}</ul>
        ) : <p className="sub">No M&A-related news on the watched companies yet.</p>}
      </div>

      <Drawer d={d} drill={drill} companies={companies} totals={totals} onClose={() => setDrill(null)} onOpen={(c, id) => openCase(c)(id)} onDeep={(c, v) => deep(c)(v)} />
    </>
  );
}

/** The detail drawer: the records behind whichever number, bar or slice was clicked. */
function Drawer({ d, drill, companies, totals, onClose, onOpen, onDeep }: {
  d: OverviewData; drill: Drill; companies: string[]; totals: number[]; onClose: () => void;
  onOpen: (co: string, id: string) => void; onDeep: (co: string, v: View) => void;
}) {
  if (!drill) return null;
  const L = d.lists;
  const signals = (rows: typeof L.open) => rows.length ? (
    <table className="tbl"><thead><tr><th>Company</th><th>For</th><th>Score</th><th /></tr></thead>
      <tbody>{rows.map((s) => <tr key={`${s.for}-${s.id}`}><td><b>{s.who}</b><div className="sub" style={{ fontSize: 11.5 }}>{s.size.label.replace("the RPG company's", s.for)}</div></td><td>{s.for}</td>
        <td className="num">{s.score !== null ? Math.round(s.score) : "—"}</td><td><button className="btnx" onClick={() => onOpen(s.for, s.id)}>Thesis</button></td></tr>)}</tbody></table>
  ) : <p className="sub">None.</p>;
  let title = "", basis = "", body: ReactNode = null;
  if (drill.kind === "open" || drill.kind === "shortlisted") {
    title = drill.kind === "open" ? "Open M&A signals" : "Shortlisted signals";
    basis = "Watched companies at most half the RPG company's size (or targets not sized yet) with public signals in the last 120 days.";
    body = signals(L[drill.kind]);
  } else if (drill.kind === "band") {
    title = `${{ high: "High", elevated: "Elevated", low: "Low" }[drill.band]} opportunity score`;
    basis = "Open M&A signals by rule-based opportunity score: high 70 or more, elevated 40–69, low under 40.";
    body = signals(L.open.filter((s) => band(s.score) === drill.band));
  } else if (drill.kind === "targets") {
    title = "New targets in the last 7 days"; basis = "Added by Target Discovery or the Sector Scout.";
    body = L.targets.length ? <table className="tbl"><tbody>{L.targets.map((t) => <tr key={`${t.for}-${t.entity_id}`}><td><b>{t.name}</b><div className="sub" style={{ fontSize: 11.5 }}>{t.why}</div></td><td>{t.for}</td><td className="sub">{t.found_at} · {t.found_via}</td></tr>)}</tbody></table>
      : <p className="sub">None in the last 7 days.</p>;
  } else if (drill.kind === "findings") {
    title = "Daily findings in the last 7 days"; basis = "The Opportunity Analyst's opportunities and threats in each company's news, not dismissed.";
    body = L.findings.length ? <table className="tbl"><tbody>{L.findings.map((f) => <tr key={f.id}><td className="sub">{f.date}</td><td>{f.for}</td>
      <td><span className={`pill2 ${f.kind === "threat" ? "rip-risk" : "rip-opportunity"}`}>{f.kind}</span> {f.title}</td><td><button className="btnx" onClick={() => onDeep(f.for, "digest")}>Open</button></td></tr>)}</tbody></table>
      : <p className="sub">None in the last 7 days.</p>;
  } else {
    const i = drill.kind === "week" ? drill.index : d.weeks.length - 1;
    const w = d.weeks[i];
    title = drill.kind === "week" ? `Week of ${short(w.week)}` : "Public signals in the last 7 days";
    basis = drill.kind === "week" ? `${totals[i]} public signals on the watched companies, by the RPG company that watches them.` : `${d.kpis.signals_week} public signals arrived in the last 7 days; this is the current week by subsidiary.`;
    body = <table className="tbl"><tbody>{companies.map((c) => <tr key={c}><td><b>{c}</b></td><td className="num">{w.counts[c] || 0}</td>
      <td><button className="btnx" onClick={() => onDeep(c, "competitors")}>Competitor Analysis</button></td></tr>)}</tbody></table>;
  }
  return <DetailDrawer open onClose={onClose} title={title} basis={basis}>{body}</DetailDrawer>;
}
