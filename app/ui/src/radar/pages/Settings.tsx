/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import {
  api,
  type AcquisitionThesisAssessment,
  type AcquisitionThesisDraft,
  type AcquisitionThesisOptions,
  type AcquisitionTargetRefreshJob,
  type SchedulerStatus,
  type SignalJob,
  type SignalsStatus,
  type SwotJob,
  type SwotQuadrant,
  type ThesisSwotInput,
} from "../api";
import { sCls } from "../components/ui";
import { useApp } from "../state";

/* ---------------- Acquisition theses ---------------- */
const SWOT_FIELDS: [SwotQuadrant, string][] = [["S", "Strengths"], ["W", "Weaknesses"], ["O", "Opportunities"], ["T", "Threats"]];

function SwotList({ title, swot, rationale = false }: {
  title: string;
  swot: Record<SwotQuadrant, { text: string; source?: string; source_url?: string | null; basis?: string; rationale?: string }[]>;
  rationale?: boolean;
}) {
  return <div className="panel">
    <h5>{title}</h5>
    {SWOT_FIELDS.map(([key, label]) => <div key={key} style={{ marginBottom: 10 }}>
      <b>{label}</b>
      <ul style={{ margin: "3px 0", paddingLeft: 18 }}>
        {swot[key].map((item, index) => <li key={`${key}-${index}`}>
          {item.text}
          {item.basis && <span className="mini"> · {item.basis === "assumption" ? "Assumption" : item.basis === "baseline" ? "Acquirer baseline" : "Target today"}</span>}
          {item.source && <div className="sub">Source: {item.source_url
            ? <a href={item.source_url} target="_blank" rel="noreferrer">{item.source}</a>
            : item.source}</div>}
          {rationale && item.rationale && <div className="sub">Why: {item.rationale}</div>}
        </li>)}
      </ul>
      {!swot[key].length && <p className="sub">No supported findings in the available evidence.</p>}
    </div>)}
  </div>;
}

export function Theses() {
  const app = useApp();
  const [list, setList] = useState<any[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [text, setText] = useState("Cable joint or heat-shrink makers in India, revenue ₹100–500 crore, family owned");
  const [desk, setDesk] = useState(app.cur === "All" ? app.companies[0] : app.cur);
  const [parsed, setParsed] = useState<any>(null);
  const [acqOptions, setAcqOptions] = useState<AcquisitionThesisOptions | null>(null);
  const [targetId, setTargetId] = useState("");
  const [targetText, setTargetText] = useState("");
  const [currentSwot, setCurrentSwot] = useState<ThesisSwotInput | null>(null);
  const [draft, setDraft] = useState<AcquisitionThesisDraft | null>(null);
  const [assessments, setAssessments] = useState<AcquisitionThesisAssessment[]>([]);
  const [drafting, setDrafting] = useState(false);
  const [savingAssessment, setSavingAssessment] = useState(false);
  const [baselineJob, setBaselineJob] = useState<SwotJob | null>(null);
  const [baselineError, setBaselineError] = useState("");
  const [generatingCurrentSwot, setGeneratingCurrentSwot] = useState(false);
  const [refreshingTarget, setRefreshingTarget] = useState<AcquisitionTargetRefreshJob | null>(null);
  useEffect(() => { api.theses().then((l) => { setList(l); setSel((s) => s ?? (l.find((t) => t.desk === app.cur) || l[0]).id); }); }, [app.version]);
  useEffect(() => {
    if (!desk) return;
    api.acquisitionThesisOptions(desk).then((options) => {
      setAcqOptions(options);
      setTargetId((current) => options.targets.some((target) => target.id === current) ? current : options.targets[0]?.id || "");
      setAssessments(options.existing);
      if (options.baseline_source.by !== "agent") {
        setBaselineError("");
        api.buildAcquisitionBaseline(desk).then(setBaselineJob).catch((error) => {
          setBaselineError((error as Error).message);
        });
      }
    }).catch((error) => app.toast((error as Error).message));
  }, [desk, app.version]);
  useEffect(() => {
    if (!baselineJob) return;
    if (baselineJob.status === "completed") {
      setBaselineJob(null);
      app.bump();
      return;
    }
    if (baselineJob.status === "failed") {
      setBaselineError(baselineJob.error || "The SWOT Analyst could not build the baseline.");
      setBaselineJob(null);
      return;
    }
    const timer = window.setTimeout(() => {
      api.swotJob(baselineJob.id).then(setBaselineJob).catch((error) => {
        setBaselineError((error as Error).message);
        setBaselineJob(null);
      });
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [baselineJob]);
  useEffect(() => {
    if (!refreshingTarget || refreshingTarget.status !== "running") return;
    const timer = window.setTimeout(() => {
      api.acquisitionTargetJob(refreshingTarget.id).then((job) => {
        setRefreshingTarget(job);
        if (job.status === "completed") {
          if (job.result?.errors.length) {
            app.toast(`Fetched ${job.result.new_signals} new signals; some sources failed: ${job.result.errors.join("; ")}`);
          } else {
            app.toast(`Fetched ${job.result?.new_signals || 0} new signals for ${job.result?.target_name}.`);
          }
          api.acquisitionThesisOptions(desk).then(setAcqOptions).catch((error) => app.toast((error as Error).message));
        } else if (job.status === "failed") {
          app.toast(job.error || "Live signal refresh failed.");
        }
      }).catch((error) => {
        app.toast((error as Error).message);
        setRefreshingTarget(null);
      });
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [refreshingTarget, desk]);
  useEffect(() => {
    setDraft(null);
    setCurrentSwot(null);
  }, [targetId]);
  if (!list) return <p className="sub">Loading theses…</p>;
  const th = list.find((t) => t.id === sel) || list[0];
  const selectedTarget = acqOptions?.targets.find((target) => target.id === targetId);
  const baselineReady = acqOptions?.baseline_source.by === "agent";
  const generateCurrentSwot = async () => {
    if (!targetId) return;
    try {
      setGeneratingCurrentSwot(true);
      setDraft(null);
      const result = await api.generateTargetCurrentSwot(desk, targetId);
      setCurrentSwot(result.current_swot);
      app.toast(`Current SWOT generated from ${result.evidence_count} live-source signals (${result.generated_by}).`);
    } catch (error) {
      setCurrentSwot(null);
      app.toast((error as Error).message);
    } finally {
      setGeneratingCurrentSwot(false);
    }
  };
  const refreshTargetSignals = async () => {
    if (!targetId) return;
    setCurrentSwot(null);
    setDraft(null);
    try {
      setRefreshingTarget(await api.refreshAcquisitionTarget(desk, targetId));
    } catch (error) {
      app.toast((error as Error).message);
    }
  };
  const draftSwot = async () => {
    try {
      if (!currentSwot) throw new Error("Generate the target's current SWOT from live evidence first.");
      setDrafting(true);
      const result = await api.draftAcquisitionSwot(desk, targetId, targetText, currentSwot);
      setDraft(result);
      app.toast("Post-acquisition SWOT draft is ready. Review it before saving.");
    } catch (error) {
      app.toast((error as Error).message);
    } finally {
      setDrafting(false);
    }
  };
  const saveAssessment = async () => {
    if (!draft || !targetId || !currentSwot) return;
    try {
      setSavingAssessment(true);
      const saved = await api.saveAcquisitionThesis(desk, targetId, targetText, currentSwot, draft.post_acquisition_swot);
      setAssessments((items) => [saved, ...items.filter((item) => item.id !== saved.id)]);
      setDraft(null);
      setTargetText("");
      app.toast(`Confirmed acquisition thesis saved for ${saved.target_name}.`);
      app.bump();
    } catch (error) {
      app.toast((error as Error).message);
    } finally {
      setSavingAssessment(false);
    }
  };
  const save = async () => {
    const t = await api.saveThesis(desk, text, parsed.criteria);
    app.toast("Thesis saved. Matches refresh in the next weekly run; shown now for the demo.");
    setParsed(null); setSel(t.id); app.bump();
  };
  return (
    <>
      <div className="top"><div>
        <span className="crumb"><b>Radar settings</b> / Acquisition theses</span><h4>Acquisition theses</h4>
        <p className="sub">Create a thesis for a specific target. Compare the acquirer’s baseline SWOT, the target’s current SWOT, and a reviewer-confirmed post-acquisition SWOT.</p>
      </div></div>
      <div className="panel">
        <h5>Target-specific acquisition thesis</h5>
        <p className="sub">Select a real target already approved in Admin → Watchlist. The target’s current SWOT is generated from collected live-source signals, with citations. The AI then drafts the combined post-acquisition SWOT; a reviewer confirms it before saving.</p>
        <div className="filters">
          <label>Acquiring RPG company<select value={desk} onChange={(e) => setDesk(e.target.value)}>{app.companies.map((company) => <option key={company}>{company}</option>)}</select></label>
          <label>Acquisition target<select value={targetId} disabled={!acqOptions?.targets.length} onChange={(e) => setTargetId(e.target.value)}>
            {!acqOptions?.targets.length && <option value="">{acqOptions ? "No approved live targets available" : "Loading approved targets…"}</option>}
            {acqOptions?.targets.map((target) => <option key={target.id} value={target.id}>{target.name} · approved live target</option>)}
          </select></label>
        </div>
        {selectedTarget ? <>
          <div className="callout" style={{ marginTop: 10 }}>
            <b>{selectedTarget.name} · {selectedTarget.sector || selectedTarget.business}</b>
            <p>Approved watchlist company · {selectedTarget.live_signal_count} collected live signals in the last 120 days.</p>
          </div>
          {acqOptions && <>
            <SwotList title={`Baseline SWOT · ${desk} before the deal`} swot={acqOptions.baseline_swot} />
            <p className="sub">
              {acqOptions.baseline_source.by === "agent"
                ? `Automatically generated by the SWOT Analyst (${acqOptions.baseline_source.model}) from ${acqOptions.baseline_source.evidence?.live || 0} live, ${acqOptions.baseline_source.evidence?.demo || 0} demo, and ${acqOptions.baseline_source.evidence?.team || 0} team evidence items.`
                : "The SWOT Analyst is automatically creating the baseline from the available company evidence. Until it finishes, the list above is demo data."}
            </p>
            {baselineJob && <p className="sub" role="status">Creating baseline SWOT… review round {baselineJob.round} of {baselineJob.max_rounds}.</p>}
            {baselineError && <div className="box" role="alert">Automatic baseline generation failed: {baselineError}. The visible baseline is still demo data.</div>}
          </>}
          <h5>Current SWOT · {selectedTarget.name} today</h5>
          <p className="sub">First fetch this approved target’s latest live signals. Then generate a current SWOT with citations; unsupported quadrants stay empty.</p>
          <button className="btnx" disabled={refreshingTarget?.status === "running"} onClick={refreshTargetSignals}>
            {refreshingTarget?.status === "running" ? "Fetching live signals…" : "Fetch live signals for this target"}
          </button>
          {refreshingTarget?.status === "completed" && refreshingTarget.result && <p className="sub" role="status">
            Refresh complete: {refreshingTarget.result.new_signals} new signals; {refreshingTarget.result.live_signal_count} live signals available.
            {refreshingTarget.result.errors.length > 0 && ` Provider errors: ${refreshingTarget.result.errors.join("; ")}`}
          </p>}
          {refreshingTarget?.status === "failed" && <div className="box" role="alert">Could not fetch target signals: {refreshingTarget.error}</div>}
          <button className="btnx" disabled={generatingCurrentSwot || selectedTarget.live_signal_count === 0}
            onClick={generateCurrentSwot}>
            {generatingCurrentSwot ? "Generating from live evidence…" : "Generate current SWOT from live sources"}
          </button>
          {selectedTarget.live_signal_count === 0 && <p className="sub">No live signals are collected for this target yet. Fetch live signals above before generating a current SWOT.</p>}
          {currentSwot && <SwotList title={`Live-evidence current SWOT · ${selectedTarget.name}`} swot={currentSwot} />}
          <label className="panel" style={{ display: "block" }}>
            <b>Acquisition thesis for this target</b>
            <textarea className="th" rows={2} value={targetText} onChange={(event) => setTargetText(event.target.value)}
              placeholder={`Why should ${desk} consider acquiring ${selectedTarget.name}?`} />
          </label>
          <p className="sub">After generation, the combined future SWOT appears below under “Post-acquisition SWOT”.</p>
          <button className="btnx pri" disabled={drafting || !baselineReady || !currentSwot || !targetId || !targetText.trim()} onClick={draftSwot}>
            {drafting ? "Drafting SWOT…" : "Generate post-acquisition SWOT draft"}
          </button>
          {draft && <>
            <div className="box"><b>AI-generated scenario · reviewer confirmation required.</b> Forward-looking items labeled “Assumption” are possibilities, not verified facts. Review the items and rationales before saving.</div>
            <div className="cols even">
              <SwotList title={`Baseline SWOT · ${desk}`} swot={draft.baseline_swot} />
              <SwotList title={`Current SWOT · ${draft.target_name}`} swot={draft.current_swot} />
            </div>
            <SwotList title={`Post-acquisition SWOT · what ${desk} + ${draft.target_name} may look like after the deal`} swot={draft.post_acquisition_swot} rationale />
            <p className="sub">Drafted by {draft.drafted_by}. Saving confirms a reviewer has reviewed this scenario.</p>
            <button className="btnx pri" disabled={savingAssessment} onClick={saveAssessment}>
              {savingAssessment ? "Saving…" : "I reviewed this SWOT — save thesis"}
            </button>
          </>}
          <div className="panel" style={{ marginTop: 14 }}>
            <h5>Saved target theses · {assessments.length}</h5>
            {assessments.length ? assessments.map((assessment) => <details key={assessment.id} style={{ marginBottom: 8 }}>
              <summary><b>{assessment.target_name}</b> · {assessment.status} · {assessment.created_at.slice(0, 10)}</summary>
              <p>{assessment.text}</p>
              <div className="cols even">
                <SwotList title={`Baseline · ${assessment.company}`} swot={assessment.baseline_swot} />
                <SwotList title={`Current · ${assessment.target_name}`} swot={assessment.current_swot} />
              </div>
              <SwotList title={`Post-acquisition · ${assessment.company} + ${assessment.target_name}`} swot={assessment.post_acquisition_swot} rationale />
            </details>) : <p className="sub">No target-specific thesis saved yet.</p>}
          </div>
        </> : <div className="box">No approved live targets are currently routed to {desk}. Add or approve a real company in Admin → Watchlist, ensure its sectors match this RPG company, and confirm the compliance gate is open. Then return here to fetch signals for that target.</div>}
      </div>
      <details className="panel">
        <summary><b>Target search criteria</b> · screen companies against a general acquisition thesis</summary>
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
      </details>
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
        <span className="crumb"><b>Radar settings</b> / Watch rules</span><h4>Alert me when…</h4>
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

/* ---------------- Demo universe and activity ---------------- */
export function Watched() {
  const app = useApp();
  const [u, setU] = useState<any[] | null>(null);
  const [act, setAct] = useState<any[]>([]);
  useEffect(() => { api.universe().then(setU); if (app.groupView) api.activity().then(setAct).catch(() => setAct([])); }, [app.version]);
  if (!u) return <p className="sub">Loading…</p>;
  return (
    <>
      <div className="top"><div>
        <span className="crumb"><b>Radar settings</b> / Demo universe</span><h4>Prototype sector universe</h4>
        <p className="sub">This read-only demo list is separate from the real-company watchlist. Compliance admins manage company proposals and approvals in Admin → Watchlist.</p>
      </div></div>
      <div className="cols even">
        <div className="panel">
          <h5>Demo universe · {u.length} companies</h5>
          <table className="tbl"><thead><tr><th>Company</th><th>RPG company</th><th>Sector</th><th>How added</th></tr></thead>
            <tbody>{u.map((x, i) => <tr key={i}><td>{x.company}</td><td>{x.desk}</td><td>{x.sector}</td><td className="mono">{x.added}</td></tr>)}</tbody></table>
        </div>
        {app.groupView && <div className="panel">
          <h5>Activity · {act.length} changes</h5>
          <table className="tbl"><thead><tr><th>Time</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
            <tbody>{act.map((a, i) => <tr key={i}><td className="mono">{a.time}</td><td>{a.who}</td><td className="mono">{a.action}</td><td>{a.detail}</td></tr>)}</tbody></table>
          <p className="sub" style={{ fontSize: 12, marginTop: 8 }}>Escalations, decisions, plans, theses, rules and universe changes appear here. Every view and change is also in the immutable audit log (Admin → Audit Log).</p>
        </div>}
      </div>
      <LiveSources />
    </>
  );
}
