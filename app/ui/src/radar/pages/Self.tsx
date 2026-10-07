import { useEffect, useState } from "react";
import { api, type Home as HomeData } from "../api";
import { SwotAgentBar, SwotBuild } from "../components/agents";
import { PositionChart } from "../components/charts";
import { SwotBox, SwotDetails } from "../components/ui";
import { useApp } from "../state";

/** Self reflection → Self analysis: each RPG company's own SWOT, and the impact/urgency graph of its
 * opportunities and threats. For All, one tile per company. */
export default function SelfAnalysis() {
  const app = useApp();
  const [d, setD] = useState<HomeData | null>(null);
  const [hl, setHl] = useState<Set<string>>(new Set());
  useEffect(() => { api.home(app.scope).then(setD).catch((e) => app.toast(e.message)); }, [app.scope, app.version]);
  if (!d || d.scope !== app.scope) return <p className="sub">Loading the self analysis…</p>;

  if (d.scope === "All")
    return (
      <>
        <div>
          <span className="crumb"><b>Self reflection</b> / Self analysis · all companies</span>
          <h4>Where each RPG company stands</h4>
          <p className="sub">Each company's SWOT, written weekly by the SWOT Analyst from public facts about the company. Pick one to see its full SWOT and graph.</p>
        </div>
        <div className="swgrid">
          {d.tiles!.map((t) => (
            <button key={t.company} className="swtile" onClick={() => app.setScope(t.company)}>
              <span className="swt-h"><b>{t.company}</b><span className="sub">{t.swot ? `SWOT of ${t.swot.source.at}` : "No SWOT yet"}</span></span>
              {t.swot ? <SwotBox s={t.swot} big={false} /> : <span className="sub" style={{ fontSize: 12.5 }}>Open it to build one.</span>}
            </button>
          ))}
        </div>
      </>
    );

  const co = app.scope;
  return (
    <>
      <div>
        <span className="crumb"><b>Self reflection</b> / Self analysis · {co}</span>
        <h4>{co}: self analysis</h4>
        <p className="sub">{co}'s strengths, weaknesses, opportunities and threats, written weekly by the SWOT Analyst from public facts about {co} and the companies it watches. What it reads and judges {co} on is set in Radar settings → SWOT parameters.</p>
      </div>
      {d.swot ? (
        <>
          <SwotAgentBar co={co} source={d.swot.source} />
          <SwotBox s={d.swot} big hl={hl} dim={hl.size > 0} />
          <div className="panel">
            <h5>SWOT graph</h5>
            <p className="sub" style={{ fontSize: 12.5, marginTop: 0 }}>Each opportunity and threat by impact and urgency (above 50 on both: act now). Hover a point to highlight it in the SWOT.</p>
            <PositionChart co={co} items={d.positions!} onHover={(id) => setHl(id ? new Set([id]) : new Set())} onOpen={(cid) => app.openRow(cid, co)} />
          </div>
          <SwotDetails s={d.swot} />
        </>
      ) : (
        <div className="callout"><b>No SWOT yet</b><p>{d.swot_status?.message}</p><SwotBuild co={co} label="Build SWOT" /></div>
      )}
    </>
  );
}
