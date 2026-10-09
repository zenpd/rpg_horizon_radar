import type { CaseDetail, CaseSummary, SwotItem, SwotView } from "../api";
import { useApp } from "../state";
import { SparkChart } from "./charts";

const JOURNEY: [string, string][] = [
  ["SWOT", "Where each company stands"], ["Shortlist", "Pick the moves that fit"], ["Deep dive", "Agents do the expensive work"],
  ["Read the book", "One page per company"], ["Follow up", "Plan, watch, outcome"],
];

/** The five-step story bar shown on the main screens. */
export function Journey({ step }: { step: number }) {
  return (
    <div className="stepper journey" aria-label="How the radar works">
      {JOURNEY.map(([l, q], i) => (
        <div key={l} className={`stp ${i < step ? "done" : i === step ? "now" : ""}`} aria-current={i === step ? "step" : undefined}>
          <b>{i < step ? "✓ " : ""}{i + 1}. {l}</b><small>{q}</small>
        </div>
      ))}
    </div>
  );
}

/** One headline number: label, value and what is counted. */
export function Kpi({ label, value, sub }: { label: string; value: string | number; sub: string }) {
  return <div className="kpi"><small>{label}</small><b>{value}</b><span>{sub}</span></div>;
}

export const sCls = (s: number) => (s >= 70 ? "s-hi" : s >= 40 ? "s-md" : "s-lo");

export function CaseBadge({ c }: { c: CaseSummary }) {
  if (c.kind === "deal")
    return <div className={`score ${sCls(c.score!)}`} style={{ width: 54, height: 46 }}><b style={{ fontSize: 19 }}>{c.score}</b><small>score</small></div>;
  return <span className={`sev ${c.threat_class}`}>{c.threat}</span>;
}

/** Evidence shown under "Signals and quick look": free sources only. */
export function QuickLookBody({ c }: { c: CaseDetail }) {
  const q = c.quick;
  if (c.kind === "deal")
    return (
      <div className="cols">
        <div className="stack">
          <p style={{ margin: 0 }}>{q.story}</p>
          <div className="tl">{q.signals!.map((s, i) => <div key={i}><time>{s.date}</time><p><b>{s.label}:</b> {s.text} <span className="mini">{s.source}</span></p></div>)}</div>
        </div>
        <div className="stack">
          <div><small className="crumb">Score {q.score!.score}</small>
            <p className="sub" style={{ fontSize: 12.5, margin: "2px 0 0" }}>{q.score!.parts.map((p) => `${p[0]} ${p[1]}`).join(" + ")} = {q.score!.base}, × {q.score!.m} for {q.score!.n_types} signal types{q.score!.capped ? ", capped at 100" : ""}</p></div>
          {q.thesis && <div><small className="crumb">Fit with {q.thesis.company}'s thesis · {q.thesis.ok} of {q.thesis.total}</small>
            <div className="crit" style={{ marginTop: 4 }}>{q.thesis.checks.map((x) => <span key={x[0]} className={x[1] ? "ok" : "no"}>{x[1] ? "✓" : "✗"} {x[0]}</span>)}</div></div>}
          <div><small className="crumb">Who's involved</small>
            <p className="sub" style={{ fontSize: 12.5, margin: "2px 0 0" }}>{q.owners!.map((o) => `${o[0]} ${o[1]}%`).join(" · ")}
              {q.bidders!.length > 0 && <><br /><b>Rival interest:</b> {q.bidders!.join("; ")}</>}</p></div>
        </div>
      </div>
    );
  return (
    <div className="cols">
      <div className="stack">
        <p style={{ margin: 0 }}>{q.analyst}</p>
        <div className="tl">{q.timeline!.map((t, i) => <div key={i}><time>{t.date}</time><p><b>{t.label}:</b> {t.text} <span className="mini">{t.source}</span></p></div>)}</div>
      </div>
      <div className="stack">
        <div><small className="crumb">{q.spark!.t}</small><SparkChart sp={q.spark!} /></div>
        <div><small className="crumb">What customers say</small><p className="sub" style={{ fontSize: 12.5, margin: "2px 0 0" }}><b>{q.voc_top!.sentiment} · {q.voc_top!.topic}</b> {q.voc_top!.text}</p></div>
      </div>
    </div>
  );
}

/** 2×2 SWOT. `big` shows every item; the small version is a tile on the group view. */
// "Talent Tracker, Patent Scout · Demo data" under a SWOT item.
function SourceLine({ sources }: { sources: SwotItem["sources"] }) {
  if (!sources.length) return <small className="sw-src">No linked source</small>;
  const names = [...new Set(sources.map((x) => x.source.split(" · ")[0]))].slice(0, 3);
  const origins = [...new Set(sources.map((x) => x.origin_label))];
  return <small className="sw-src">{names.join(", ")}{sources.length > names.length ? ` +${sources.length - names.length}` : ""} · {origins.join(", ")}</small>;
}

export function SwotBox({ s, big, hl, dim }: { s: SwotView; big: boolean; hl?: Set<string>; dim?: boolean }) {
  const { openRow } = useApp();
  const Q: ["S" | "W" | "O" | "T", string, string][] = [["S", "Strengths", "Internal · helps"], ["W", "Weaknesses", "Internal · hurts"], ["O", "Opportunities", "External · helps"], ["T", "Threats", "External · hurts"]];
  return (
    <div className={`swot${big ? " big" : ""}${dim ? " dim" : ""}`} aria-label={`SWOT for ${s.company}`}>
      {Q.map(([k, l, sub]) => (
        <div key={k} className={`sq q${k}`}>
          <div className="sqh"><b>{l}</b><small>{sub}</small></div>
          {big ? (
            <ol>
              {s[k].map((x) => (
                <li key={x.id} id={`sw_${x.id}`} className={`${x.case_id ? "sig" : ""}${hl?.has(x.id) ? " hl" : ""}`}>
                  <span className="mono">{x.id}</span>
                  <span>{x.text}{x.case_id && <> <a href="#" className="sw-link" onClick={(e) => { e.preventDefault(); openRow(x.case_id!, s.company); }}>signals</a></>}
                    <SourceLine sources={x.sources} /></span>
                </li>
              ))}
            </ol>
          ) : (
            <p><b className="mono">{s[k].length}</b> {s[k][0]?.text}</p>
          )}
        </div>
      ))}
    </div>
  );
}


// "How this SWOT was built": the method, then each item's reasoning and full list of sources.
export function SwotDetails({ s }: { s: SwotView }) {
  const m = s.method;
  const Q: ["S" | "W" | "O" | "T", string][] = [["S", "Strengths"], ["W", "Weaknesses"], ["O", "Opportunities"], ["T", "Threats"]];
  return (
    <details className="panel swdetails">
      <summary><b>How this SWOT was built</b> <span className="sub">{m.built_by === "agent" ? `SWOT Analyst · ${m.at}` : "demo data"} · reasoning and sources for every item</span></summary>
      <p>{m.summary}</p>
      {m.built_by === "demo" && (
        <p className="sub">{m.live_signals_available
          ? `${m.live_signals_available} live signals are available for ${s.company}. Press "Rebuild with SWOT Analyst" to build the SWOT from them.`
          : "No live signals yet for this company: map its rival to a real company under Radar settings → Watched companies, refresh live signals, then rebuild."}</p>
      )}
      {m.steps.length > 0 && <ol className="swsteps">{m.steps.map((x, i) => <li key={i}>{x}</li>)}</ol>}
      {Q.map(([k, label]) => (
        <div key={k} className="swd-q">
          <h5>{label}</h5>
          {s[k].map((x) => (
            <div key={x.id} className="swd-item">
              <div><span className="mono">{x.id}</span> <b>{x.text}</b></div>
              {x.reasoning ? <p className="swd-why"><b>Why:</b> {x.reasoning}</p> : <p className="swd-why sub">No reasoning: written by hand for the demo.</p>}
              {x.sources.length ? (
                <ul className="swd-src">{x.sources.map((y) => (
                  <li key={y.id}>
                    <span className={`chip ${y.origin}`}>{y.origin_label}</span>{" "}
                    <span className="sub">{y.source}{y.date ? ` · ${y.date}` : ""}</span> {y.url ? <a href={y.url} target="_blank" rel="noreferrer">{y.text}</a> : y.text}
                  </li>
                ))}</ul>
              ) : <p className="sub swd-why">No source linked.</p>}
            </div>
          ))}
        </div>
      ))}
    </details>
  );
}
