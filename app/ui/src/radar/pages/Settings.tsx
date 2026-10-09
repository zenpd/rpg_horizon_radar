/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import { api, type SchedulerStatus, type SignalJob, type SignalsStatus } from "../api";
import { sCls } from "../components/ui";
import { useApp } from "../state";

/* ---------------- Acquisition theses ---------------- */
export function Theses() {
  const app = useApp();
  const [list, setList] = useState<any[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [text, setText] = useState("Cable joint or heat-shrink makers in India, revenue ₹100–500 crore, family owned");
  const [desk, setDesk] = useState(app.companies[0]);
  const [parsed, setParsed] = useState<any>(null);
  useEffect(() => { api.theses().then((l) => { setList(l); setSel((s) => s ?? (l.find((t) => t.desk === app.cur) || l[0]).id); }); }, [app.version]);
  if (!list) return <p className="sub">Loading theses…</p>;
  const th = list.find((t) => t.id === sel) || list[0];
  const save = async () => {
    const t = await api.saveThesis(desk, text, parsed.criteria);
    app.toast("Thesis saved. Matches refresh in the next weekly run; shown now for the demo.");
    setParsed(null); setSel(t.id); app.bump();
  };
  return (
    <>
      <div className="top"><div>
        <h1>Acquisition thesis screener</h1>
        <p className="sub">Each RPG company writes what it wants to buy. Every company in the watched universe is checked against it each week.</p>
      </div></div>
      <div className="filters"><label>Thesis <select value={th.id} onChange={(e) => setSel(e.target.value)}>{list.map((x) => <option key={x.id} value={x.id}>{x.desk}: {x.text.slice(0, 60)}…</option>)}</select></label></div>
      <div className="panel"><h5>{th.desk} thesis</h5><p style={{ marginBottom: 8 }}>"{th.text}"</p><div className="crit">{th.criteria.map((c: string) => <span key={c}>{c}</span>)}</div></div>
      <div className="panel">
        <h5>Matching companies in the sector</h5>
        <table className="tbl">
          <thead><tr><th>Company</th><th>Match</th><th>Criteria met</th><th>Signal score</th></tr></thead>
          <tbody>
            {th.matches.map((r: any) => (
              <tr key={r.case_id}>
                <td><a href="#" onClick={(e) => { e.preventDefault(); app.openRow(r.case_id); }}>{r.name}</a><br /><span className="sub" style={{ fontSize: 11.5 }}>{r.category} · {r.geo}</span></td>
                <td style={{ minWidth: 140 }}><div className="match"><div className="pbar"><i style={{ width: `${r.pct}%` }} /></div>{r.pct}%</div></td>
                <td>{r.ok} of {r.total}</td>
                <td><span className={`score ${sCls(r.score)}`} style={{ height: 28, width: 44, display: "inline-flex" }}><b style={{ fontSize: 14 }}>{r.score}</b></span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <h5>Write a new thesis</h5>
        <p className="sub" style={{ fontSize: 12.5, marginBottom: 8 }}>Describe the target in plain words. An LLM turns it into criteria, and you confirm them before they are used.</p>
        <textarea className="th" id="thText" aria-label="New thesis" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="btns" style={{ marginTop: 8 }}>
          <label className="topctl">RPG company <select id="thDesk" value={desk} onChange={(e) => setDesk(e.target.value)}>{app.companies.map((d) => <option key={d}>{d}</option>)}</select></label>
          <button className="btnx pri" id="thParse" onClick={async () => setParsed(await api.parseThesis(text))}>Convert to criteria</button>
        </div>
        {parsed && (
          <div className="callout" style={{ marginTop: 10 }}>
            <b>Suggested criteria · please confirm</b>{parsed.parsed_by && parsed.parsed_by !== "rules" && <span className="sub" style={{ fontSize: 12 }}> · read by {parsed.parsed_by}</span>}
            <div className="crit">
              {parsed.labels.sector.map((s: string) => <span key={s}>Sector: {s}</span>)}
              {parsed.criteria.geo.map((g: string) => <span key={g}>Geography: {g}</span>)}
              <span>Revenue ₹{parsed.criteria.rev[0]}–{parsed.criteria.rev[1]} cr</span>
              {parsed.criteria.own.map((o: string) => <span key={o}>Ownership: {o}</span>)}
            </div>
            <div className="btns" style={{ marginTop: 8 }}><button className="btnx pri" id="thSave" onClick={save}>Confirm and save</button></div>
          </div>
        )}
      </div>
    </>
  );
}

// Which live sources have keys, which approved real companies each RPG company watches, and a
// manual refresh. Discovery only proposes companies; a compliance admin approves each one in
// Admin -> Watchlist before anything about it is fetched.
function LiveSources() {
  const app = useApp();
  const [s, setS] = useState<SignalsStatus | null>(null);
  const [sch, setSch] = useState<SchedulerStatus | null>(null);
  const [job, setJob] = useState<(SignalJob & { kind: "signals" | "rivals" }) | null>(null);
  useEffect(() => {
    api.signalsStatus().then(setS).catch((e) => app.toast(e.message));
    api.scheduler().then(setSch).catch(() => setSch(null));
  }, [app.version]);
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const poll = job.kind === "rivals" ? api.rivalJob : api.signalJob;
    const t = setTimeout(() => poll(job.id).then((j) => {
      setJob({ ...j, kind: job.kind });
      if (j.status === "completed") {
        const r: any = j.result;
        app.toast(job.kind === "rivals" ? `${r.found.length} new companies proposed; approve them in Admin → Watchlist${r.errors.length ? ` (${r.errors.length} errors)` : ""}` : `Fetched ${r.signals} new live signals`);
        app.bump();
      }
      if (j.status === "failed") app.toast(j.error || "Failed");
    }).catch((e) => app.toast(e.message)), 2000);
    return () => clearTimeout(t);
  }, [job]);
  if (!s) return null;
  const mapped = s.companies.filter((c) => c.real_name).length;
  const busy = job?.status === "running" || !!sch?.running;
  const tavily = s.sources.find((x) => x.name === "Tavily")?.configured;
  return (
    <div className="panel">
      <h5>Rivals and live data sources</h5>
      <p className="sub" style={{ fontSize: 12.5, marginTop: 0 }}>
        Rivals are real, listed companies. Discovery proposes them with its sources; a compliance admin approves each one
        (Admin → Watchlist) before any data about it is fetched, and only for RPG companies whose compliance gate is open.
        The approved rival with the most recent signals replaces the demo rival story in that company's SWOT.
      </p>
      <p className="sub" style={{ fontSize: 12.5, marginTop: 0 }}>
        {sch?.enabled
          ? <>Kept current automatically: discovery runs every {sch.rivals_every_days} days (next {sch.next?.rivals}); live signals refresh daily at {sch.signals_at} (next {sch.next?.signals})
              {sch.auto_rebuild ? ", and a company's SWOT is rebuilt when new signals arrive" : ""}.{sch.running ? ` Running now: ${sch.running}.` : ""}</>
          : "Automatic updates are off (SCHEDULER_ENABLED=false). Use the buttons below."}
        {sch?.last_error && <> Last error: {sch.last_error}</>}
      </p>
      <div className="crit">{s.sources.map((x) => <span key={x.name}>{x.configured ? "✓" : "○"} {x.name}{x.note ? ` · ${x.note}` : x.configured ? "" : " · no key"}</span>)}</div>
      <table className="tbl" style={{ marginTop: 10 }}>
        <thead><tr><th>RPG company</th><th>Rival tracked</th><th>Other rivals found</th><th>Live signals</th></tr></thead>
        <tbody>{s.companies.map((c) => (
          <tr key={c.company}>
            <td>{c.company}</td>
            <td>{c.real_name
              ? <><b>{c.real_name}</b>{c.stock_symbol && <span className="mono sub"> {c.stock_symbol}</span>}<br />
                  <span className="sub" style={{ fontSize: 11.5 }}>{c.rival_source === "manual" ? "set by hand" : `found ${c.rivals_found_at}`}</span>
                  {c.rival_source === "auto" && c.rivals_found[0] && <RivalWhy r={c.rivals_found[0]} />}</>
              : <span className="sub">{c.gate_open ? "none approved yet" : "compliance gate closed"} (demo: {c.rival_placeholder})</span>}</td>
            <td>{c.rivals_found.filter((r) => r.name !== c.real_name).map((r) => <div key={r.name}>{r.name}{r.status === "proposed" && <span className="sub"> · awaiting approval</span>} <RivalWhy r={r} /></div>)}</td>
            <td className="mono">{c.live_signals}</td>
          </tr>
        ))}</tbody>
      </table>
      {app.groupView && <div className="btnrow" style={{ alignItems: "center", gap: 10, marginTop: 10 }}>
        <button className="btnx" disabled={!tavily || busy} onClick={() => api.findRivals().then((j) => setJob({ ...j, kind: "rivals" })).catch((e) => app.toast(e.message))}>
          {job?.kind === "rivals" && job.status === "running" ? "Finding rivals…" : "Propose rivals now"}
        </button>
        <button className="btnx pri" disabled={!mapped || busy} onClick={() => api.refreshSignals().then((j) => setJob({ ...j, kind: "signals" })).catch((e) => app.toast(e.message))}>
          {job?.kind === "signals" && job.status === "running" ? "Fetching live signals…" : "Refresh live signals"}
        </button>
        <span className="sub" style={{ fontSize: 12 }}>
          {s.last_refresh ? `Last refresh ${s.last_refresh}` : "Never refreshed"} · Approve, dismiss or add companies in Admin → Watchlist
        </span>
      </div>}
      {s.errors.length > 0 && <ul className="sub" style={{ fontSize: 12 }}>{s.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
    </div>
  );
}

// Why the Rival Finder counts a company as a rival, with the pages that name it.
function RivalWhy({ r }: { r: SignalsStatus["companies"][number]["rivals_found"][number] }) {
  return (
    <details className="rivalwhy"><summary className="sub">why</summary>
      <span>{r.why}</span>{" "}
      {r.sources.map((x, i) => <a key={x.url} href={x.url} target="_blank" rel="noreferrer" title={x.title}>[{i + 1}]</a>)}
    </details>
  );
}

/* ---------------- Watch rules ---------------- */
export function WatchRules() {
  const app = useApp();
  const [list, setList] = useState<any[] | null>(null);
  const [form, setForm] = useState({ desk: app.groupView ? "All" : app.companies[0], metric: "score", op: "above", val: "50" });
  const load = () => api.triggers().then(setList);
  useEffect(() => { load(); }, [app.version]);
  if (!list) return <p className="sub">Loading watch rules…</p>;
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const t = await api.addTrigger({ ...form, company: app.scope });
    app.toast(`Rule added. ${t.hits.length} compan${t.hits.length === 1 ? "y matches" : "ies match"} right now.`);
    load();
  };
  return (
    <>
      <div className="top"><div>
        <h1>Watch rules</h1>
        <p className="sub">Rules set by each strategy team. Checked after every daily run.</p>
      </div></div>
      <div className="panel">
        <h5>Your rules</h5>
        <table className="tbl">
          <thead><tr><th>On</th><th>Rule</th><th>RPG company</th><th>Firing now</th><th /></tr></thead>
          <tbody>
            {list.map((tr) => (
              <tr key={tr.id}>
                <td><button className="btnx" aria-pressed={tr.on} aria-label={tr.on ? "Turn off" : "Turn on"} style={{ padding: "2px 6px" }} onClick={async () => { await api.toggleTrigger(tr.id, !tr.on); load(); }}><span className={`toggle${tr.on ? " on" : ""}`} /></button></td>
                <td><b>{tr.text}</b></td><td>{tr.desk}</td>
                <td>{tr.on ? (tr.hits.length ? tr.hits.map((h: any) => <a key={h.case_id} href="#" className="pill2 fired" style={{ marginRight: 4 }} onClick={(e) => { e.preventDefault(); app.openRow(h.case_id); }}>{h.name.split(" ")[0]}</a>) : <span className="pill2">none</span>) : <span className="pill2">off</span>}</td>
                <td><button className="btnx" onClick={async () => { await api.deleteTrigger(tr.id); load(); }}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <h5>Add a rule</h5>
        <form className="frm" onSubmit={add}>
          <label>RPG company<select id="trDesk" value={form.desk} onChange={(e) => setForm({ ...form, desk: e.target.value })}>{(app.groupView ? ["All", ...app.companies] : app.companies).map((d) => <option key={d}>{d}</option>)}</select></label>
          <label>Metric<select id="trMetric" value={form.metric} onChange={(e) => setForm({ ...form, metric: e.target.value })}>
            <option value="score">Opportunity score</option><option value="pledge">Promoter pledge %</option><option value="rating">Credit rating</option><option value="insolvency">Insolvency filed</option><option value="rivalstake">New stake by a rival</option>
          </select></label>
          <label>Condition<select id="trOp" value={form.op} onChange={(e) => setForm({ ...form, op: e.target.value })}><option>above</option><option>below</option><option>is</option></select></label>
          <label>Value<input id="trVal" value={form.val} onChange={(e) => setForm({ ...form, val: e.target.value })} /></label>
          <button className="btnx pri" type="submit">Add rule</button>
        </form>
      </div>
    </>
  );
}

/* ---------------- Watched companies and activity ---------------- */
export function Watched() {
  const app = useApp();
  const [u, setU] = useState<any[] | null>(null);
  const [act, setAct] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [desk, setDesk] = useState(app.cur);
  useEffect(() => { api.universe().then(setU); if (app.groupView) api.activity().then(setAct).catch(() => setAct([])); }, [app.version]);
  if (!u) return <p className="sub">Loading…</p>;
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.addUniverse(name, desk);
    app.toast("Company added. It will be scanned from the next daily run.");
    setName(""); app.bump();
  };
  return (
    <>
      <div className="top"><div>
        <h1>Watched companies and activity</h1>
        <p className="sub">The sector universe the radar scans every day, and a log of changes made in this demo.</p>
      </div></div>
      <div className="cols even">
        <div className="panel">
          <h5>Sector universe · {u.length} companies watched</h5>
          <table className="tbl"><thead><tr><th>Company</th><th>RPG company</th><th>Sector</th><th>How added</th></tr></thead>
            <tbody>{u.map((x, i) => <tr key={i}><td>{x.company}</td><td>{x.desk}</td><td>{x.sector}</td><td>{x.added}</td></tr>)}</tbody></table>
          <form className="frm" style={{ marginTop: 10 }} onSubmit={add}>
            <label>Company<input id="uName" placeholder="Company name" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label>RPG company<select id="uDesk" value={desk} onChange={(e) => setDesk(e.target.value)}>{app.companies.map((d) => <option key={d}>{d}</option>)}</select></label>
            <button className="btnx pri" type="submit">Add to universe</button>
          </form>
        </div>
        {app.groupView && <div className="panel">
          <h5>Activity · {act.length} changes</h5>
          <table className="tbl"><thead><tr><th>Time</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
            <tbody>{act.map((a, i) => <tr key={i}><td className="mono">{a.time}</td><td>{a.who}</td><td>{a.action}</td><td>{a.detail}</td></tr>)}</tbody></table>
          <p className="sub" style={{ fontSize: 12, marginTop: 8 }}>Escalations, decisions, plans, theses, rules and universe changes appear here. Every view and change is also in the immutable audit log (Admin → Audit Log).</p>
        </div>}
      </div>
      <LiveSources />
    </>
  );
}
