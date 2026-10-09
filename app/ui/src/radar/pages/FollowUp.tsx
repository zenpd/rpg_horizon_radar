import { useEffect, useState } from "react";
import { api, type FollowUp as FU } from "../api";
import { Journey } from "../components/ui";
import { useApp } from "../state";

export default function FollowUp() {
  const app = useApp();
  const [list, setList] = useState<FU[] | null>(null);
  const [sel, setSel] = useState<string | null>(app.followSel);
  useEffect(() => { api.followUps(app.scope).then(setList); }, [app.scope, app.version]);
  useEffect(() => { if (app.followSel) setSel(app.followSel); }, [app.followSel]);

  if (!list) return <p className="sub">Loading follow-ups…</p>;
  if (!list.length)
    return (
      <>
        <div><h1>Nothing to follow up yet</h1><p className="sub">Each approved company gets an owner, a 90-day plan and watch rules here.</p></div>
        <Journey step={4} />
        <div className="empty2" style={{ padding: 28 }}>Approve a page in the deep-dive book and it appears here with its plan and watch rules.</div>
      </>
    );
  const c = list.find((x) => x.id === sel) || list[list.length - 1];
  const done = c.plan.filter((p) => p.done).length;
  const run = async (f: () => Promise<unknown>, msg: string) => { try { await f(); app.toast(msg); app.bump(); } catch (e) { app.toast((e as Error).message); } };

  return (
    <>
      <div>
        <h1>Follow-up · {list.length} approved</h1>
        <p className="sub">Each approved company has an owner, a 90-day plan and automatic watch rules. New signals land here after every daily run.</p>
      </div>
      <Journey step={4} />
      <div className="kfilter" role="tablist" aria-label="Approved companies">
        {list.map((x) => <button key={x.id} type="button" role="tab" aria-pressed={x.id === c.id} onClick={() => setSel(x.id)}>{x.who}{x.stage === "closed" ? " · closed" : ""}</button>)}
      </div>
      <div className="top"><div>
        <h2>{c.who} · {c.title}</h2>
        <p className="sub">{c.kind === "deal" ? "Target · deal to consider" : "Rival · threat to answer"} · for {c.companies.join(" · ")} · {c.in_book
          ? <a href="#" onClick={(e) => { e.preventDefault(); app.openBookAt(c.id); }}>Read its book page</a> : "Approved from an earlier book"}</p>
      </div></div>
      <div className="cols">
        <div className="stack">
          <div className="panel">
            <h5>90-day plan · {done} of {c.plan.length} done</h5>
            {c.plan.map((p, i) => (
              <div key={i} className={`chk${p.done ? " done" : ""}`}>
                <input type="checkbox" id={`pl_${i}`} checked={!!p.done} disabled={c.stage === "closed"}
                  onChange={(e) => run(() => api.planStep(c.id, i, e.target.checked, app.scope), e.target.checked ? "Step marked done." : "Step reopened.")} />
                <label htmlFor={`pl_${i}`}><b>{p.when} · {p.what}.</b> {p.how}</label>
              </div>
            ))}
          </div>
          <div className="panel">
            <h5>Updates since the overview</h5>
            {c.updates.length ? c.updates.map((u, i) => <div key={i} className={`upd${u.fresh ? " fresh" : ""}`}><time>{u.date}</time><p>{u.text}</p></div>) : <p className="sub">No updates yet.</p>}
            {c.stage === "act" && <div className="btnrow" style={{ marginTop: 10 }}><button className="btnx" id="cWeek" onClick={() => run(() => api.simulateWeek(c.id, app.scope), "Next week's run added an update.")}>Simulate next week's run</button></div>}
          </div>
        </div>
        <div className="stack">
          <div className="panel"><h5>Owner</h5><p style={{ margin: 0 }}><b>{c.owner}</b></p><p className="sub" style={{ fontSize: 12.5 }}>Approved {c.approved} · progress reviewed in the Monday digest</p></div>
          <div className="panel"><h5>Watching for</h5><ul style={{ margin: 0, paddingLeft: 18 }}>{c.watching.map((x) => <li key={x}>{x}</li>)}</ul>
            <p className="sub" style={{ fontSize: 12, marginTop: 6 }}>Set up automatically on approval. Any hit reopens this case at the top of This week.</p></div>
          {c.stage === "act" ? (
            <div className="decide-bar">
              <h5>Record the outcome</h5>
              <p className="sub" style={{ margin: 0 }}>Outcomes teach the radar which signals led to real decisions (the Learn step).</p>
              <div className="row">
                <button className="btnx pri" onClick={() => run(() => api.outcome(c.id, "acted", app.scope), "Outcome saved.")}>Close: acted on it</button>
                <button className="btnx" onClick={() => run(() => api.outcome(c.id, "dropped", app.scope), "Outcome saved.")}>Close: dropped</button>
              </div>
            </div>
          ) : <div className="callout"><b>Closed · {c.outcome}</b><p>Saved to the learning loop. Signal weights are reviewed monthly.</p></div>}
        </div>
      </div>
    </>
  );
}
