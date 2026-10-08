// M&A signal cards and the detailed acquisition thesis, shared by M&A Signals and Shortlisted signals.
import { useEffect, useState, type ReactNode } from "react";
import { api, type CompanyFinancials, type SignalCard as Card, type SignalJob, type SignalStatus, type SwotView, type ThesisPage } from "../api";
import { useApp } from "../state";
import { ConnectionsGraph, QuarterlyResults } from "./charts";
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
      {c.found_via === "sector news" && <span className="pill2 from-news" title="Found by the Sector Scout in this week's industry news">Found in sector news</span>}
      <div className="kv small">
        <div><small>For</small><b>{c.companies.join(", ")}</b></div>
        <div><small>Listing</small><b>{c.listing ? `NSE: ${c.listing}` : "Not matched"}</b></div>
        <div><small>Size</small><b className={c.size.ok === null ? "unverified" : ""}>{c.size.label.replace("the RPG company's", c.company)}</b></div>
        <div><small>Signals · latest</small><b>{c.signal_count} · {c.date}</b></div>
        <div><small>Acquisition</small><b>{c.thesis ? TYPE_LABEL[c.thesis.acquisition_type] : "Thesis being written"}</b></div>
        {c.finance && <div><small>Balance sheet</small><b className={c.finance.listed && !c.finance.pending ? `zone-${c.finance.zone || "none"}` : "unverified"}
          title={c.finance.stress?.length ? `Under stress: ${c.finance.stress.join("; ")}` : undefined}>{c.finance.label}</b></div>}
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

const THESIS_TABS = [["overview", "Overview"], ["swot", "SWOT"], ["fit", "Fit and ripple"], ["financials", "Financials"],
                     ["connections", "Connections"], ["evidence", "Signals and evidence"]] as const;
type ThesisTab = (typeof THESIS_TABS)[number][0];

/** The detailed acquisition thesis for one signal, in tabs; written by the Acquisition Thesis agent in the background. */
export function ThesisView({ caseId, onBack }: { caseId: string; onBack: () => void }) {
  const app = useApp();
  const [d, setD] = useState<ThesisPage | null>(null);
  const [co, setCo] = useState<string | undefined>(app.scope === "All" ? undefined : app.scope);
  const [swot, setSwot] = useState<SwotView | null>(null);
  const [job, setJob] = useState<SignalJob | null>(null);
  const [tab, setTab] = useState<ThesisTab>(() => {
    try { return (localStorage.getItem("thesis-tab") as ThesisTab) || "overview"; } catch { return "overview"; }
  });
  const [hl, setHl] = useState<string | null>(null);
  const pick = (k: ThesisTab) => { setTab(k); try { localStorage.setItem("thesis-tab", k); } catch { /* private window */ } };

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
  // a citation opens Signals and evidence at that source
  const cite = (ids: string[]) => ids.map((e) => <sup key={e}><a href={`#ev-${e}`} onClick={(ev) => {
    ev.preventDefault(); setHl(e); pick("evidence");
    requestAnimationFrame(() => document.getElementById(`ev-${e}`)?.scrollIntoView({ block: "center", behavior: "smooth" }));
  }}>[{e.slice(1)}]</a></sup>);

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
      <div className="kfilter thesis-tabs" role="tablist" aria-label="Acquisition thesis sections">
        {THESIS_TABS.map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-pressed={k === tab} onClick={() => pick(k)}>
            {l}{k === "connections" && t?.draft.connections ? ` · ${t.draft.connections.length}` : k === "evidence" && t ? ` · ${t.evidence.length}` : ""}
          </button>
        ))}
      </div>

      {!t && tab !== "financials" && tab !== "evidence" ? (
        <div className="callout" style={{ marginTop: 12 }}>
          <b>{job?.status === "failed" || (d.failed && !running) ? "The acquisition thesis could not be written" : "The acquisition thesis is being written"}</b>
          <p>{job?.status === "failed" ? `It could not be written: ${job.error}`
            : d.failed && !running ? `The last attempt (${d.failed.at}) failed: ${d.failed.error} The radar tries again every 30 minutes; press Write thesis to try now.`
            : `The Acquisition Thesis agent writes every new signal's thesis in the background: it researches ${c.who} (results, shareholding, ownership, web and news), then compares it with ${d.company}'s SWOT. This page updates when it is ready${running ? "" : ", or press Write thesis to write it now"}. Financials and Signals and evidence are already available.`}</p>
        </div>
      ) : null}

      {t && tab === "overview" && <>
        <div className="reco" style={{ marginTop: 12 }}><small>The thesis</small><p style={{ margin: 0 }}>{t.draft.headline}</p></div>
        {t.draft.background && <div className="panel">
          <h5>Company background</h5>
          <p style={{ marginTop: 0 }}>{t.draft.background.summary}</p>
          <ul className="cmp">{t.draft.background.points.map((x, i) => <li key={i}>{x.text} {cite(x.evidence)}</li>)}</ul>
        </div>}
        <div className="panel"><h5>Partial or full acquisition · {TYPE_LABEL[t.draft.acquisition_type]}</h5><p style={{ margin: 0 }}>{t.draft.acquisition_reason}</p></div>
        <div className="panel"><h5>Open questions for diligence</h5><ol style={{ margin: 0, paddingLeft: 18 }}>{t.draft.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ol></div>
      </>}

      {t && tab === "swot" && <>
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
      </>}

      {t && tab === "fit" && <>
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
      </>}

      {tab === "financials" && (d.financials
        ? <FinancialHealth target={c.who} acquirer={d.company} f={d.financials} />
        : <p className="sub" style={{ marginTop: 12 }}>No financial figures on record.</p>)}

      {t && tab === "connections" && <div className="panel">
        <h5>Connections · {t.draft.connections?.length || 0}</h5>
        {t.draft.connections?.length ? (
          <>
            <ConnectionsGraph center={c.who} items={t.draft.connections} />
            <table className="tbl" style={{ marginTop: 8 }}><tbody>{t.draft.connections.map((x, i) => (
              <tr key={i}><td><b>{x.name}</b>{x.link && <> <span className="pill2 fired">{x.link}</span></>}</td><td><span className="pill2">{x.relation}</span></td><td>{x.detail} {cite(x.evidence)}</td></tr>
            ))}</tbody></table>
          </>
        ) : <p className="sub">The public evidence names no shareholders, parent, subsidiaries or partners for {c.who}.</p>}
        <p className="sub" style={{ fontSize: 12 }}>Only links the public sources state; full shareholder registers (MCA filings) are not among the radar's sources.</p>
      </div>}

      {tab === "evidence" && <>
        <div className="panel">
          <h5>Public signals and score</h5>
          {c.recommended && <p className="sub" style={{ marginTop: 0 }}>Recommended move in {c.recommended.co}'s SWOT: <b>{c.recommended.title}</b></p>}
          <QuickLookBody c={c} />
        </div>
        {t && <div className="panel">
          <h5>Evidence · {t.evidence.length}</h5>
          <p className="sub" style={{ marginTop: 0 }}>Every numbered source the thesis cites; a [number] on the other tabs brings you here.</p>
          <ol className="evlist">{t.evidence.map((x) => (
            <li key={x.id} id={`ev-${x.id}`} className={x.id === hl ? "hl" : ""}><span className="sub">{x.source}{x.date ? ` · ${x.date}` : ""}</span> {x.url ? <a href={x.url} target="_blank" rel="noreferrer">{x.text}</a> : x.text}</li>
          ))}</ol>
          {t.research_errors.length > 0 && <p className="sub" style={{ fontSize: 12 }}>Some sources failed: {t.research_errors.slice(0, 3).join("; ")}</p>}
        </div>}
      </>}

      <p className="sub" style={{ fontSize: 12 }}>Built from public information only. Contains no price, valuation or synergy figure and no non-public information. Not a recommendation to bid.</p>
    </>
  );
}


/** Thesis → Financial health: the target's published figures beside the RPG company's (rule-based, Fincrux). */
function FinancialHealth({ target, acquirer, f }: { target: string; acquirer: string; f: { target: CompanyFinancials; acquirer: CompanyFinancials } }) {
  const cr = (v?: number | null) => v === null || v === undefined ? "—" : `₹${Math.round(v).toLocaleString("en-IN")} cr`;
  const pc = (v?: number | null, signed = true) => v === null || v === undefined ? "—" : `${signed && v > 0 ? "+" : ""}${v.toFixed(1)}%`;
  const x = (v?: number | null) => v === null || v === undefined ? "—" : `${v}x`;
  const z = (c: CompanyFinancials) => c.health?.altman_z ? <span className={`pill2 ${{ safe: "fit-strong", grey: "fit-moderate", distress: "fit-weak" }[c.health.altman_z.zone]}`}>{c.health.altman_z.z} · {c.health.altman_z.zone}</span> : "—";
  const rows: [string, (c: CompanyFinancials) => ReactNode][] = [
    ["Market cap", (c) => cr(c.health?.market_cap)],
    ["Sales, last 4 quarters", (c) => cr(c.ttm_sales)],
    ["Sales growth, latest quarter YoY", (c) => pc(c.sales_yoy)],
    ["Net profit growth, latest quarter YoY", (c) => pc(c.profit_yoy)],
    ["Operating margin, latest quarter", (c) => pc(c.opm, false)],
    ["Sales growth a year, last 3 years", (c) => pc(c.health?.sales_cagr_3y)],
    ["Debt / equity", (c) => x(c.health?.debt_to_equity)],
    ["Interest cover", (c) => x(c.health?.interest_cover)],
    ["Free cash flow, last year", (c) => cr(c.health?.fcf)],
    ["ROCE", (c) => pc(c.health?.roce, false)],
    ["Altman Z-score", z],
    ["Promoter holding", (c) => pc(c.promoters, false)],
  ];
  const note = (c: CompanyFinancials, name: string) => !c.listed ? `${name} is not listed, so it publishes no quarterly results or balance sheet.`
    : c.pending ? `${name}'s figures have not been fetched yet (Fincrux allows 5 calls a day): Self reflection → The financial market → Fetch missing figures.` : null;
  const notes = [note(f.target, target), note(f.acquirer, acquirer)].filter(Boolean);
  const e = f.target.expected;
  const has = (c: CompanyFinancials) => c.listed && !c.pending;
  return (
    <div className="panel">
      <h5>Financial health · {target} beside {acquirer}</h5>
      {[f.target, f.acquirer].some((c) => (c.sales_series?.length || 0) > 1) && (
        <div className="qcharts" style={{ marginBottom: 10 }}>
          {([[f.target, target, false], [f.acquirer, acquirer, true]] as const).filter(([c]) => (c.sales_series?.length || 0) > 1).map(([c, name, own]) => (
            <QuarterlyResults key={name} name={name} own={own} quarters={c.quarters || []} sales={c.sales_series || []} profit={c.profit_series || []} opm={c.opm_series || []} />
          ))}
        </div>
      )}
      {(has(f.target) || has(f.acquirer)) && (
        <table className="tbl mkt">
          <thead><tr><th>Measure</th><th>{target}</th><th>{acquirer}</th></tr></thead>
          <tbody>{rows.map(([label, get]) => <tr key={label}><td>{label}</td><td className="num">{has(f.target) ? get(f.target) : "—"}</td><td className="num">{has(f.acquirer) ? get(f.acquirer) : "—"}</td></tr>)}</tbody>
        </table>
      )}
      {e && (
        <p style={{ marginBottom: 0 }}><b>Level to expect after a deal:</b> an average quarter of {cr(e.sales)} sales, {cr(e.profit)} net profit and a {pc(e.opm, false)} operating margin ({e.quarters} quarters, {e.from} to {e.to}).
          <span className="sub"> For smaller deals, a target's average over the 8 quarters before the deal predicted its figures after it (Dogan and Ugurlu, 2024); a guide, not a forecast.</span></p>
      )}
      {notes.map((n) => <p key={n} className="sub" style={{ margin: "6px 0 0" }}>{n}</p>)}
      <p className="sub" style={{ fontSize: 12, marginBottom: 0 }}>From published accounts (Fincrux). The Altman Z-score's working capital is estimated; how each figure is worked out is on The financial market.</p>
    </div>
  );
}
