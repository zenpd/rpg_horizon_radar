import { useEffect, useState } from "react";
import { api, type CaseSummary, type Overview } from "../api";
import { HBars, OwnershipGraph } from "../components/charts";
import { Journey } from "../components/ui";
import { useApp } from "../state";

type Page = CaseSummary & { recommendation: string };

export default function Book() {
  const app = useApp();
  const [pages, setPages] = useState<Page[] | null>(null);
  const [ov, setOv] = useState<Overview | null>(null);
  useEffect(() => { api.book().then((b) => setPages(b.pages)); }, [app.version]);

  const N = pages && pages.length ? pages.length + 2 : 0;
  const p = Math.max(0, Math.min(app.bookPage, Math.max(0, N - 1)));
  const c = pages && p >= 1 && p <= pages.length ? pages[p - 1] : null;

  useEffect(() => { setOv(null); if (c) api.overview(c.id).then(setOv); }, [c?.id, app.version]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (/INPUT|SELECT|TEXTAREA/.test((document.activeElement as HTMLElement)?.tagName || "")) return;
      if (e.key === "ArrowRight" && p < N - 1) { app.setBookPage(p + 1); window.scrollTo(0, 0); }
      if (e.key === "ArrowLeft" && p > 0) { app.setBookPage(p - 1); window.scrollTo(0, 0); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [p, N]);

  if (!pages) return <p className="sub">Loading the book…</p>;
  if (!N)
    return (
      <>
        <div><span className="crumb"><b>Deep-dive book</b></span><h4>No pages yet</h4></div>
        <Journey step={3} />
        <div className="empty2" style={{ padding: 28 }}>
          Shortlist companies on <b>This week</b> and escalate them. Agents then write one page per company here.
          <div className="btnrow" style={{ justifyContent: "center", marginTop: 12 }}><button className="btnx pri" onClick={() => app.go("home")}>Go to This week</button></div>
        </div>
      </>
    );

  const go = (n: number) => { app.setBookPage(n); window.scrollTo(0, 0); };
  const tabs: [string, number, boolean][] = [["Cover", 0, false], ...pages.map((x, i) => [x.who, i + 1, x.stage === "decide"] as [string, number, boolean]), ["Decisions", N - 1, false]];

  return (
    <>
      <div><span className="crumb"><b>Deep-dive book</b> · Week 40</span><h4>{pages.length} compan{pages.length > 1 ? "ies" : "y"} · one page each</h4></div>
      <Journey step={3} />
      <div className="booknav">
        <button className="btnx" disabled={p === 0} onClick={() => go(p - 1)}>← Previous</button>
        <div className="bktabs">{tabs.map(([l, i, pend]) => <button key={i} type="button" aria-current={i === p ? "page" : "false"} onClick={() => go(i)}>{l}{pend && <> <i className="dot" /></>}</button>)}</div>
        <button className="btnx" disabled={p === N - 1} onClick={() => go(p + 1)}>Next →</button>
      </div>
      <div className="pagewrap turn" key={p}>
        {p === 0 && <Cover pages={pages} go={go} />}
        {c && (ov ? (ov.kind === "deal" ? <DealPage o={ov} /> : <ThreatPage o={ov} />) : <p className="sub">Loading page…</p>)}
        {p === N - 1 && <Decisions pages={pages} go={go} />}
        <div className="pgno">Page {p + 1} of {N}</div>
      </div>
      <div className="booknav bottom">
        <button className="btnx" disabled={p === 0} onClick={() => go(p - 1)}>← Previous</button>
        <span className="sub">Tip: use the ← → keys to turn pages</span>
        <button className="btnx pri" disabled={p === N - 1} onClick={() => go(p + 1)}>Next page →</button>
      </div>
    </>
  );
}

function statusOf(x: CaseSummary) { return x.stage === "decide" ? "Decision pending" : x.owner ? "Approved" : x.outcome || ""; }

function Cover({ pages, go }: { pages: Page[]; go: (n: number) => void }) {
  const app = useApp();
  return (
    <article className="doc page">
      <header className="doc-h">
        <span className="eb">Deep-dive book · Week 40 · written 29 Sep</span>
        <h3>{pages.length} compan{pages.length > 1 ? "ies" : "y"} for decision</h3>
        <p>Escalated by {app.scope === "All" ? "Group strategy" : app.scope + " strategy team"} · prepared by 7 agents · each page is fixed once written</p>
      </header>
      <section>
        <h5>Contents</h5>
        <div className="toc">
          {pages.map((c, i) => (
            <button key={c.id} className="tocrow" onClick={() => go(i + 1)}>
              <span className="mono">p. {i + 2}</span>
              <span><b>{c.who}</b> <span className={`kchip ${c.kind}`}>{c.kind === "deal" ? "Target" : "Rival"}</span><br /><span className="sub">{c.title}</span></span>
              <span className="sub" style={{ textAlign: "right" }}>Recommends: {c.recommendation}<br /><b>{statusOf(c)}</b></span>
            </button>
          ))}
        </div>
      </section>
      <section><h5>How to read this book</h5><p>Each page covers one company: why it is in the book, what happened, why it matters, what could happen, the risks and a 90-day plan. Every page ends with a decision. The last page lists all decisions.</p></section>
      <div className="btnrow"><button className="btnx pri" onClick={() => go(1)}>Start reading</button></div>
    </article>
  );
}

function Decisions({ pages, go }: { pages: Page[]; go: (n: number) => void }) {
  const app = useApp();
  return (
    <article className="doc page">
      <header className="doc-h"><span className="eb">Deep-dive book · last page</span><h3>Decisions</h3><p>{pages.filter((c) => c.stage !== "decide").length} of {pages.length} decided</p></header>
      <div style={{ overflowX: "auto" }}>
        <table className="tbl">
          <thead><tr><th>Company</th><th>Recommendation</th><th>Decision</th><th>Owner</th></tr></thead>
          <tbody>
            {pages.map((c, i) => (
              <tr key={c.id}>
                <td><a href="#" onClick={(e) => { e.preventDefault(); go(i + 1); }}>{c.who}</a></td><td>{c.recommendation}</td>
                <td>{c.stage === "decide" ? <span className="pill2 fired">Pending</span> : statusOf(c)}</td><td>{c.owner || "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages.some((c) => c.owner) && <div className="btnrow"><button className="btnx pri" onClick={() => app.go("follow")}>Go to follow-up</button></div>}
    </article>
  );
}

function DocHead({ o, kind }: { o: Overview; kind: string }) {
  return (
    <>
      <header className="doc-h">
        <span className="eb">Detailed overview · v1 · written {o.written} · fixed once written</span>
        <h3>{o.title}</h3>
        <p>{kind} · prepared for {o.company} leadership{o.kind === "deal" ? " and Group M&A" : ""}</p>
      </header>
      {o.why && (
        <div className="whybox">
          <small>Why this is in the book · from {o.why.company}'s SWOT</small>
          <b>{o.why.title}</b>
          <div className="uses">{o.why.uses.map((u) => <div key={u.id}><span className={`u${u.id[0]}`}>{u.id}</span> <span className="sub" style={{ fontSize: 12.5 }}>{u.text}</span></div>)}</div>
        </div>
      )}
      <div className="reco">
        <small>Recommendation</small><b>{o.recommendation.title}.</b><p>{o.recommendation.text}</p>
        <p className="need"><b style={{ fontFamily: "var(--body)", fontSize: 13.5 }}>Decision needed:</b> {o.recommendation.decision} Confidence {o.recommendation.confidence}%.</p>
      </div>
      <div className="kv">{o.glance.map(([k, v]) => <div key={k}><small>{k}</small><b>{v}</b></div>)}</div>
    </>
  );
}

function Plan({ o }: { o: Overview }) {
  return <div className="tl">{o.plan.map((p) => <div key={p.when}><time>{p.when.replace("Days ", "")}</time><p><b>{p.what}.</b> {p.how}</p></div>)}</div>;
}

function Copy({ o }: { o: Overview }) {
  const app = useApp();
  const txt = `${o.who}: ${o.title}\nRecommendation: ${o.recommendation.title}. ${o.recommendation.text}\nDecision needed: ${o.recommendation.decision}`;
  return <div className="btnrow"><button className="btnx" onClick={() => navigator.clipboard?.writeText(txt).then(() => app.toast("Summary copied."), () => app.toast("Copy isn't available here. Select the text instead."))}>Copy summary</button></div>;
}

function DecisionBar({ o }: { o: Overview }) {
  const app = useApp();
  const [owner, setOwner] = useState(o.owners[0]);
  if (o.stage !== "decide") return <div className="stamp">{o.owner ? `Approved ${o.approved} · owner: ${o.owner}` : o.outcome}</div>;
  const act = async (a: "approve" | "park" | "reject") => {
    try {
      await api.decide(o.id, a, a === "approve" ? owner : undefined, app.scope);
      app.toast(a === "approve" ? `Approved. ${o.who} moves to Follow-up with ${owner}.` : a === "park" ? "Parked. It comes back in 90 days or on a new signal." : "Rejected.");
      app.bump();
    } catch (e) { app.toast((e as Error).message); }
  };
  return (
    <div className="decide-bar">
      <h5>Decision</h5>
      <p className="sub" style={{ margin: 0 }}>Approving names an owner, turns the 90-day plan into tracked steps and sets up watch rules. The company then moves to Follow-up.</p>
      <div className="row">
        <label htmlFor="cOwner">Owner<select id="cOwner" value={owner} onChange={(e) => setOwner(e.target.value)}>{o.owners.map((x) => <option key={x}>{x}</option>)}</select></label>
        <button className="btnx pri" onClick={() => act("approve")}>Approve and assign owner</button>
        <button className="btnx" onClick={() => act("park")}>Park for 90 days</button>
        <button className="btnx" onClick={() => act("reject")}>Reject</button>
      </div>
    </div>
  );
}

function DealPage({ o }: { o: Overview }) {
  const h = o.health!, sc = o.scenario;
  return (
    <>
      <article className="doc page">
        <DocHead o={o} kind="Deal to consider" />
        <section><h5>1. What happened</h5><p>{o.story}</p><div className="tl">{o.signals!.map((s, i) => <div key={i}><time>{s.date}</time><p><b>{s.label}:</b> {s.text}</p></div>)}</div></section>
        <section>
          <h5>2. Why it matters for {o.company}</h5>
          <p><b>Impact if we do nothing: {o.impact![0]}.</b> {o.impact![1]}</p>
          <ul>{o.pros!.map((x) => <li key={x}>{x}</li>)}</ul>
          {o.thesis!.length > 0 && <div className="crit">{o.thesis!.map((x) => <span key={x[0]} className={x[1] ? "ok" : "no"}>{x[1] ? "✓" : "✗"} {x[0]}</span>)}</div>}
        </section>
        <section>
          <h5>3. Financial health</h5>
          <div className="verdict"><small className="crumb">Health verdict · fixed rules</small><br /><b>{h.verdict[0]}</b><p style={{ margin: "4px 0 0" }}>{h.verdict[1]}</p></div>
          <div className="kv">{h.kv.map(([k, v]) => <div key={k}><small>{k}</small><b>{v}</b></div>)}</div>
          <div className="subcol">
            <div><h6>Revenue · ₹ crore</h6><HBars vals={h.revenue} years={h.years} fmt={(x) => x.toLocaleString("en-IN")} /></div>
            <div><h6>EBITDA margin · %</h6><HBars vals={h.margin} years={h.years} fmt={(x) => x + "%"} /></div>
          </div>
          <div className="crit" style={{ flexDirection: "column", alignItems: "flex-start", gap: 6 }}>{h.checks.map((c) => <span key={c.text} className={c.bad ? "flagbad" : "flagok"}>{c.bad ? "▲ " : "✓ "}{c.text}</span>)}</div>
        </section>
        <section>
          <h5>4. What could happen</h5>
          <div className="subcol">
            <div><h6>If {sc.rival} buys it first</h6><div className="tl">{sc.rival_first.map((x: string, i: number) => <div key={i}><time>Step {i + 1}</time><p>{x}</p></div>)}</div></div>
            <div><h6>If {o.company} buys it</h6><div className="tl">{sc.we_buy.map((x: string, i: number) => <div key={i}><time>{i === 0 ? "Likely" : "Possible"}</time><p>{x}</p></div>)}</div></div>
          </div>
          <p className="sub" style={{ fontSize: 12 }}>Simulated by the War Room agent from {sc.basis}. A thinking aid, not a forecast.</p>
        </section>
        <section><h5>5. Who's involved</h5><OwnershipGraph g={o.graph!} /></section>
        <section><h5>6. Risks and red flags</h5><ul>{o.risks!.map((x) => <li key={x}>{x}</li>)}</ul><div className="crit">{o.flags!.map((f) => <span key={f}>{f}</span>)}</div></section>
        <section><h5>7. Questions for diligence</h5><ol>{o.questions!.map((q) => <li key={q}>{q}</li>)}</ol></section>
        <section><h5>8. 90-day plan</h5><Plan o={o} /></section>
        <footer>
          <span><b>Sources:</b> {o.sources.join(", ")}.</span>
          <span>Built from public information only. Contains no price or valuation and no non-public information. Not a recommendation to bid.</span>
          <Copy o={o} />
        </footer>
      </article>
      <DecisionBar o={o} />
    </>
  );
}

function ThreatPage({ o }: { o: Overview }) {
  const m = o.market, n0 = m ? 1 : 0;
  return (
    <>
      <article className="doc page">
        <DocHead o={o} kind="Threat to answer" />
        <section><h5>1. What happened</h5><div className="tl">{o.timeline!.map((t, i) => <div key={i}><time>{t.date}</time><p><b>{t.label}:</b> {t.text}</p></div>)}</div></section>
        <section><h5>2. Why it matters for {o.company}</h5><p>{o.analyst}</p><p><b>Suggested:</b> {o.suggest}</p></section>
        {m && <section><h5>3. What the market thinks</h5><p>Over the last year {o.who} returned <b>{m.rival_return >= 0 ? "+" : ""}{m.rival_return}%</b> against <b>{m.base_return >= 0 ? "+" : ""}{m.base_return}%</b> for {m.base_name}. {m.why}</p><p><b>So what for {o.company}:</b> {m.act}</p></section>}
        <section><h5>{3 + n0}. What customers say</h5><ul>{o.voc!.map((v) => <li key={v.topic}><b>{v.sentiment} · {v.topic}</b> {v.text} ({v.mentions} mentions)</li>)}</ul><p><b>Opening for {o.company}:</b> {o.opening}</p></section>
        <section>
          <h5>{4 + n0}. What could happen</h5><p><b>Scenario:</b> {o.scenario.question}</p>
          <div className="tl">{o.scenario.play.map((p: [string, string]) => <div key={p[0]}><time>{p[0].replace("Month ", "M")}</time><p>{p[1]}</p></div>)}</div>
          <p className="sub" style={{ fontSize: 12 }}>Simulated from {o.scenario.basis}.</p>
        </section>
        <section>
          <h5>{5 + n0}. Response options</h5>
          <div className="opts">
            {o.options!.map((x) => (
              <div key={x.title} className={`opt${x.recommended ? " rec" : ""}`}>
                <span className={`sev ${x.recommended ? "opp" : "watch"}`} style={{ alignSelf: "flex-start" }}>{x.recommended ? "Recommended" : "Fallback"}</span>
                <b>{x.title}</b><p>{x.text}</p>
                <div className="rate"><span>Impact</span><b>{x.impact}</b><span>Cost</span><b>{x.cost}</b><span>Risk</span><b>{x.risk}</b></div>
              </div>
            ))}
          </div>
        </section>
        <section><h5>{6 + n0}. 90-day plan</h5><Plan o={o} /></section>
        <footer><span><b>Sources:</b> {o.sources.join("; ")}.</span><Copy o={o} /></footer>
      </article>
      <DecisionBar o={o} />
    </>
  );
}
