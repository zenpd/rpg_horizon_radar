// Widgets for the radar's two LLM agents, shared by Self analysis, M&A Signals and the Weekly digest.
import { useEffect, useState } from "react";
import { api, type Finding, type Findings as FindingsData, type SignalJob, type SwotJob, type SwotView } from "../api";
import { useApp } from "../state";

// The daily Opportunity Analyst's findings for one company: what the news means for its SWOT.
export function Findings({ co, onHover }: { co: string; onHover: (ref: string | null) => void }) {
  const app = useApp();
  const [d, setD] = useState<FindingsData | null>(null);
  const [job, setJob] = useState<SignalJob | null>(null);
  useEffect(() => { setD(null); api.opportunities(co).then(setD).catch(() => setD(null)); }, [co, app.version]);
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setTimeout(() => api.opportunityJob(job.id).then((j) => {
      setJob(j);
      if (j.status === "completed") { app.toast(`The Opportunity Analyst found ${j.result?.findings ?? 0} new finding(s) in ${j.result?.news ?? 0} news items`); app.bump(); }
      if (j.status === "failed") app.toast(j.error || "The Opportunity Analyst failed");
    }).catch((e) => app.toast(e.message)), 2000);
    return () => clearTimeout(t);
  }, [job]);
  const decide = (f: Finding, status: Finding["status"]) => api.decideFinding(f.id, status).then(() => {
    app.toast(status === "kept" ? "Kept: it feeds the next weekly SWOT." : status === "dismissed" ? "Dismissed." : "Undone.");
    app.bump();
  }).catch((e) => app.toast(e.message));
  if (!d) return null;
  const running = job?.status === "running";
  return (
    <div className="panel findings">
      <div className="intro" style={{ alignItems: "center" }}>
        <h5 style={{ margin: 0 }}>Today's opportunities and threats · {d.findings.length}</h5>
        <span className="sub" style={{ fontSize: 12 }}>
          {d.last_run ? `Opportunity Analyst read ${d.news_read ?? 0} news items on ${d.last_run}` : "The Opportunity Analyst has not run yet"} · last 7 days
        </span>
        <button className="btnx" disabled={running} onClick={() => api.runOpportunities(co).then(setJob).catch((e) => app.toast(e.message))}>
          {running ? "Reading today's news…" : "Run now"}
        </button>
      </div>
      {d.errors.length > 0 && <p className="sub" style={{ fontSize: 12 }}>Some sources failed: {d.errors.slice(0, 2).join("; ")}</p>}
      {!d.findings.length ? (
        <p className="sub">No findings in the last 7 days. Every day the Opportunity Analyst reads news about {co}, its watched companies and its industry, and reports what changes its SWOT.</p>
      ) : (
        <div className="fgrid">
          {d.findings.map((f) => (
            <div key={f.id} className={`finding ${f.kind}${f.status === "kept" ? " kept" : ""}`} onMouseEnter={() => onHover(f.swot_ref)} onMouseLeave={() => onHover(null)}>
              <div className="fh">
                <span className={`pill2 ${f.kind === "opportunity" ? "opp" : "thr"}`}>{f.kind === "opportunity" ? "Opportunity" : "Threat"}</span>
                <span className="sub" style={{ fontSize: 12 }}>{f.date} · impact {f.impact} · urgency {f.urgency}</span>
              </div>
              <b>{f.title}</b>
              <p>{f.summary}</p>
              <p className="feffect"><b>{f.swot_ref ? `Affects ${f.swot_ref}` : "New for the SWOT"}</b>{f.swot_ref && f.swot_text ? ` (${f.swot_text})` : ""}: {f.effect}</p>
              <p><b>Next step:</b> {f.action}</p>
              <p className="sub" style={{ fontSize: 12 }}>
                {f.sources.map((s, i) => <span key={i}>{i > 0 && " · "}{s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.source}</a> : s.source}{s.date ? ` (${s.date})` : ""}</span>)}
              </p>
              <div className="btnrow">
                {f.status === "new" ? (
                  <>
                    <button className="btnx pri" onClick={() => decide(f, "kept")}>Keep</button>
                    <button className="btnx" onClick={() => decide(f, "dismissed")}>Dismiss</button>
                  </>
                ) : (
                  <><span className="sub" style={{ fontSize: 12 }}>Kept · feeds the next weekly SWOT</span><button className="btnx" onClick={() => decide(f, "new")}>Undo</button></>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Runs the SWOT Analyst agent for one company (researching the company first when needed),
// polls the job, then reloads the screen.
export function SwotBuild({ co, label, research = false }: { co: string; label: string; research?: boolean }) {
  const app = useApp();
  const [job, setJob] = useState<SwotJob | null>(null);

  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setTimeout(() => api.swotJob(job.id).then((j) => {
      setJob(j);
      if (j.status === "completed") { app.toast(`The SWOT Analyst wrote ${co}'s SWOT`); app.bump(); }
      if (j.status === "failed") app.toast(j.error || "The SWOT Analyst failed");
    }).catch((e) => app.toast(e.message)), 1500);
    return () => clearTimeout(t);
  }, [job]);

  const running = job?.status === "running";
  const progress = job?.phase === "research" ? `Researching ${co}: results, shareholding, web and news…`
    : `SWOT Analyst writing… round ${Math.max(job?.round || 0, 1)} of ${job?.max_rounds || 3}`;
  return (
    <span className="btnrow" style={{ alignItems: "center", gap: 10, display: "inline-flex" }}>
      <button className="btnx" disabled={running} onClick={() => api.rebuildSwot(co, research).then(setJob).catch((e) => app.toast(e.message))}>
        {running ? progress : label}
      </button>
      {job?.status === "failed" && <span className="sub" style={{ fontSize: 12 }}>{job.error}</span>}
    </span>
  );
}

export function SwotAgentBar({ co, source }: { co: string; source: SwotView["source"] }) {
  const researched = source.research_at ? ` · company research of ${new Date(source.research_at).toLocaleDateString(undefined, { day: "2-digit", month: "short" })}` : "";
  return (
    <div className="btnrow" style={{ alignItems: "center", gap: 10 }}>
      <span className="sub" style={{ fontSize: 12 }}>Written by the SWOT Analyst agent ({source.model}) · {source.at}{researched}</span>
      <SwotBuild co={co} label="Rebuild SWOT" />
      <SwotBuild co={co} label="Refresh research and rebuild" research />
    </div>
  );
}
