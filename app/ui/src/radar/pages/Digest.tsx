import { useEffect, useState } from "react";
import { api } from "../api";
import { Findings } from "../components/agents";
import { useApp } from "../state";

/** Self reflection → Weekly digest on the relevant market news. Today: the week's findings of the daily
 * Opportunity Analyst (news about the company, its watched companies and its industry, judged against
 * its SWOT). The weekly analyst overview and recommendations are added by the weekly digest agent. */
export default function Digest() {
  const app = useApp();
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  useEffect(() => { if (app.scope === "All") api.opportunityCounts().then((r) => setCounts(r.counts)).catch(() => setCounts({})); }, [app.scope, app.version]);
  const all = app.scope === "All";
  return (
    <>
      <div>
        <span className="crumb"><b>Self reflection</b> / Weekly digest · {all ? "all companies" : app.scope}</span>
        <h4>This week's market news{all ? "" : ` for ${app.scope}`}</h4>
        <p className="sub">Every morning the Opportunity Analyst reads the news about each RPG company, the companies it watches and its industry, and reports the opportunities and threats it creates for the company's SWOT. Keep a finding to feed it into the next weekly SWOT.</p>
      </div>
      {all ? (
        <div className="swgrid">
          {app.companies.map((co) => (
            <button key={co} className="swtile" onClick={() => app.setScope(co)}>
              <span className="swt-h"><b>{co}</b><span className="sub">{counts ? `${counts[co] || 0} new finding${counts[co] === 1 ? "" : "s"} this week` : "…"}</span></span>
            </button>
          ))}
        </div>
      ) : <Findings co={app.scope} onHover={() => undefined} />}
      <div className="callout analyst" style={{ marginTop: 16 }}>
        <b>Analyst overview and recommendations</b>
        <p>An analyst overview of {all ? "each company's" : `${app.scope}'s`} position across the market, and the areas to improve, will be written here each week from these findings by the weekly digest agent (not built yet).</p>
      </div>
    </>
  );
}
