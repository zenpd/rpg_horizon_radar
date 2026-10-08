import { useState } from "react";
import type { CaseDetail, CaseSummary, ScoreDetail, Signal, SwotItem, SwotView } from "../api";
import { useApp } from "../state";

export const sCls = (s: number) => (s >= 70 ? "s-hi" : s >= 40 ? "s-md" : "s-lo");

/** The rule-based opportunity score, or a note that the company has none yet. */
export function CaseBadge({ c }: { c: CaseSummary }) {
  if (c.score === null) return <span className="pill2" title="Not scored yet">no score</span>;
  return <div className={`score ${sCls(c.score)}`} style={{ width: 54, height: 46 }}><b style={{ fontSize: 19 }}>{Math.round(c.score)}</b><small>score</small></div>;
}

/** A list of public signals, each linking to its source. */
export function SignalList({ signals }: { signals: Signal[] }) {
  return (
    <div className="tl">
      {signals.map((s, i) => (
        <div key={i}><time>{s.date}</time>
          <p><b>{s.label}:</b> {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.text}</a> : s.text} <span className="mini">{s.source}{s.url ? " ↗" : ""}</span></p>
        </div>
      ))}
    </div>
  );
}

/** "Signals and quick look": the company's public signals and how its score was reached. */
export function QuickLookBody({ c }: { c: CaseDetail }) {
  const q = c.quick;
  return (
    <div className="cols">
      <div className="stack"><SignalList signals={q.signals} /></div>
      <div className="stack">
        {q.score ? (
          <div><small className="crumb">Score {Math.round(q.score.score)} · rule-based</small>
            <p className="sub" style={{ fontSize: 12.5, margin: "2px 0 0" }}>{q.score.rationale || `Signal types: ${q.score.types.join(", ")}`}</p></div>
        ) : <p className="sub" style={{ fontSize: 12.5 }}>Not scored yet: the score is computed after the next ingestion run.</p>}
        <p className="sub" style={{ fontSize: 12 }}>Watched for {c.companies.join(", ")} · public sources only</p>
      </div>
    </div>
  );
}

// "Annual report, NSE · Live" under a SWOT item.
function SourceLine({ sources }: { sources: SwotItem["sources"] }) {
  if (!sources.length) return <small className="sw-src">No linked source</small>;
  const names = [...new Set(sources.map((x) => x.source.split(" · ")[0]))].slice(0, 3);
  const origins = [...new Set(sources.map((x) => x.origin_label))];
  return <small className="sw-src">{names.join(", ")}{sources.length > names.length ? ` +${sources.length - names.length}` : ""} · {origins.join(", ")}</small>;
}

/** 2×2 SWOT. `big` shows every item; the small version is a tile on the group view. */
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
                  <span>{x.factor && <span className="chip factor">{x.factor}</span>} {x.text}{x.case_id && <> <a href="#" className="sw-link" onClick={(e) => { e.preventDefault(); openRow(x.case_id!, s.company); }}>signals</a></>}
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
      <summary><b>How this SWOT was built</b> <span className="sub">SWOT Analyst · {m.at} · reasoning and sources for every item</span></summary>
      <p>{m.summary}</p>
      {m.steps.length > 0 && <ol className="swsteps">{m.steps.map((x, i) => <li key={i}>{x}</li>)}</ol>}
      {Q.map(([k, label]) => (
        <div key={k} className="swd-q">
          <h5>{label}</h5>
          {s[k].map((x) => (
            <div key={x.id} className="swd-item">
              <div><span className="mono">{x.id}</span> <b>{x.text}</b>{x.factor && <> <span className="chip factor">{x.factor}</span></>}</div>
              {x.reasoning && <p className="swd-why"><b>Why:</b> {x.reasoning}</p>}
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


/** "Opportunity score: 72" with an "i" that shows how that number was calculated. */
export function ScorePill({ score, detail, label = "Opportunity score" }: { score: number | null; detail: ScoreDetail | null | undefined; label?: string }) {
  const [open, setOpen] = useState(false);
  const competitor = label !== "Opportunity score";
  return (
    <span className="score-wrap">
      <span className="score-pill">{label}: {score !== null ? Math.round(score) : "–"}</span>
      <button className="info-i" aria-label={`How the ${label.toLowerCase()} is calculated`} aria-expanded={open} onClick={() => setOpen(!open)}>i</button>
      {open && (
        <div className="score-pop" role="dialog">
          <div className="card2-h"><b>How the {label.toLowerCase()} is calculated</b><button className="info-x" aria-label="Close" onClick={() => setOpen(false)}>×</button></div>
          <p>Rule-based, no AI. Each kind of public move in the latest {detail?.window_days ?? 90} days adds its weight once; several kinds at the same time multiply the total; the result is capped at {detail?.max ?? 100}. {competitor
            ? "A higher score means the company is making more moves at once — deals, fund raises, leadership changes, results, distress — so it needs closer watching."
            : "A higher score means more signs of change or distress that could open an M&A opportunity. It does not say whether the company can be bought: see its size."}</p>
          {detail ? <>
            <table className="tbl score-tbl"><tbody>
              {detail.parts.map((p) => <tr key={p.type}><td style={{ textTransform: "capitalize" }}>{p.type}</td><td className="num">+{p.weight}</td></tr>)}
              <tr><td><b>Sum of weights</b></td><td className="num"><b>{detail.base}</b></td></tr>
              <tr><td>× {detail.kinds} kind{detail.kinds === 1 ? "" : "s"} of move at once</td><td className="num">× {detail.multiplier}</td></tr>
              <tr><td><b>Score</b>{detail.raw > detail.max ? ` (${detail.raw}, capped)` : ""}</td><td className="num"><b>{detail.score}</b></td></tr>
            </tbody></table>
            <p className="sub" style={{ fontSize: 11.5, margin: 0 }}>Multiplier: ×{detail.multipliers["1"]} for 1 kind, ×{detail.multipliers["2"]} for 2, ×{detail.multipliers["3"]} for 3, ×{detail.multipliers["4+"]} for 4 or more. Weights: credit downgrade 30; delayed filing, promoter pledge, auditor change 25; leadership churn, distress news, legal action, earnings decline 20; patent shift, hiring scale-down, opportunity news, stake sell-down, share-price slump, deal activity 15; hiring scale-up, fund raise 10.</p>
          </> : <p className="sub" style={{ margin: 0 }}>No public moves in the window, so no score.</p>}
        </div>
      )}
    </span>
  );
}
