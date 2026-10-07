// M&A signal cards and the detailed acquisition thesis, shared by M&A Signals and Shortlisted signals.
import { useEffect, useState } from "react";
import { api, type CaseDetail, type SignalCard as Card, type SignalJob, type SignalStatus, type SwotView, type ThesisDoc } from "../api";
import { useApp } from "../state";
import { ConnectionsGraph } from "./charts";
import { QuickLookBody, ScorePill } from "./ui";

const TYPE_LABEL: Record<string, string> = { full: "Full acquisition", partial: "Partial stake", unclear: "Unclear" };

/** One M&A signal: definite facts only, with View and a status action. */
export function SignalCardView({ c, onView }: { c: Card; onView: () => void }) {
  const app = useApp();
  const set = (status: SignalStatus, msg: string) => api.setStatus(c.id, status).then(() => { app.toast(msg); app.bump(); }).catch((e) => app.toast(e.message));
  return (
    <div className="card2">
      <div className="card2-h">
        <b className="rt" style={{ margin: 0 }}>{c.who}</b>
        <ScorePill score={c.score} detail={c.score_detail} />
      </div>
      <div className="kv small">
        <div><small>For</small><b>{c.companies.join(", ")}</b></div>
        <div><small>Listing</small><b>{c.listing ? `NSE: ${c.listing}` : "Not matched"}</b></div>
        <div><small>Size</small><b className={c.size.ok === null ? "unverified" : ""}>{c.size.label.replace("the RPG company's", c.company)}</b></div>
        <div><small>Signals · latest</small><b>{c.signal_count} · {c.date}</b></div>
        <div><small>Acquisition</small><b>{c.thesis ? TYPE_LABEL[c.thesis.acquisition_type] : "Thesis being written"}</b></div>
      </div>
      <div className="uses">{c.chips.map((x) => {
        const s = c.chip_links?.[x];
        const tip = s ? `${s.date} · ${s.text} (${s.source})` : x;
        return s?.url
          ? <a key={x} className="pill2 chiplink" href={s.url} target="_blank" rel="noreferrer" title={tip}>{x} ↗</a>
          : <span key={x} className="pill2" title={tip}>{x}</span>;
      })}</div>
      {(() => {
        const s = c.chip_links?.[c.chips[0]];
        return s ? <p className="sub latest">Latest: {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.text.length > 110 ? s.text.slice(0, 108) + "…" : s.text}</a> : s.text} <span className="mini">· {s.source} · {s.date}</span></p> : null;
      })()}
      <div className="btnrow" style={{ marginTop: 4 }}>
        <button className="btnx pri" onClick={onView}>View</button>
        {c.status === "open" && <button className="btnx" onClick={() => set("dismissed", `${c.who} moved to the archive.`)}>Dismiss</button>}
        {c.status === "dismissed" && <button className="btnx" onClick={() => set("open", `${c.who} is back in M&A Signals.`)}>Restore</button>}
        {c.status === "shortlisted" && <button className="btnx" onClick={() => set("open", `${c.who} removed from the shortlist.`)}>Remove from shortlist</button>}
      </div>
    </div>
  );
}

/** The detailed acquisition thesis for one signal, written by the Acquisition Thesis agent on first view. */
export function ThesisView({ caseId, onBack }: { caseId: string; onBack: () => void }) {
  const app = useApp();
  const [d, setD] = useState<{ company: string; signal: CaseDetail; thesis: ThesisDoc | null; failed: { error: string; at: string } | null } | null>(null);
  const [co, setCo] = useState<string | undefined>(app.scope === "All" ? undefined : app.scope);
  const [swot, setSwot] = useState<SwotView | null>(null);
  const [job, setJob] = useState<SignalJob | null>(null);

  useEffect(() => {
    api.thesis(caseId, co).then((r) => { setD(r); if (!co) setCo(r.company); })
      .catch(() => api.thesis(caseId).then((r) => { setD(r); setCo(r.company); }).catch((e) => app.toast(e.message)));
  }, [caseId, co, app.version]);
  useEffect(() => { if (d?.company) api.home(d.company).then((h) => setSwot(h.swot)).catch(() => setSwot(null)); }, [d?.company]);
  const write = () => api.writeThesis(caseId, d?.company).then(setJob).catch((e) => app.toast(e.message));
  useEffect(() => {  // the radar writes every signal's thesis in the background: check back until it is there
    if (!d || d.thesis || job) return;
    const t = setTimeout(() => api.thesis(caseId, d.company).then(setD).catch(() => undefined), 15000);
    return () => clearTimeout(t);
  }, [d, job]);
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setTimeout(() => api.thesisJob(job.id).then((j) => {
      setJob(j);
      if (j.status === "completed") { app.toast("The acquisition thesis is ready."); app.bump(); }
      if (j.status === "failed") app.toast(j.error || "The Acquisition Thesis agent failed");
    }).catch((e) => app.toast(e.message)), 2500);
    return () => clearTimeout(t);
  }, [job]);

  if (!d) return <p className="sub">Loading…</p>;
  const c = d.signal, t = d.thesis, running = job?.status === "running";
  const set = (status: SignalStatus, msg: string) => api.setStatus(c.id, status).then(() => { app.toast(msg); app.bump(); }).catch((e) => app.toast(e.message));
  const cite = (ids: string[]) => ids.map((e) => <sup key={e}><a href={`#ev-${e}`}>[{e.slice(1)}]</a></sup>);

  return (
    <>
      <div><a href="#" className="crumb" onClick={(e) => { e.preventDefault(); onBack(); }}>← Back to signals</a></div>
      <div className="top"><div>
        <span className="crumb"><b>Acquisition thesis</b> · {c.who} for {d.company}</span>
        <h4>{c.who}</h4>
        <p className="sub">{t ? `Written by the Acquisition Thesis agent (${t.model}) on ${t.at}` : "No thesis written yet"} · a draft for review, not a valuation or a recommendation to bid.</p>
      </div></div>
      <div className="btnrow" style={{ alignItems: "center" }}>
        {c.status === "shortlisted"
          ? <button className="btnx" onClick={() => set("open", "Removed from the shortlist.")}>Remove from shortlist</button>
          : <button className="btnx pri" onClick={() => set("shortlisted", `${c.who} shortlisted.`)}>Shortlist</button>}
        {c.status !== "dismissed" && <button className="btnx" onClick={() => set("dismissed", `${c.who} moved to the archive.`)}>Dismiss</button>}
        <button className="btnx" disabled={running} onClick={write}>{running ? "Writing the thesis…" : t ? "Rewrite thesis" : "Write thesis"}</button>
        {c.companies.length > 1 && (
          <label className="sub" style={{ fontSize: 12.5 }}>Thesis for <select value={d.company} onChange={(e) => setCo(e.target.value)}>{c.companies.map((x) => <option key={x}>{x}</option>)}</select></label>
        )}
        {c.status !== "open" && <span className="pill2">{c.status_label}{c.status_at ? ` · ${c.status_at}` : ""}</span>}
      </div>
      <div className="kv">
        <div><small>Company</small><b>{c.who}</b></div>
        <div><small>Listing</small><b>{c.listing ? `NSE: ${c.listing}` : "Not matched to a listing"}</b></div>
        <div><small>Size</small><b>{c.size.label.replace("the RPG company's", d.company)}</b></div>
        <div><small>Opportunity score</small><b>{c.score !== null ? `${Math.round(c.score)} of 100` : "Not scored"}</b></div>
        <div><small>Public signals · 120 days</small><b>{c.signal_count} · latest {c.date}</b></div>
        <div><small>Likely acquisition</small><b>{t ? TYPE_LABEL[t.draft.acquisition_type] : "—"}</b></div>
      </div>

      {!t ? (
        <div className="callout" style={{ marginTop: 12 }}>
          <b>{job?.status === "failed" || (d.failed && !running) ? "The acquisition thesis could not be written" : "The acquisition thesis is being written"}</b>
          <p>{job?.status === "failed" ? `It could not be written: ${job.error}`
            : d.failed && !running ? `The last attempt (${d.failed.at}) failed: ${d.failed.error} The radar tries again every 30 minutes; press Write thesis to try now.`
            : `The Acquisition Thesis agent writes every new signal's thesis in the background: it researches ${c.who} (results, shareholding, ownership, web and news), then compares it with ${d.company}'s SWOT. This page updates when it is ready${running ? "" : ", or press Write thesis to write it now"}.`}</p>
        </div>
      ) : (
        <>
          <div className="reco" style={{ marginTop: 12 }}><small>The thesis</small><p style={{ margin: 0 }}>{t.draft.headline}</p></div>
          {t.draft.background && <div className="panel">
            <h5>Company background</h5>
            <p style={{ marginTop: 0 }}>{t.draft.background.summary}</p>
            <ul className="cmp">{t.draft.background.points.map((x, i) => <li key={i}>{x.text} {cite(x.evidence)}</li>)}</ul>
          </div>}

          {t.draft.connections && <div className="panel">
            <h5>Connections · {t.draft.connections.length}</h5>
            {t.draft.connections.length ? (
              <>
                <ConnectionsGraph center={c.who} items={t.draft.connections} />
                <table className="tbl" style={{ marginTop: 8 }}><tbody>{t.draft.connections.map((x, i) => (
                  <tr key={i}><td><b>{x.name}</b>{x.link && <> <span className="pill2 fired">{x.link}</span></>}</td><td><span className="pill2">{x.relation}</span></td><td>{x.detail} {cite(x.evidence)}</td></tr>
                ))}</tbody></table>
              </>
            ) : <p className="sub">The public evidence names no shareholders, parent, subsidiaries or partners for {c.who}.</p>}
            <p className="sub" style={{ fontSize: 12 }}>Only links the public sources state; full shareholder registers (MCA filings) are not among the radar's sources.</p>
          </div>}

          <div className="panel"><h5>Partial or full acquisition · {TYPE_LABEL[t.draft.acquisition_type]}</h5><p style={{ margin: 0 }}>{t.draft.acquisition_reason}</p></div>

          <div className="panel">
            <h5>SWOT comparison</h5>
            <div className="cols even">
              <div>
                <b>{c.who}</b>
                {(["strengths", "weaknesses", "opportunities", "threats"] as const).map((k) => (
                  <div key={k} className={`tswot ${{ strengths: "qS", weaknesses: "qW", opportunities: "qO", threats: "qT" }[k]}`}><small>{k}</small><ul>{t.draft.target_swot[k].map((x, i) => <li key={i}>{x.text} {cite(x.evidence)}</li>)}</ul></div>
                ))}
              </div>
              <div>
                <b>{d.company}</b>
                {swot ? (["S", "W", "O", "T"] as const).map((k) => (
                  <div key={k} className={`tswot q${k}`}><small>{{ S: "strengths", W: "weaknesses", O: "opportunities", T: "threats" }[k]}</small>
                    <ul>{swot[k].map((x) => <li key={x.id}><span className="mono">{x.id}</span> {x.text}</li>)}</ul></div>
                )) : <p className="sub">No SWOT for {d.company} yet (Self analysis → Build SWOT).</p>}
              </div>
            </div>
            <h5 style={{ marginTop: 12 }}>How they fit together</h5>
            <ul className="cmp">{t.draft.comparison.map((x, i) => (
              <li key={i}><span className={`pill2 eff-${x.effect}`}>{x.effect}</span>{x.swot_ref && <span className="mono"> {x.swot_ref}</span>} {x.point} {cite(x.evidence)}</li>
            ))}</ul>
          </div>

          <div className="panel">
            <h5>Post-acquisition SWOT · {d.company} with {c.who}</h5>
            {t.draft.post_swot ? <>
              <p className="sub" style={{ marginTop: 0 }}>{d.company}'s SWOT as it would look after the deal: what the target adds (new), what it changes in today's SWOT (strengthened, weakened) and what stays (carried over).</p>
              <div className="pswot">
                {(["strengths", "weaknesses", "opportunities", "threats"] as const).map((k) => (
                  <div key={k} className={`tswot ${{ strengths: "qS", weaknesses: "qW", opportunities: "qO", threats: "qT" }[k]}`}><small>{k}</small><ul className="cmp">{t.draft.post_swot![k].map((x, i) => (
                    <li key={i}><span className={`pill2 chg-${x.change.replace(" ", "-")}`}>{x.change}</span>{x.swot_ref && <span className="mono"> {x.swot_ref}</span>} {x.text} {cite(x.evidence)}</li>
                  ))}</ul></div>
                ))}
              </div>
            </> : <p className="sub" style={{ margin: 0 }}>This thesis was written before the post-acquisition SWOT was added; press Rewrite thesis to add it.</p>}
          </div>

          <div className="panel">
            <h5>Fitment analysis</h5>
            <table className="tbl"><thead><tr><th>Fit</th><th>Rating</th><th>Why</th></tr></thead>
              <tbody>{t.draft.fitment.map((x) => (
                <tr key={x.dimension}><td><b>{x.dimension}</b></td><td><span className={`pill2 fit-${x.rating}`}>{x.rating}</span></td><td>{x.reasoning} {cite(x.evidence)}</td></tr>
              ))}</tbody></table>
          </div>

          <div className="panel">
            <h5>Ripple effect on the other RPG companies</h5>
            <table className="tbl"><tbody>{t.draft.ripple.map((x) => (
              <tr key={x.company}><td><b>{x.company}</b></td><td><span className={`pill2 rip-${x.effect}`}>{x.effect}</span></td><td>{x.reasoning}</td></tr>
            ))}</tbody></table>
          </div>

          <div className="panel"><h5>Open questions for diligence</h5><ol style={{ margin: 0, paddingLeft: 18 }}>{t.draft.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ol></div>
        </>
      )}

      <div className="panel">
        <h5>Public signals and score</h5>
        {c.recommended && <p className="sub" style={{ marginTop: 0 }}>Recommended move in {c.recommended.co}'s SWOT: <b>{c.recommended.title}</b></p>}
        <QuickLookBody c={c} />
      </div>

      {t && (
        <details className="panel">
          <summary><b>Evidence · {t.evidence.length}</b> <span className="sub">every numbered source the thesis cites</span></summary>
          <ol className="evlist">{t.evidence.map((x) => (
            <li key={x.id} id={`ev-${x.id}`}><span className="sub">{x.source}{x.date ? ` · ${x.date}` : ""}</span> {x.url ? <a href={x.url} target="_blank" rel="noreferrer">{x.text}</a> : x.text}</li>
          ))}</ol>
          {t.research_errors.length > 0 && <p className="sub" style={{ fontSize: 12 }}>Some sources failed: {t.research_errors.slice(0, 3).join("; ")}</p>}
        </details>
      )}
      <p className="sub" style={{ fontSize: 12 }}>Built from public information only. Contains no price, valuation or synergy figure and no non-public information. Not a recommendation to bid.</p>
    </>
  );
}
