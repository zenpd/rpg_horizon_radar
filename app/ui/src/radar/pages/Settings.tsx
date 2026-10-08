/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import { api, type SchedulerStatus, type SignalJob, type SignalsStatus, type SwotParams, type SwotParamsAll, type WatchedCompany } from "../api";
import { useApp } from "../state";

/* ---------------- Acquisition theses ---------------- */
export function Theses() {
  const app = useApp();
  const [list, setList] = useState<any[] | null>(null);
  const [sectors, setSectors] = useState<Record<string, string>>({});
  const [sel, setSel] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [desk, setDesk] = useState(app.companies[0]);
  const [parsed, setParsed] = useState<any>(null);
  useEffect(() => { api.reference().then((r) => setSectors(r.sector_labels)); }, []);
  useEffect(() => { api.theses().then((l) => { setList(l); setSel((s) => s ?? (l.find((t) => t.desk === app.cur) || l[0])?.id ?? null); }); }, [app.version]);
  if (!list) return <p className="sub">Loading theses…</p>;
  const th = list.find((t) => t.id === sel) || list[0];
  const pick = (k: string, on: boolean) => setParsed({ ...parsed, criteria: { ...parsed.criteria, sector: on ? [...parsed.criteria.sector, k] : parsed.criteria.sector.filter((x: string) => x !== k) } });
  const save = async () => {
    try {
      const t = await api.saveThesis(desk, text, parsed.criteria);
      app.toast("Thesis saved.");
      setParsed(null); setText(""); setSel(t.id); app.bump();
    } catch (e) { app.toast((e as Error).message); }
  };
  return (
    <>
      <div className="top"><div>
        <span className="crumb"><b>Radar settings</b> / Acquisition theses</span><h4>Acquisition theses</h4>
        <p className="sub">Each RPG company writes what it wants to buy, turned into criteria it confirms.</p>
      </div></div>
      {th ? (
        <>
          <div className="filters"><label>Thesis <select value={th.id} onChange={(e) => setSel(e.target.value)}>{list.map((x) => <option key={x.id} value={x.id}>{x.desk}: {x.text.slice(0, 60)}{x.text.length > 60 ? "…" : ""}</option>)}</select></label></div>
          <div className="panel"><h5>{th.desk} thesis</h5><p style={{ marginBottom: 8 }}>"{th.text}"</p><div className="crit">{th.criteria.map((c: string) => <span key={c}>{c}</span>)}</div></div>
          <div className="panel">
            <h5>Matching companies</h5>
            <p className="sub" style={{ margin: 0 }}>None yet. Matching needs sourced acquisition targets with sector, revenue and ownership data, which the radar does not have yet.</p>
          </div>
        </>
      ) : <div className="empty2" style={{ padding: 20 }}>No theses yet. Write the first one below.</div>}
      <div className="panel">
        <h5>Write a new thesis</h5>
        <p className="sub" style={{ fontSize: 12.5, marginBottom: 8 }}>Describe the target in plain words. It is turned into criteria, and you confirm them before they are saved.</p>
        <textarea className="th" id="thText" aria-label="New thesis" placeholder="e.g. Cable joint or heat-shrink makers in India, revenue ₹100–500 crore, family owned" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="btns" style={{ marginTop: 8 }}>
          <label className="topctl">RPG company <select id="thDesk" value={desk} onChange={(e) => setDesk(e.target.value)}>{app.companies.map((d) => <option key={d}>{d}</option>)}</select></label>
          <button className="btnx pri" id="thParse" disabled={text.trim().length < 3} onClick={async () => setParsed(await api.parseThesis(text))}>Convert to criteria</button>
        </div>
        {parsed && (
          <div className="callout" style={{ marginTop: 10 }}>
            <b>Suggested criteria · please confirm</b>{parsed.parsed_by && parsed.parsed_by !== "rules" && <span className="sub" style={{ fontSize: 12 }}> · read by {parsed.parsed_by}</span>}
            <p className="sub" style={{ fontSize: 12.5, margin: "6px 0 2px" }}>Sectors:</p>
            <div className="crit">
              {Object.entries(sectors).map(([k, label]) => (
                <label key={k} style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                  <input type="checkbox" checked={parsed.criteria.sector.includes(k)} onChange={(e) => pick(k, e.target.checked)} />{label}
                </label>
              ))}
            </div>
            <div className="crit" style={{ marginTop: 6 }}>
              {parsed.criteria.geo.map((g: string) => <span key={g}>Geography: {g}</span>)}
              {parsed.criteria.rev[1] < 99999 && <span>Revenue ₹{parsed.criteria.rev[0]}–{parsed.criteria.rev[1]} cr</span>}
              {parsed.criteria.own.map((o: string) => <span key={o}>Ownership: {o}</span>)}
            </div>
            <div className="btns" style={{ marginTop: 8 }}><button className="btnx pri" id="thSave" disabled={!parsed.criteria.sector.length} onClick={save}>Confirm and save</button></div>
          </div>
        )}
      </div>
    </>
  );
}

// Which live sources have keys, which real companies each RPG company watches, and a manual
// refresh. Companies discovery finds are watched at once.
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
        app.toast(job.kind === "rivals" ? `${r.found.length} new companies added to the watchlist${r.errors.length ? ` (${r.errors.length} errors)` : ""}` : `Fetched ${r.signals} new live signals`);
        app.bump();
      }
      if (j.status === "failed") app.toast(j.error || "Failed");
    }).catch((e) => app.toast(e.message)), 2000);
    return () => clearTimeout(t);
  }, [job]);
  if (!s) return null;
  const watched = s.companies.reduce((n, c) => n + c.companies.filter((x) => x.status === "watching").length, 0);
  const busy = job?.status === "running" || !!sch?.running;
  const tavily = s.sources.find((x) => x.name === "Tavily")?.configured;
  return (
    <div className="panel">
      <h5>Watched companies and live data sources</h5>
      <p className="sub" style={{ fontSize: 12.5, marginTop: 0 }}>
        Watched companies are real, listed companies. Discovery finds them with its sources and they are watched at once; remove or
        add companies in Users and watchlist → Watchlist.
      </p>
      <p className="sub" style={{ fontSize: 12.5, marginTop: 0 }}>
        {sch?.enabled
          ? <>Kept current automatically, once a day at {sch.signals_at} (next {sch.next?.signals}): the radar collects the news, then runs everything that searches from it and saves the results — the Opportunity Analyst, the Sector Scout, company sizes, and the theses and overviews the news changed.
              Discovery runs with that daily run every {sch.rivals_every_days} days (next {sch.next?.rivals}), and the SWOT Analyst every {sch.swot_every_days} days (next {sch.next?.swot}). Restarting the app starts no searches.
              {sch.running ? ` Running now: ${sch.running}.` : ""}</>
          : "Automatic updates are off (SCHEDULER_ENABLED=false). Use the buttons below."}
        {sch?.last_error && <> Last error: {sch.last_error}</>}
      </p>
      <div className="crit">{s.sources.map((x) => <span key={x.name}>{x.configured ? "✓" : "○"} {x.name}{x.note ? ` · ${x.note}` : x.configured ? "" : " · no key"}</span>)}</div>
      <table className="tbl" style={{ marginTop: 10 }}>
        <thead><tr><th>RPG company</th><th>Watching</th><th>Live signals</th></tr></thead>
        <tbody>{s.companies.map((c) => (
          <tr key={c.company}>
            <td>{c.company}</td>
            <td>{c.companies.filter((x) => x.status === "watching").map((x) => (
              <div key={x.name}><b>{x.name}</b>{x.stock_symbol && <span className="mono sub"> {x.stock_symbol}</span>}
                <span className="sub" style={{ fontSize: 11.5 }}> · {x.origin === "manual" ? "added by hand" : `found ${x.found_at}`}</span>{x.why && <RivalWhy r={x} />}</div>
            ))}{!c.companies.some((x) => x.status === "watching") && <span className="sub">none</span>}</td>
            <td className="mono">{c.live_signals}</td>
          </tr>
        ))}</tbody>
      </table>
      <div className="btnrow" style={{ alignItems: "center", gap: 10, marginTop: 10 }}>
        <button className="btnx" disabled={!tavily || busy} onClick={() => api.findRivals().then((j) => setJob({ ...j, kind: "rivals" })).catch((e) => app.toast(e.message))}>
          {job?.kind === "rivals" && job.status === "running" ? "Finding rivals…" : "Find rivals now"}
        </button>
        <button className="btnx pri" disabled={!watched || busy} onClick={() => api.refreshSignals().then((j) => setJob({ ...j, kind: "signals" })).catch((e) => app.toast(e.message))}>
          {job?.kind === "signals" && job.status === "running" ? "Fetching live signals…" : "Refresh live signals"}
        </button>
        <span className="sub" style={{ fontSize: 12 }}>
          {s.last_refresh ? `Last refresh ${s.last_refresh}` : "Never refreshed"} · Remove or add companies in Users and watchlist → Watchlist
        </span>
      </div>
      {s.errors.length > 0 && <ul className="sub" style={{ fontSize: 12 }}>{s.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
    </div>
  );
}

// Why discovery found a company, with the pages that name it.
function RivalWhy({ r }: { r: WatchedCompany }) {
  return (
    <details className="rivalwhy"><summary className="sub">why</summary>
      <span>{r.why}</span>{" "}
      {r.sources.map((x, i) => <a key={x.url} href={x.url} target="_blank" rel="noreferrer" title={x.title}>[{i + 1}]</a>)}
    </details>
  );
}

/* ---------------- SWOT parameters ---------------- */
export function SwotParameters() {
  const app = useApp();
  const [all, setAll] = useState<SwotParamsAll | null>(null);
  const [sch, setSch] = useState<SchedulerStatus | null>(null);
  const [co, setCo] = useState(app.cur);
  const [form, setForm] = useState<SwotParams | null>(null);
  const [queries, setQueries] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { api.swotSettings().then(setAll).catch((e) => app.toast(e.message)); api.scheduler().then(setSch).catch(() => setSch(null)); }, [app.version]);
  useEffect(() => {
    const p = all?.companies.find((c) => c.company === co);
    if (p) { setForm(p); setQueries(p.sector_queries.join("\n")); }
  }, [all, co]);
  if (!all || !form) return <p className="sub">Loading SWOT parameters…</p>;
  const flip = (k: "sources" | "factors", key: string) =>
    setForm({ ...form, [k]: form[k].includes(key) ? form[k].filter((x) => x !== key) : [...form[k], key] });
  const save = async (rebuild: boolean) => {
    setSaving(true);
    try {
      await api.saveSwotSettings(co, { sources: form.sources, factors: form.factors, sector_queries: queries.split("\n").map((x) => x.trim()).filter(Boolean) });
      if (rebuild) await api.rebuildSwot(co, true);
      app.toast(rebuild ? `Saved. The SWOT Analyst is rebuilding ${co}'s SWOT; it shows on Self analysis when done.` : `Saved. ${co}'s next weekly SWOT uses these parameters.`);
      app.bump();
    } catch (e) { app.toast((e as Error).message); } finally { setSaving(false); }
  };
  const box = (k: "sources" | "factors", x: { key: string; label: string }) => (
    <label key={x.key} className="chk"><input type="checkbox" checked={form[k].includes(x.key)} onChange={() => flip(k, x.key)} /> {x.label}</label>
  );
  return (
    <>
      <div className="top"><div>
        <span className="crumb"><b>Radar settings</b> / SWOT parameters</span><h4>SWOT parameters</h4>
        <p className="sub">What the SWOT Analyst reads and judges each RPG company on, and the industry news the Opportunity Analyst reads every day.
          {sch?.next ? ` Next weekly SWOT: ${sch.next.swot}. Next daily opportunities: ${sch.next.opportunities}.` : ""}</p>
      </div></div>
      <div className="filters"><label>RPG company <select value={co} onChange={(e) => setCo(e.target.value)}>{app.companies.map((x) => <option key={x}>{x}</option>)}</select></label></div>
      <div className="cols even">
        <div className="panel">
          <h5>Evidence sources</h5>
          <p className="sub" style={{ fontSize: 12, marginTop: 0 }}>What is collected and may be cited. Strengths and weaknesses need at least one source about the company itself.</p>
          <div className="chkgrid">{all.sources.map((x) => box("sources", x))}</div>
        </div>
        <div className="panel">
          <h5>Analysis factors</h5>
          <p className="sub" style={{ fontSize: 12, marginTop: 0 }}>What {co} is judged on. The research searches the web for each ticked factor, and every SWOT item is tagged with one.</p>
          <div className="chkgrid">{all.factors.map((x) => box("factors", x))}</div>
        </div>
      </div>
      <div className="panel">
        <h5>Industry news searches</h5>
        <p className="sub" style={{ fontSize: 12, marginTop: 0 }}>One search per line (up to 6). The Opportunity Analyst reads these every day, with news about {co} and the companies it watches.</p>
        <textarea className="th" rows={4} value={queries} onChange={(e) => setQueries(e.target.value)} placeholder="e.g. natural rubber prices" />
      </div>
      <div className="btnrow">
        <button className="btnx pri" disabled={saving} onClick={() => save(false)}>Save</button>
        <button className="btnx" disabled={saving} onClick={() => save(true)}>Save and rebuild {co}'s SWOT now</button>
      </div>
    </>
  );
}

/* ---------------- Watch rules ---------------- */
export function WatchRules() {
  const app = useApp();
  const [list, setList] = useState<any[] | null>(null);
  const [form, setForm] = useState({ desk: "All", op: "above", val: "50" });
  const load = () => api.triggers().then(setList);
  useEffect(() => { load(); }, [app.version]);
  if (!list) return <p className="sub">Loading watch rules…</p>;
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    let t;
    try { t = await api.addTrigger({ desk: form.desk, op: form.op, val: Number(form.val), company: app.scope }); } catch (err) { app.toast((err as Error).message); return; }
    app.toast(`Rule added. ${t.hits.length} compan${t.hits.length === 1 ? "y matches" : "ies match"} right now.`);
    load();
  };
  return (
    <>
      <div className="top"><div>
        <span className="crumb"><b>Radar settings</b> / Watch rules</span><h4>Alert me when…</h4>
        <p className="sub">Rules set by each strategy team, checked against the watched companies' rule-based scores.</p>
      </div></div>
      <div className="panel">
        <h5>Your rules</h5>
        <table className="tbl">
          <thead><tr><th>On</th><th>Rule</th><th>RPG company</th><th>Firing now</th><th /></tr></thead>
          <tbody>
            {!list.length && <tr><td colSpan={5} className="sub">No rules yet.</td></tr>}
            {list.map((tr) => (
              <tr key={tr.id}>
                <td><button className="btnx" aria-pressed={tr.on} aria-label={tr.on ? "Turn off" : "Turn on"} style={{ padding: "2px 6px" }} onClick={async () => { await api.toggleTrigger(tr.id, !tr.on); load(); }}><span className={`toggle${tr.on ? " on" : ""}`} /></button></td>
                <td><b>{tr.text}</b></td><td>{tr.desk}</td>
                <td>{tr.on ? (tr.hits.length ? tr.hits.map((h: any) => <a key={h.case_id} href="#" className="pill2 fired" style={{ marginRight: 4 }} onClick={(e) => { e.preventDefault(); app.openRow(h.case_id); }}>{h.name}</a>) : <span className="pill2">none</span>) : <span className="pill2">off</span>}</td>
                <td><button className="btnx" onClick={async () => { await api.deleteTrigger(tr.id); load(); }}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <h5>Add a rule</h5>
        <form className="frm" onSubmit={add}>
          <label>RPG company<select id="trDesk" value={form.desk} onChange={(e) => setForm({ ...form, desk: e.target.value })}>{(["All", ...app.companies]).map((d) => <option key={d}>{d}</option>)}</select></label>
          <label>Metric<select id="trMetric" disabled><option>Opportunity score</option></select></label>
          <label>Condition<select id="trOp" value={form.op} onChange={(e) => setForm({ ...form, op: e.target.value })}><option>above</option><option>below</option></select></label>
          <label>Value (0–100)<input id="trVal" type="number" min={0} max={100} value={form.val} onChange={(e) => setForm({ ...form, val: e.target.value })} /></label>
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
  useEffect(() => { api.universe().then(setU); api.activity().then(setAct).catch(() => setAct([])); }, [app.version]);
  if (!u) return <p className="sub">Loading…</p>;
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.addUniverse(name, desk);
    app.toast("Company added to the universe list.");
    setName(""); app.bump();
  };
  return (
    <>
      <div className="top"><div>
        <span className="crumb"><b>Radar settings</b> / Watched companies</span><h4>Watched companies and activity</h4>
        <p className="sub">Companies each strategy team wants on its radar, the live sources, and a log of what people changed.</p>
      </div></div>
      <div className="cols even">
        <div className="panel">
          <h5>Universe · {u.length} compan{u.length === 1 ? "y" : "ies"}</h5>
          <p className="sub" style={{ fontSize: 12, marginTop: 0 }}>A team's own list. Data is fetched for the companies on the watchlist (Users and watchlist → Watchlist).</p>
          <table className="tbl"><thead><tr><th>Company</th><th>RPG company</th><th>How added</th></tr></thead>
            <tbody>{u.length ? u.map((x, i) => <tr key={i}><td>{x.company}</td><td>{x.desk}</td><td className="mono">{x.added}</td></tr>) : <tr><td colSpan={3} className="sub">None yet.</td></tr>}</tbody></table>
          <form className="frm" style={{ marginTop: 10 }} onSubmit={add}>
            <label>Company<input id="uName" placeholder="Company name" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label>RPG company<select id="uDesk" value={desk} onChange={(e) => setDesk(e.target.value)}>{app.companies.map((d) => <option key={d}>{d}</option>)}</select></label>
            <button className="btnx pri" type="submit">Add to universe</button>
          </form>
        </div>
        <div className="panel">
          <h5>Activity · {act.length} changes</h5>
          <table className="tbl"><thead><tr><th>Time</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
            <tbody>{act.length ? act.map((a, i) => <tr key={i}><td className="mono">{a.time}</td><td>{a.who}</td><td className="mono">{a.action}</td><td>{a.detail}</td></tr>) : <tr><td colSpan={4} className="sub">Nothing yet.</td></tr>}</tbody></table>
          <p className="sub" style={{ fontSize: 12, marginTop: 8 }}>Escalations, decisions, plans, theses, rules and universe changes appear here. Every view and change is also in Users and watchlist → Activity.</p>
        </div>
      </div>
      <LiveSources />
    </>
  );
}


/* ---------------- Radar settings: one screen, four tabs ---------------- */
const SETTINGS_TABS = [["thesis", "Acquisition theses"], ["params", "SWOT parameters"], ["rules", "Watch rules"], ["watched", "Watched companies"]] as const;

export function RadarSettings() {
  const [tab, setTab] = useState<(typeof SETTINGS_TABS)[number][0]>("thesis");
  return (
    <>
      <div className="kfilter" role="tablist" aria-label="Radar settings">
        {SETTINGS_TABS.map(([k, l]) => <button key={k} type="button" role="tab" aria-pressed={k === tab} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === "thesis" && <Theses />}
      {tab === "params" && <SwotParameters />}
      {tab === "rules" && <WatchRules />}
      {tab === "watched" && <Watched />}
    </>
  );
}
