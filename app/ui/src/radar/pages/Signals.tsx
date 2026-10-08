import { useEffect, useRef, useState } from "react";
import { api, type Candidate, type ScoutResult, type SignalJob, type SignalList, type SignalStatus } from "../api";
import { CompetitorOverview } from "../components/overview";
import { SignalCardView, ThesisView } from "../components/signals";
import { useApp } from "../state";

/** Radar → M&A Signals: a card per signal (a watched company with public signals). View opens its
 * acquisition thesis; Dismiss moves it to the archive. */
export default function Signals() {
  const app = useApp();
  return <SignalBoard title="M&A Signals" tabs={[["open", "Signals"], ["dismissed", "Archive"]]} withCandidates
    intro="Each card is a company the RPG company could plausibly acquire — at most half its size, or a target whose size is not verified yet — with public signals worth a look. Competitors too big to buy stay in Competitor Analysis. View opens the acquisition thesis, where you can shortlist it; Dismiss moves it to the archive."
    empty={{ open: `No acquisition targets${app.scope === "All" ? "" : ` for ${app.scope}`} yet. Target discovery runs weekly (or press Find rivals now in Radar settings → Watched companies); a target appears here once it has public signals.`, dismissed: "The archive is empty." }} />;
}

export function SignalBoard({ title, tabs, intro, empty, withCandidates }: {
  title: string; tabs: [SignalStatus, string][]; intro: string; empty: Partial<Record<SignalStatus, string>>; withCandidates?: boolean;
}) {
  const app = useApp();
  const [status, setStatus] = useState<SignalStatus>(tabs[0][0]);
  const [showCands, setShowCands] = useState(false);
  const [cands, setCands] = useState<Candidate[] | null>(null);
  const [scoutJob, setScoutJob] = useState<(SignalJob & { result: ScoutResult | null }) | null>(null);
  useEffect(() => {
    if (!scoutJob || scoutJob.status !== "running") return;
    const t = setTimeout(() => api.scoutJob(scoutJob.id).then((j) => {
      setScoutJob(j);
      if (j.status === "completed" && j.result) {
        const r = j.result, n = Object.values(r.read).reduce((a, b) => a + b, 0);
        app.toast(`Read ${n} news items: ${r.added.length} new target${r.added.length === 1 ? "" : "s"}${r.matched.length ? `, ${r.matched.length} already watched` : ""}${r.too_big.length ? `, ${r.too_big.length} too big` : ""}${r.not_sized?.length ? `, ${r.not_sized.length} not sized yet (${r.not_sized.join(", ")})` : ""}.${r.errors.length && !n ? " " + r.errors[0] : ""}`);
        app.bump();
      }
      if (j.status === "failed") app.toast(j.error || "The Sector Scout failed");
    }).catch((e) => app.toast(e.message)), 3000);
    return () => clearTimeout(t);
  }, [scoutJob]);
  const scouting = scoutJob?.status === "running";
  useEffect(() => {
    if (!withCandidates || app.scope === "All") { setCands(null); return; }
    api.candidates(app.scope).then((r) => setCands(r.candidates)).catch(() => setCands(null));
  }, [withCandidates, app.scope, app.version]);
  const [d, setD] = useState<SignalList | null>(null);
  const [sel, setSel] = useState<string | null>(app.signalSel);
  useEffect(() => { api.signals(app.scope, status).then(setD).catch((e) => app.toast(e.message)); }, [app.scope, status, app.version]);
  useEffect(() => { if (app.signalSel) { setSel(app.signalSel); app.clearSignalSel(); } }, [app.signalSel]);
  // switching company leaves an open thesis or the candidates for that company's own M&A Signals
  const scopeSeen = useRef(app.scope);
  useEffect(() => {
    if (scopeSeen.current === app.scope) return;
    scopeSeen.current = app.scope;
    setSel(null);
    setShowCands(false);
  }, [app.scope]);
  if (sel) return <ThesisView caseId={sel} onBack={() => setSel(null)} />;
  if (showCands) return <Candidates list={cands} onBack={() => setShowCands(false)} />;
  if (!d || d.status !== status) return <p className="sub">Loading…</p>;
  return (
    <>
      <div>
        <span className="crumb"><b>Radar</b> / {title} · {app.scope === "All" ? "all companies" : app.scope}</span>
        <h4>{title}</h4>
        <p className="sub">{intro}</p>
      </div>
      {tabs.length > 1 && (
        <div className="kfilter" role="tablist">
          {tabs.map(([k, l]) => <button key={k} type="button" role="tab" aria-pressed={k === status} onClick={() => setStatus(k)}>{l} · {d.counts[k]}</button>)}
          {withCandidates && <button type="button" role="tab" aria-pressed={false} onClick={() => setShowCands(true)}
            title={app.scope === "All" ? "Pick a company above to see its candidates" : undefined}>Candidates{cands ? ` · ${cands.length}` : ""}</button>}
        </div>
      )}
      {withCandidates && app.scope !== "All" && (
        <div className="btnrow" style={{ alignItems: "center", marginTop: 8 }}>
          <button className="btnx" disabled={scouting} onClick={() => api.scout(app.scope).then(setScoutJob).catch((e) => app.toast(e.message))}>
            {scouting ? "Reading the industry's news…" : `Scan ${app.scope}'s industry news now`}</button>
          <span className="sub" style={{ fontSize: 12 }}>The Sector Scout reads the last week of {app.scope}'s industry news daily and adds the smaller companies in it that {app.scope} could buy, with the news as their signals.</span>
        </div>
      )}
      {d.signals.length ? (
        <div className="cards">{d.signals.map((c) => <SignalCardView key={c.id} c={c} onView={() => setSel(c.id)} />)}</div>
      ) : <div className="empty2" style={{ padding: 24 }}>
        {empty[status]}
        {withCandidates && status === "open" && cands && cands.length > 0 && <>
          <p style={{ margin: "10px 0 6px" }}><b>{cands.length} candidate{cands.length === 1 ? "" : "s"}</b> {app.scope} could buy {cands.length === 1 ? "has" : "have"} been found but {cands.length === 1 ? "has" : "have"} no public signals yet.</p>
          <button className="btnx pri" onClick={() => setShowCands(true)}>See candidates</button>
        </>}
      </div>}
    </>
  );
}


/** M&A Signals → Candidates: targets the company could buy that have no public signals yet. */
function Candidates({ list, onBack }: { list: Candidate[] | null; onBack: () => void }) {
  const app = useApp();
  const co = app.scope;
  const [open, setOpen] = useState<number | null>(null);
  const [job, setJob] = useState<SignalJob | null>(null);
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setTimeout(() => api.targetJob(job.id).then((j) => {
      setJob(j);
      if (j.status === "completed") { app.toast("Target discovery finished."); app.bump(); }
      if (j.status === "failed") app.toast(j.error || "Target discovery failed");
    }).catch((e) => app.toast(e.message)), 3000);
    return () => clearTimeout(t);
  }, [job]);
  if (open !== null) return <CompetitorOverview id={open} company={co} onBack={() => setOpen(null)} />;
  const running = job?.status === "running";
  return (
    <>
      <div><a href="#" className="crumb" onClick={(e) => { e.preventDefault(); onBack(); }}>← Back to M&A Signals</a></div>
      <div>
        <span className="crumb"><b>Radar</b> / M&A Signals / Candidates · {co}</span>
        <h4>Candidates{list ? ` · ${list.length}` : ""}</h4>
        <p className="sub">Companies Target Discovery found that {co === "All" ? "an RPG company" : co} could buy — at most half its size, or not sized yet — but that have no public signals yet, so they are not M&A signals. Each moves to Signals once news, filings or results about it arrive. Overview opens its research and analysis.</p>
      </div>
      {co === "All" ? <div className="empty2" style={{ padding: 24 }}>Pick a company above to see its candidates.</div> : <>
        <div className="btnrow" style={{ alignItems: "center" }}>
          <button className="btnx" disabled={running} onClick={() => api.discoverTargets(co).then(setJob).catch((e) => app.toast(e.message))}>{running ? "Finding targets… (a few minutes)" : "Find more targets"}</button>
          <span className="sub" style={{ fontSize: 12 }}>Searches the web for companies matching {co}'s target profile and sizes each one; ones too big to buy are set aside.</span>
        </div>
        {!list ? <p className="sub">Loading…</p> : list.length ? (
          <div className="cards">{list.map((x) => (
            <div key={x.entity_id} className="card2">
              <div className="card2-h"><b className="rt" style={{ margin: 0 }}>{x.name}</b><span className="pill2">No signals yet</span></div>
              <div className="kv small">
                <div><small>Size</small><b className={x.size.ok === null ? "unverified" : ""}>{x.size.label.replace("the RPG company's", co)}</b></div>
                <div><small>Employees</small><b>{x.employees || "Not stated"}</b></div>
                <div><small>Clients</small><b>{x.clients || "Not stated"}</b></div>
                <div><small>Based in</small><b>{x.headquarters || "Not stated"}</b></div>
                <div><small>Listing</small><b>{x.nse_symbol ? `NSE: ${x.nse_symbol}` : "Not matched"}</b></div>
                <div><small>Found</small><b>{x.found_at || "—"}</b></div>
              </div>
              {x.why && <p className="sub" style={{ fontSize: 13 }}>{x.why} {x.sources.map((s, i) => <a key={s.url} href={s.url} target="_blank" rel="noreferrer" title={s.title}>[{i + 1}]</a>)}</p>}
              <div className="btnrow"><button className="btnx pri" onClick={() => setOpen(x.entity_id)}>Overview</button></div>
            </div>
          ))}</div>
        ) : <div className="empty2" style={{ padding: 24 }}>No candidates for {co} yet. Press Find more targets.</div>}
      </>}
    </>
  );
}
