import { useEffect, useState } from "react";
import { api, type SignalList, type SignalStatus } from "../api";
import { SignalCardView, ThesisView } from "../components/signals";
import { useApp } from "../state";

/** Radar → M&A Signals: a card per signal (a watched company with public signals). View opens its
 * acquisition thesis; Dismiss moves it to the archive. */
export default function Signals() {
  const app = useApp();
  return <SignalBoard title="M&A Signals" tabs={[["open", "Signals"], ["dismissed", "Archive"]]}
    intro="Each card is a company the RPG company could plausibly acquire — at most half its size, or a target whose size is not verified yet — with public signals worth a look. Competitors too big to buy stay in Competitor Analysis. View opens the acquisition thesis, where you can shortlist it; Dismiss moves it to the archive."
    empty={{ open: `No acquisition targets${app.scope === "All" ? "" : ` for ${app.scope}`} yet. Target discovery runs weekly (or press Find rivals now in Radar settings → Watched companies); a target appears here once it has public signals.`, dismissed: "The archive is empty." }} />;
}

export function SignalBoard({ title, tabs, intro, empty }: { title: string; tabs: [SignalStatus, string][]; intro: string; empty: Partial<Record<SignalStatus, string>> }) {
  const app = useApp();
  const [status, setStatus] = useState<SignalStatus>(tabs[0][0]);
  const [d, setD] = useState<SignalList | null>(null);
  const [sel, setSel] = useState<string | null>(app.signalSel);
  useEffect(() => { api.signals(app.scope, status).then(setD).catch((e) => app.toast(e.message)); }, [app.scope, status, app.version]);
  useEffect(() => { if (app.signalSel) { setSel(app.signalSel); app.clearSignalSel(); } }, [app.signalSel]);
  if (sel) return <ThesisView caseId={sel} onBack={() => setSel(null)} />;
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
        </div>
      )}
      {d.signals.length ? (
        <div className="cards">{d.signals.map((c) => <SignalCardView key={c.id} c={c} onView={() => setSel(c.id)} />)}</div>
      ) : <div className="empty2" style={{ padding: 24 }}>{empty[status]}</div>}
    </>
  );
}
