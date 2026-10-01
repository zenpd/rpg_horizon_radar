import { useEffect, useState } from "react";
import { api, type Job } from "../api";
import { Journey } from "../components/ui";
import { useApp } from "../state";

export default function DeepDive() {
  const app = useApp();
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    if (!app.jobId) return;
    let stop = false;
    const poll = async () => {
      const j = await api.job(app.jobId!);
      if (stop) return;
      setJob(j);
      if (j.status === "completed") {
        app.toast(`The deep-dive book is ready: ${j.items.length} page${j.items.length > 1 ? "s" : ""}.`);
        app.bump(); app.setBookPage(0); app.go("book");
      } else setTimeout(poll, 450);
    };
    poll();
    return () => { stop = true; };
  }, [app.jobId]);

  if (!app.jobId) return <p className="sub">No deep dive is running. Shortlist companies on This week and escalate them.</p>;
  const n = job?.items.length ?? 0;
  return (
    <>
      <div>
        <span className="crumb"><b>Deep dive</b> · {n} compan{n === 1 ? "y" : "ies"}</span>
        <h4>Agents are preparing one page per company</h4>
        <p className="sub">This is the expensive work only shortlisted companies get: paid financial data, ownership trees, rival deals and what-if scenarios. About 2 hours in production, a few seconds here.</p>
      </div>
      <Journey step={2} />
      <div className="dd">
        {job?.items.map((it) => {
          const done = it.done_steps >= it.total_steps;
          return (
            <div key={it.case_id} className={done ? "ok" : "run"}>
              <span className="ic">{done ? "✓" : ""}</span>
              <div style={{ minWidth: 0 }}>
                <p><b>{it.who}</b> · {it.title}</p>
                <div className="match" style={{ margin: "6px 0 4px" }}>
                  <div className="pbar"><i style={{ width: `${Math.round((it.done_steps / it.total_steps) * 100)}%` }} /></div>
                  <span className="mono" style={{ fontSize: 11.5 }}>{it.done_steps}/{it.total_steps}</span>
                </div>
                <small>{done || !it.current ? "Page written" : `${it.current.task} · ${it.current.agent}`}</small>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
