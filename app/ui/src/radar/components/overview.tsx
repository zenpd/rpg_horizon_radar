// Competitor Analysis → Overview: one watched company's recent moves, financial snapshot, SWOT,
// how it competes with the RPG company, the competitive intensity and what to watch.
import { useEffect, useState } from "react";
import { api, type Overview, type SignalJob } from "../api";
import { useApp } from "../state";
import { ScorePill, SignalList } from "./ui";

const SIDE: Record<string, string> = { ahead: "rip-risk", behind: "rip-opportunity", "head-to-head": "rip-neutral" };
const THREAT: Record<string, string> = { high: "fit-weak", medium: "fit-moderate", low: "fit-strong" };
const QUAD = { strengths: "qS", weaknesses: "qW", opportunities: "qO", threats: "qT" } as const;

export function CompetitorOverview({ id, company, onBack }: { id: number; company: string; onBack: () => void }) {
  const app = useApp();
  const [d, setD] = useState<Overview | null>(null);
  const [job, setJob] = useState<SignalJob | null>(null);
  const load = () => api.overview(id, company).then(setD).catch((e) => app.toast(e.message));
  useEffect(() => { load(); }, [id, company, app.version]);

  const write = () => api.writeOverview(id, company).then(setJob).catch((e) => app.toast(e.message));
  // A company with no overview yet (one with no recent moves is not written in the background): write it now.
  useEffect(() => { if (d && !d.profile && !d.failed && !job) write(); }, [d]);
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setTimeout(() => api.overviewJob(job.id).then((j) => {
      setJob(j);
      if (j.status === "completed") load();
      if (j.status === "failed") app.toast(j.error || "The Competitor Profile agent failed");
    }).catch((e) => app.toast(e.message)), 2500);
    return () => clearTimeout(t);
  }, [job]);

  if (!d) return <p className="sub">Loading…</p>;
  const r = d.rival, p = d.profile, running = job?.status === "running";
  const cite = (ids: string[]) => ids.map((e) => <sup key={e}><a href={`#pev-${e}`}>[{e.slice(1)}]</a></sup>);
  const moves = d.moves.filter((m) => m.signals.length);

  return (
    <>
      <div><a href="#" className="crumb" onClick={(e) => { e.preventDefault(); onBack(); }}>← Back to competitors</a></div>
      <div className="top"><div>
        <span className="crumb"><b>Competitor overview</b> · {r.name} for {company}</span>
        <h4>{r.name}</h4>
        <p className="sub">{p ? `Analysis by the Competitor Profile agent (${p.model}) on ${p.at}` : "Analysis not written yet"} · from public information only.</p>
      </div></div>
      <div className="btnrow" style={{ alignItems: "center" }}>
        <button className="btnx" disabled={running} onClick={write}>{running ? "Writing the overview…" : p ? "Rewrite overview" : "Write overview"}</button>
      </div>
      <div className="kv">
        <div><small>Listing</small><b>{r.nse_symbol ? `NSE: ${r.nse_symbol}` : "Not matched to a listing"}</b></div>
        <div><small>Size</small><b>{r.size.label.replace("the RPG company's", company)}</b></div>
        <div><small>Recent moves · 120 days</small><b>{r.signals}{r.latest_date ? ` · latest ${r.latest_date}` : ""}</b></div>
        <div><small>Competitive intensity</small><b><ScorePill score={r.score} detail={r.score_detail} label="Score" /></b></div>
      </div>

      {p ? (
        <div className="reco" style={{ marginTop: 12 }}><small>In short</small><p style={{ margin: 0 }}>{p.draft.summary}</p></div>
      ) : (
        <div className="callout" style={{ marginTop: 12 }}>
          <b>{d.failed && !running ? "The overview could not be written" : "The overview is being written"}</b>
          <p>{d.failed && !running ? `The last attempt (${d.failed.at}) failed: ${d.failed.error} Press Write overview to try again.`
            : `The Competitor Profile agent researches ${r.name} (results, shareholding, web and news) and compares it with ${company}'s SWOT. This page updates when it is ready.`}</p>
        </div>
      )}
      {r.why && <div className="callout" style={{ marginTop: 12 }}><b>Why it is watched</b><p>{r.why}</p>
        {r.sources.length > 0 && <p className="sub" style={{ fontSize: 12 }}>{r.sources.map((x, i) => <a key={x.url} href={x.url} target="_blank" rel="noreferrer" title={x.title}>[{i + 1}] </a>)}</p>}</div>}

      <div className="panel">
        <h5>Recent moves · last 120 days</h5>
        {moves.length ? moves.map((m) => (
          <div key={m.group} style={{ marginTop: 8 }}><b style={{ fontSize: 13.5 }}>{m.group} · {m.signals.length}</b><SignalList signals={m.signals} /></div>
        )) : <p className="sub" style={{ margin: 0 }}>No recent moves in the last 120 days: no patents, hiring or leadership changes, deals, filings or news the radar picked up.</p>}
      </div>

      <div className="panel">
        <h5>Financial snapshot</h5>
        {d.financials.length ? <ul className="cmp">{d.financials.map((f, i) => (
          <li key={i}>{f.url ? <a href={f.url} target="_blank" rel="noreferrer">{f.text}</a> : f.text} <span className="sub">· {f.source}{f.date ? ` · ${f.date}` : ""}</span></li>
        ))}</ul> : <p className="sub" style={{ margin: 0 }}>No quarterly results or shareholding on record{d.researched_at ? "" : " yet: they are collected when the overview is written"}. Fincrux allows five lookups a day, and private companies publish none.</p>}
      </div>

      {p && <>
        <div className="panel">
          <h5>SWOT · {r.name}</h5>
          <div className="pswot">
            {(["strengths", "weaknesses", "opportunities", "threats"] as const).map((k) => (
              <div key={k} className={`tswot ${QUAD[k]}`}><small>{k}</small><ul>{p.draft.swot[k].map((x, i) => <li key={i}>{x.text} {cite(x.evidence)}</li>)}</ul></div>
            ))}
          </div>
        </div>

        <div className="panel">
          <h5>How it competes with {company}</h5>
          <ul className="cmp">{p.draft.versus.map((x, i) => (
            <li key={i}><span className={`pill2 ${SIDE[x.side]}`}>{x.side === "ahead" ? `ahead of ${company}` : x.side === "behind" ? `behind ${company}` : "head-to-head"}</span>
              {x.swot_ref && <span className="mono"> {x.swot_ref}</span>} {x.point} {cite(x.evidence)}</li>
          ))}</ul>
          <p style={{ marginBottom: 0 }}><b>Overall: <span className={`pill2 ${THREAT[p.draft.threat.level]}`}>{p.draft.threat.level}</span></b> {p.draft.threat.reason}</p>
        </div>

        <div className="panel"><h5>What to watch next</h5><ul className="cmp">{p.draft.watch.map((w, i) => <li key={i}>{w}</li>)}</ul></div>

        <details className="panel">
          <summary><b>Evidence · {p.evidence.length}</b> <span className="sub">every numbered source the analysis cites</span></summary>
          <ol className="evlist">{p.evidence.map((x) => (
            <li key={x.id} id={`pev-${x.id}`}><span className="sub">{x.source}{x.date ? ` · ${x.date}` : ""}</span> {x.url ? <a href={x.url} target="_blank" rel="noreferrer">{x.text}</a> : x.text}</li>
          ))}</ol>
          {p.research_errors.length > 0 && <p className="sub" style={{ fontSize: 12 }}>Some sources failed: {p.research_errors.slice(0, 3).join("; ")}</p>}
        </details>
      </>}
    </>
  );
}
