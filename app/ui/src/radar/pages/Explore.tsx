/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { MarketChart, SparkChart, ToneChart } from "../components/charts";
import { useApp } from "../state";

const pct = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(1) + "%";

function ScopeNote() {
  const app = useApp();
  return app.scope === "All" ? <div><span className="scope-note">Showing {app.cur} — pick a company above to change</span></div> : null;
}

/* ---------------- Competitors ---------------- */
export function Competitors() {
  const app = useApp();
  const co = app.cur;
  const [d, setD] = useState<any>(null);
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => { setSel(null); api.competitors(co).then(setD); }, [co, app.version]);
  if (!d) return <p className="sub">Loading competitors…</p>;
  const list: any[] = d.rivals, s = list.find((x) => x.name === sel) || list[0];
  const follow = async () => {
    const on = s.watch !== "Deep";
    setD(await api.follow(co, s.name, on));
    if (on) app.toast(`${s.name} moved to deep watch.`);
  };
  return (
    <>
      <div className="top"><div>
        <h1>{co}'s competitors · {list.length} tracked</h1>
        <p className="sub">Discovered and kept up to date by the Research Agent. Click a rival to see its moves.</p>
        <ScopeNote />
      </div></div>
      <div className="panel" style={{ overflowX: "auto" }}>
        <table className="tbl">
          <thead><tr><th>Competitor</th><th>Segment</th><th>Watch</th><th>Threat</th><th>Signals · 30 days</th><th>Latest move</th></tr></thead>
          <tbody>
            {list.map((x) => (
              <tr key={x.name} style={x.name === s.name ? { background: "var(--accent-soft)" } : undefined}>
                <td><a href="#" onClick={(e) => { e.preventDefault(); setSel(x.name); }}><b>{x.name}</b></a></td><td>{x.segment}</td>
                <td><span className="pill2">{x.watch}</span></td><td><span className={`sev ${x.threat[0]}`}>{x.threat[1].replace("Threat: ", "")}</span></td>
                <td className="mono">{x.signals_30d}</td><td>{x.latest_move.length > 70 ? x.latest_move.slice(0, 68) + "…" : x.latest_move}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="top"><div><h2>{s.name} · {s.segment}</h2></div></div>
      {s.primary ? (
        <div className="cols">
          <div className="stack">
            <div className="panel"><h5>Timeline of moves</h5><div className="tl">{s.timeline.map((t: string[], i: number) => <div key={i}><time>{t[0]}</time><p><b>{t[1]}:</b> {t[2]} <span className="mini">{t[3]}</span></p></div>)}</div></div>
            <div className="panel"><h5>What customers say about {s.name} · last 30 days</h5>
              <div className="voc">{s.voc.map((v: any[], i: number) => <div key={i}><span className={`sev ${v[0]}`}>{v[1]}</span><p><b>{v[2]}</b> {v[3]}</p><span className="num">{v[4]} mentions</span></div>)}</div></div>
          </div>
          <div className="stack">
            <div className="callout"><b>Analyst view</b><p>{s.analyst}</p><p><b style={{ fontFamily: "var(--body)" }}>Suggested for {co}:</b> {s.suggest}</p></div>
            <div className="panel"><h5>{s.spark.t}</h5><SparkChart sp={s.spark} /></div>
            <div className="panel"><h5>{s.tone.t}</h5><ToneChart t={s.tone} /></div>
            <div className="btnrow"><button className="btnx pri" onClick={() => app.openRow(s.case_id, co)}>See it in this week's digest</button></div>
          </div>
        </div>
      ) : (
        <div className="cols">
          <div className="stack"><div className="panel"><h5>Latest moves</h5><div className="tl"><div><time>16 Sep</time><p><b>{s.latest_move}.</b> {s.why || ""} <span className="mini">{s.why ? "Market & Financials Tracker" : "Watcher"}</span></p></div></div></div></div>
          <div className="stack">
            <div className="callout"><b>{s.watch} watch</b>
              <p>{s.watch === "Deep" ? "All agents now track this rival, including hiring, patents and customer voice. New moves appear from the next daily run."
                : s.watch === "Standard" ? "News, exchange filings and share price are tracked. Follow this rival to add hiring, patents and customer voice."
                  : "News only. Follow this rival to track filings, hiring, patents and customer voice."}</p>
              {s.act && <p><b style={{ fontFamily: "var(--body)" }}>So what for {co}:</b> {s.act}</p>}
            </div>
            <div className="btnrow"><button className={`btnx${s.watch === "Deep" ? "" : " pri"}`} onClick={follow}>{s.watch === "Deep" ? "Following ✓" : "Follow this rival"}</button></div>
          </div>
        </div>
      )}
    </>
  );
}

/* ---------------- Market performance ---------------- */
export function Market() {
  const app = useApp();
  const co = app.cur;
  const [rival, setRival] = useState<string | undefined>(undefined);
  const [period, setPeriod] = useState("1Y");
  const [q, setQ] = useState("");
  const [d, setD] = useState<any>(null);
  useEffect(() => { setRival(undefined); setQ(""); }, [co]);
  useEffect(() => { api.market(co, rival, period).then(setD); }, [co, rival, period]);
  if (!d) return <p className="sub">Loading market data…</p>;
  const hits = d.rivals.filter((r: any) => (r.name + " " + r.segment).toLowerCase().includes(q.trim().toLowerCase()));
  const gap = d.rival_return - d.base_return;
  return (
    <>
      <div className="top"><div>
        <h1>{co} vs competitors: market performance</h1>
        <p className="sub">{d.listed ? "Share prices indexed to 100 at the start of the period · illustrative data" : `${co} is not listed, so rivals are compared with the listed sector index (dashed line) · illustrative data`}</p>
        <ScopeNote />
      </div><span style={{ flex: 1 }} /><span className="lock">Live feed · 15-min delay</span></div>
      <div className="fin-controls">
        <div className="fin-search">
          <label htmlFor="finSearch" className="crumb">{d.listed ? `Compare ${co} with` : "Compare the sector index with"}</label>
          <input id="finSearch" type="search" placeholder="Search a competitor…" autoComplete="off" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="fin-list" role="listbox" aria-label="Competitors">
            {hits.map((r: any) => <button key={r.name} type="button" role="option" aria-selected={r.name === d.rival} onClick={() => setRival(r.name)}>{r.name}</button>)}
            <small>{hits.length ? `+${d.more_tracked} more ${co} rivals in production` : "No tracked rival matches. In production, any listed company can be added."}</small>
          </div>
        </div>
        <div className="seg fin-period" role="group" aria-label="Time period">
          {d.periods.map((p: string) => <button key={p} type="button" aria-pressed={p === period} onClick={() => setPeriod(p)}>{p}</button>)}
        </div>
      </div>
      <div className="cols">
        <div className="panel">
          <div className="fin-legend">
            <span><i style={{ background: "var(--chart)" }} />{d.base_name} <b className={d.base_return >= 0 ? "up" : "dn"}>{pct(d.base_return)}</b></span>
            <span><i style={{ background: "var(--chart2)" }} />{d.rival} <b className={d.rival_return >= 0 ? "up" : "dn"}>{pct(d.rival_return)}</b></span>
            <span style={{ color: "var(--faint)" }}>over {period}</span>
          </div>
          <MarketChart a={d.base_series} b={d.rival_series} labels={d.labels} event={d.event} listed={d.listed} />
        </div>
        <div className="stack">
          <div className="callout">
            <b>Why the gap? · Market &amp; Financials Tracker</b>
            <p>Over {period}, {d.rival} {gap >= 0 ? "outperformed" : "underperformed"} {d.listed ? co : "the sector index"} by {Math.abs(gap).toFixed(1)} points. {d.why}</p>
            <p><b style={{ fontFamily: "var(--body)" }}>So what for {co}:</b> {d.act}</p>
          </div>
          <div className="panel"><h5>Valuation and fundamentals</h5>
            <table className="fin-table">
              <thead><tr><th>Metric</th><th>{d.listed ? co : "Sector median"}</th><th>{d.rival}</th></tr></thead>
              <tbody>{d.metrics.map((m: any) => <tr key={m.metric}><td>{m.metric}</td><td>{m.base}</td><td>{m.rival}</td></tr>)}</tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}

/* ---------------- Rival deals ---------------- */
export function RivalDeals() {
  const app = useApp();
  const [f, setF] = useState(app.scope);
  const [d, setD] = useState<any>(null);
  useEffect(() => setF(app.scope), [app.scope]);
  useEffect(() => { api.deals(f).then(setD); }, [f]);
  if (!d) return <p className="sub">Loading deals…</p>;
  const max = d.top_buyers[0]?.count || 1;
  return (
    <>
      <div className="top"><div>
        <h1>Rival deals · who is buying what</h1>
        <p className="sub">From exchange filings, stake disclosures (SAST), CCI combination orders, deal databases and news.</p>
      </div></div>
      <div className="cols">
        <div className="panel">
          <div className="filters" style={{ marginBottom: 8 }}>
            <label>RPG company <select value={f} onChange={(e) => setF(e.target.value)}>{(app.groupView ? ["All", ...app.companies] : app.companies).map((x) => <option key={x}>{x}</option>)}</select></label>
          </div>
          <table className="tbl">
            <thead><tr><th>Date</th><th>Buyer → target</th><th>Type</th><th>Size</th><th>Source</th></tr></thead>
            <tbody>
              {d.deals.map((x: any, i: number) => (
                <tr key={i}>
                  <td className="mono">{x.date.slice(5).split("-").reverse().join("/")}</td>
                  <td><b>{x.buyer}</b> → {x.case_id ? <a href="#" onClick={(e) => { e.preventDefault(); app.openRow(x.case_id); }}>{x.target}</a> : x.target}<br /><span className="sub" style={{ fontSize: 11.5 }}>{x.sector} · {x.for}</span></td>
                  <td>{x.type}</td><td>{x.size}</td><td>{x.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="stack">
          <div className="panel"><h5>Most active buyers · 6 months</h5>
            {d.top_buyers.map((b: any) => <div key={b.buyer} className="barrow"><span>{b.buyer}</span><div className="pbar"><i style={{ width: `${(b.count / max) * 100}%` }} /></div><span>{b.count}</span></div>)}</div>
          <div className="callout"><b>Watch-out</b><p>Rival A Ltd bought 6% of Meridian Treadworks, a company on the CEAT watchlist, and completed Axle Components in August. It may be assembling a components platform.</p></div>
        </div>
      </div>
    </>
  );
}

/* ---------------- Ask Radar ---------------- */
type Turn = { question: string; lead?: string; points?: [string, number][]; meaning?: string; confidence?: number; sources?: string[]; fallback?: boolean; suggestions?: string[]; generated_by?: string };

export function AskRadar() {
  const app = useApp();
  const co = app.cur;
  const [threads, setThreads] = useState<Record<string, Turn[]>>({});
  const [sugg, setSugg] = useState<string[]>([]);
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    api.askStart(co).then((r) => {
      setSugg(r.suggestions);
      setThreads((t) => (t[co] ? t : { ...t, [co]: [{ question: r.first.question, lead: r.first.lead, points: r.first.points, meaning: r.first.meaning, confidence: r.first.confidence, sources: r.first.sources }] }));
    });
  }, [co]);
  const list = threads[co] || [];
  const ask = async (q: string) => {
    if (!q.trim()) return;
    const a = await api.ask(co, q.trim());
    setThreads((t) => ({ ...t, [co]: [...(t[co] || []), a] }));
    setTimeout(() => endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" }), 50);
  };
  const src = [...list].reverse().find((t) => !t.fallback)?.sources || [];
  return (
    <>
    <div className="top"><div>
      <h1>Ask Radar</h1>
      <p className="sub">Ask about {co}'s competitors and M&amp;A signals in plain words. Each answer lists the sources it came from.</p>
      <ScopeNote />
    </div></div>
    <div className="cols">
      <div className="chat">
        {list.map((t, i) => (
          <div key={i} style={{ display: "contents" }}>
            <div className="q">{t.question}</div>
            {t.fallback ? (
              <div className="a fallback">
                <p style={{ margin: 0 }}>I don't have a confident answer for that yet. Here's what I can tell you about:</p>
                <div className="src" style={{ marginTop: 6 }}>{(t.suggestions || sugg).map((s) => <button key={s} type="button" className="askSug" onClick={() => ask(s)}><span>→</span><span>{s}</span></button>)}</div>
              </div>
            ) : (
              <div className="a">
                <p style={{ margin: 0 }}>{t.lead}</p>
                <ul>{t.points!.map((p, j) => <li key={j}>{p[0]}<sup>[{p[1]}]</sup></li>)}</ul>
                <p style={{ margin: 0 }}><b>What it means for {co}:</b> {t.meaning}</p>
                {t.generated_by
                  ? <span className="sub" style={{ fontSize: 12 }}>Drafted by {t.generated_by} from the radar's evidence · not fact-checked · {t.confidence}% confidence</span>
                  : <span className="verified">✓ Verified by 2+ sources · {t.confidence}% confidence</span>}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
        <form className="prompt" onSubmit={(e) => { e.preventDefault(); ask(text); setText(""); }}>
          <input type="text" id="askInput" placeholder={`Ask a follow-up about ${co}'s market…`} autoComplete="off" value={text} onChange={(e) => setText(e.target.value)} />
          <button type="submit" className="rbtn pri" id="askSend">Send</button>
        </form>
      </div>
      <div className="panel">
        <h5>Sources</h5><div className="src">{src.map((s, i) => <div key={i}><span>[{i + 1}]</span><p style={{ margin: 0 }}>{s}</p></div>)}</div>
        <h5 style={{ marginTop: 14 }}>Try asking</h5>
        <div className="src">{sugg.map((s) => <button key={s} type="button" className="askSug" onClick={() => ask(s)}><span>→</span><span>{s}</span></button>)}</div>
      </div>
    </div>
    </>
  );
}
