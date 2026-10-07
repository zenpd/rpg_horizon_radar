import { useEffect, useState } from "react";
import { api, type Rival } from "../api";
import { CompetitorOverview } from "../components/overview";
import { ScorePill } from "../components/ui";
import { useApp } from "../state";

/** Radar → Competitor Analysis: a card per watched company, and its overview (moves, financials, SWOT,
 * how it competes, threat, what to watch) on demand. */
export default function Competitors() {
  const app = useApp();
  const co = app.cur;
  const [list, setList] = useState<Rival[] | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  useEffect(() => { api.competitors(co).then((d) => setList(d.rivals)).catch((e) => app.toast(e.message)); }, [co, app.version]);

  // Another screen asked to open one company (by its case id).
  useEffect(() => {
    if (!list || !app.focus) return;
    const hit = list.find((x) => x.case_id === app.focus);
    if (hit) setSel(hit.entity_id);
    app.clearFocus();
  }, [list, app.focus]);
  useEffect(() => { setSel(null); }, [co]);

  if (!list) return <p className="sub">Loading competitors…</p>;
  if (sel !== null && list.some((x) => x.entity_id === sel)) {
    return <CompetitorOverview id={sel} company={co} onBack={() => setSel(null)} />;
  }
  return (
    <>
      <div>
        <span className="crumb"><b>Radar</b> / Competitor Analysis · {co}</span>
        <h4>{co}'s competitors and their moves · {list.length}</h4>
        <p className="sub">Competitors and adjacent players {co} watches, found by discovery or added by hand, with their recent public moves (news, filings, patents, hiring, deals) and rule-based scores.
          {app.scope === "All" && <> Showing {co} — pick a company above to change.</>}</p>
      </div>
      {!list.length ? (
        <div className="empty2" style={{ padding: 24 }}>No companies on {co}'s watchlist yet. Discovery finds them weekly (or press Find rivals now in Radar settings → Watched companies), or add them in Users and watchlist → Watchlist.</div>
      ) : (
        <div className="cards">
          {list.map((x) => (
            <div key={x.name} className="card2">
              <div className="card2-h">
                <b className="rt" style={{ margin: 0 }}>{x.name}</b>
                <ScorePill score={x.score} detail={x.score_detail} />
              </div>
              <div className="kv small">
                <div><small>Listing</small><b>{x.nse_symbol ? `NSE: ${x.nse_symbol}` : "Not matched"}</b></div>
                <div><small>Size</small><b>{x.size.label.replace("the RPG company's", co)}</b></div>
                <div><small>Recent moves · 120 days</small><b>{x.signals}</b></div>
                <div><small>On the watchlist</small><b>{x.origin === "manual" ? "Added by hand" : x.found_at ? `Found ${x.found_at}` : "Found by discovery"}</b></div>
              </div>
              <p className="sub" style={{ fontSize: 13 }}>{x.latest_move ? <><b>Latest move · {x.latest_date}:</b> {x.latest_move.length > 140 ? x.latest_move.slice(0, 138) + "…" : x.latest_move}</> : "No recent moves in the last 120 days."}</p>
              <div className="btnrow">
                <button className="btnx" onClick={() => setSel(x.entity_id)}>Overview</button>
                {x.case_id && (x.size.ok === true || (x.size.ok === null && x.role === "target")) && <button className="btnx pri" onClick={() => app.openSignal(x.case_id!)}>Acquisition thesis</button>}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
