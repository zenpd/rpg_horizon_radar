import { useEffect, useState } from "react";
import { api, type Home as HomeData, type RecCard, type SwotJob, type SwotView } from "../api";
import { PositionChart } from "../components/charts";
import { CaseBadge, Journey, Kpi, QuickLookBody, SwotBox, SwotDetails } from "../components/ui";
import { slug, useApp } from "../state";

export default function Home() {
  const app = useApp();
  const [d, setD] = useState<HomeData | null>(null);
  const [hl, setHl] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState<Set<string>>(new Set());

  useEffect(() => { api.home(app.scope).then(setD).catch((e) => app.toast(e.message)); }, [app.scope, app.version]);

  // Jump to a company's row when another screen asked for it.
  useEffect(() => {
    if (!d || !app.focus) return;
    const k = slug(app.focus);
    setOpen((o) => new Set(o).add(k));
    requestAnimationFrame(() => {
      const row = document.getElementById("row_" + k) || document.getElementById("row_" + k + "_s");
      if (!document.getElementById("row_" + k)) (document.querySelector("details.skip") as HTMLDetailsElement | null)?.setAttribute("open", "");
      if (row) { row.scrollIntoView({ block: "center", behavior: "smooth" }); row.classList.add("flash"); setTimeout(() => row.classList.remove("flash"), 1600); }
      app.clearFocus();
    });
  }, [d, app.focus]);

  if (!d || d.scope !== app.scope) return <p className="sub">Loading this week…</p>;
  const all = d.scope === "All";

  return (
    <>
      <div>
        <h1>{all ? "Where each RPG company stands, and the moves that fit" : `${app.scope}: where it stands, and the moves that fit`}</h1>
        <p className="sub">{d.week} · SWOT rebuilt from today's 17:00 run · {d.signal_count} signals · illustrative data</p>
      </div>
      <div className="kpis">
        <Kpi label="Signals" value={d.signal_count} sub={all ? "Behind the SWOTs of all companies" : `Behind ${app.scope}'s SWOT`} />
        <Kpi label="Recommended moves" value={d.recommended.length} sub="Link a strength or weakness to an opportunity or threat" />
        <Kpi label="Watched, not recommended" value={d.set_aside.length} sub="Companies with signals that do not fit the SWOT" />
        <Kpi label="Shortlisted" value={`${app.shortlist.length} of 5`} sub="Moves picked for a deep dive" />
      </div>
      <Journey step={app.shortlist.length ? 1 : 0} />
      {all ? (
        <div className="swgrid">
          {d.tiles!.map((t) => (
            <button key={t.company} className="swtile" onClick={() => app.setScope(t.company)}>
              <span className="swt-h"><b>{t.company}</b><span className="sub">{t.moves} move{t.moves > 1 ? "s" : ""} fit · {t.set_aside} set aside</span></span>
              <SwotBox s={t} big={false} />
            </button>
          ))}
        </div>
      ) : (
        <>
          <SwotAgentBar co={app.scope} source={d.swot!.source} />
          <SwotBox s={d.swot!} big hl={hl} dim={hl.size > 0} />
          <PositionChart co={app.scope} items={d.positions!} onHover={(id) => setHl(id ? new Set([id]) : new Set())} onOpen={(cid) => app.openRow(cid, app.scope)} />
          <SwotDetails s={d.swot!} />
        </>
      )}
      <div className="callout analyst">
        <b>Analyst overview</b><p>{d.analyst}</p>
        <span className="sub" style={{ fontSize: 12 }}>Opportunities and threats come from the signals. Strengths and weaknesses come from {all ? "each company's" : `${app.scope}'s`} own filings and plans, checked against peers and confirmed by the strategy team. A move is recommended only when it links the two.</span>
      </div>
      <div className="homecols">
        <div className="stack" style={{ minWidth: 0 }}>
          <div className="intro">
            <h5 style={{ margin: 0 }}>Recommended moves · {d.recommended.length}</h5>
            <span className="sub" style={{ fontSize: 12 }}>{all ? "Pick a company above to see its full SWOT" : "Hover a move to see the SWOT items behind it"}</span>
          </div>
          <div className="digest">
            {d.recommended.map((r) => (
              <Rec key={r.case_id} r={r} all={all} open={open.has(slug(r.case_id))}
                onToggle={(o) => setOpen((s) => { const n = new Set(s); o ? n.add(slug(r.case_id)) : n.delete(slug(r.case_id)); return n; })}
                onHover={(on) => !all && setHl(on ? new Set(r.uses) : new Set())} />
            ))}
          </div>
          {d.set_aside.length > 0 && (
            <details className="panel skip">
              <summary><b>Watched, not recommended · {d.set_aside.length}</b> <span className="sub">companies with signals that don't fit the SWOT this week</span></summary>
              <div className="skiplist">
                {d.set_aside.map((s) => (
                  <div key={s.co + s.case_id} id={`row_${slug(s.case_id)}_s`}><b>{s.who}</b> <span className="pill2">{s.co}</span><p className="sub" style={{ margin: "2px 0 0", fontSize: 12.5 }}>{s.why}</p></div>
                ))}
              </div>
            </details>
          )}
        </div>
        <aside className="panel feed" aria-label="Signals behind the SWOT">
          <h5>Signals behind the SWOT</h5>
          {d.signals.map((f, i) => (
            <button key={i} className="fitem" onClick={() => app.openRow(f.case_id)}>
              <time>{f.date}</time>
              <span><b>{f.who}</b> · {f.label}<br /><span className="sub">{f.text.length > 90 ? f.text.slice(0, 88) + "…" : f.text}</span></span>
            </button>
          ))}
          <p className="sub" style={{ fontSize: 11.5, marginTop: 8 }}>{d.signal_count} signals in total.</p>
        </aside>
      </div>
      <ShortlistBar names={Object.fromEntries(d.recommended.map((r) => [r.case_id, r.case.who]))} />
    </>
  );
}

function Rec({ r, all, open, onToggle, onHover }: { r: RecCard; all: boolean; open: boolean; onToggle: (o: boolean) => void; onHover: (on: boolean) => void }) {
  const app = useApp();
  const c = r.case, k = slug(c.id), inD = c.stage === "digest", on = app.shortlist.includes(c.id);
  return (
    <div className={`drow rec${on ? " on" : ""}`} id={`row_${k}`} tabIndex={-1}
      onMouseEnter={() => onHover(true)} onMouseLeave={() => onHover(false)} onFocus={() => onHover(true)} onBlur={() => onHover(false)}>
      <div className="dmain">
        {inD ? (
          <label className="slbox" htmlFor={`sl_${k}`}>
            <input type="checkbox" id={`sl_${k}`} checked={on} onChange={(e) => { if (!app.toggleShortlist(c.id, e.target.checked)) e.target.checked = false; }} />
            <span>Shortlist</span>
          </label>
        ) : <span className="slbox done" aria-hidden="true"><span>{c.stage === "closed" ? "Closed" : "Escalated"}</span></span>}
        <div className="dtxt">
          <span className={`tows t${r.type}`}>{r.tows[0]} · {r.tows[1]}</span>
          <p className="rt">{r.title}</p>
          <p className="sub" style={{ fontSize: 12.8 }}>{r.why}</p>
          <div className="uses">
            {r.uses.map((u) => <span key={u} className={`u${u[0]}`} title={r.uses_text[u]}>{u}</span>)}
            <span className="sub" style={{ fontSize: 11.5 }}>{all ? r.co + " · " : ""}{c.who} · {c.kind === "deal" ? "target" : "rival"}</span>
          </div>
          {!inD && (
            <p className="sub" style={{ fontSize: 12, marginTop: 4 }}>
              <span className={`esc-badge${c.stage === "closed" ? " closed" : ""}`}>{c.stage === "closed" ? "Closed" : "Escalated"}</span>
              <b>{c.status_label}</b> · <a href="#" onClick={(e) => { e.preventDefault(); c.owner ? app.openFollowUp(c.id) : app.openBookAt(c.id); }}>{c.owner ? "Open follow-up" : "Open book page"}</a>
            </p>
          )}
        </div>
        <CaseBadge c={c} />
      </div>
      <details id={`det_${k}`} open={open} onToggle={(e) => onToggle((e.target as HTMLDetailsElement).open)}>
        <summary>Signals and quick look · {c.who}</summary>
        <QuickLookBody c={c} />
      </details>
    </div>
  );
}

// Runs the SWOT Analyst agent for one company, polls the job, then reloads the screen.
function SwotAgentBar({ co, source }: { co: string; source: SwotView["source"] }) {
  const app = useApp();
  const [job, setJob] = useState<SwotJob | null>(null);

  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setTimeout(() => api.swotJob(job.id).then((j) => {
      setJob(j);
      if (j.status === "completed") { app.toast(`SWOT Analyst rebuilt ${co}'s SWOT`); app.bump(); }
      if (j.status === "failed") app.toast(j.error || "The SWOT Analyst failed");
    }).catch((e) => app.toast(e.message)), 1500);
    return () => clearTimeout(t);
  }, [job]);

  const running = job?.status === "running";
  return (
    <div className="btnrow" style={{ alignItems: "center", gap: 10 }}>
      <span className="sub" style={{ fontSize: 12 }}>
        {source.by === "agent" ? `Written by the SWOT Analyst agent (${source.model}) · ${source.at}` : "Mock SWOT from the demo data"}
      </span>
      {app.groupView && <button className="btnx" disabled={running} onClick={() => api.rebuildSwot(co).then(setJob).catch((e) => app.toast(e.message))}>
        {running ? `SWOT Analyst working… round ${Math.max(job!.round, 1)} of ${job!.max_rounds}` : "Rebuild with SWOT Analyst"}
      </button>}
    </div>
  );
}

// `names` maps a case id to its company, from the moves listed on this page.
function ShortlistBar({ names }: { names: Record<string, string> }) {
  const app = useApp();
  return (
    <div className="slbar" id="slbar">
      {app.shortlist.length ? (
        <>
          <span><b>{app.shortlist.length} shortlisted:</b> {app.shortlist.map((id) => names[id] || id).join(", ")}</span>
          <span className="spacer" />
          <button className="btnx" onClick={app.clearShortlist}>Clear</button>
          <button className="btnx pri" onClick={() => app.escalate()}>Escalate {app.shortlist.length} for deep dive</button>
        </>
      ) : (
        <span className="sub">Tick <b>Shortlist</b> on the moves you want to pursue (up to 5). Only those get a deep dive and a page in the book.</span>
      )}
    </div>
  );
}

