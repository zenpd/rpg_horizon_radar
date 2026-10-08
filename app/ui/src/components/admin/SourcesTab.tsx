import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { CalendarClock, CheckCircle2, CircleSlash, RefreshCw } from "lucide-react";

import { getSourcesStatus, runIngest, waitForJob } from "../../services/api";
import type { SourcesStatus } from "../../types";

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return value;
  }
}

function pace(minDays: number) {
  if (minDays === 0) return "every run";
  if (minDays === 1) return "daily";
  if (minDays === 7) return "weekly";
  return `every ${minDays} days`;
}

export default function SourcesTab() {
  const [data, setData] = useState<SourcesStatus | null>(null);
  const [running, setRunning] = useState(false);

  const load = () => {
    getSourcesStatus().then(setData).catch(() => {});
  };
  useEffect(load, []);

  const run = async () => {
    setRunning(true);
    try {
      const job = await waitForJob(await runIngest());
      if (job.status === "failed" || !job.result) {
        toast.error(`Ingestion failed: ${job.error || "unknown error"}`);
      } else {
        toast.success(`Ingestion complete — ${job.result.new_raw_signals} new signals, ${job.result.errors.length} source errors.`);
      }
      load();
    } catch {
      // handled globally
    } finally {
      setRunning(false);
    }
  };

  if (!data) return <div className="text-sm text-gray-400 py-10 text-center">Loading sources…</div>;
  const s = data.scheduler;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="card p-5">
          <p className="section-title flex items-center gap-1.5">
            <CalendarClock size={12} /> Schedule
          </p>
          {s.enabled ? (
            <ul className="text-xs text-gray-600 space-y-1.5">
              <li>
                Live ingestion daily at <strong>{s.ingest_daily_at}</strong> — next {formatDateTime(s.next.ingest)}, last{" "}
                {formatDateTime(s.last.ingest)}.
              </li>
              <li>
                Watchlist discovery every <strong>{s.discovery_every_days} days</strong> — next {formatDateTime(s.next.discovery)}.
                Companies it finds are watched at once.
              </li>
              <li>
                Opportunity Analyst and Sector Scout with the daily news run — next {formatDateTime(s.next.opportunities)}.
              </li>
              <li>
                SWOT Analyst every <strong>{s.swot_every_days} days</strong> (research refreshed first) — next {formatDateTime(s.next.swot)}.
              </li>
              {s.running && <li className="text-amber-600">Running now: {s.running}</li>}
              {s.last_error && <li className="text-rose-600">Last error: {s.last_error}</li>}
            </ul>
          ) : (
            <p className="text-xs text-gray-500">The scheduler is off (SCHEDULER_ENABLED=false). Runs happen only on request.</p>
          )}
        </div>
        <div className="card p-5 flex flex-col">
          <p className="section-title">Last run</p>
          <p className="text-xs text-gray-600">
            {data.last_run
              ? `${formatDateTime(data.last_run.at)} — ${data.last_run.new_raw_signals ?? 0} new signals, ${data.last_run.errors.length} source errors.`
              : "No live run yet."}
          </p>
          <p className="text-xs text-gray-400 mt-2">
            Reasoning model for discovery and SWOT: {data.llm_routes.length ? data.llm_routes.join(" → ") : "none configured"}.
            Scoring never uses it.
          </p>
          <div className="mt-auto pt-4">
            <button type="button" onClick={run} disabled={running} className="btn btn-secondary btn-sm">
              <RefreshCw size={13} className={running ? "animate-spin" : ""} />
              {running ? "Running… (a few minutes)" : "Run ingestion now"}
            </button>
          </div>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-widest text-gray-400 font-bold border-b border-gray-100">
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Key</th>
              <th className="px-4 py-3">Pace per company</th>
              <th className="px-4 py-3">Companies pulled</th>
              <th className="px-4 py-3">Last pull</th>
              <th className="px-4 py-3">Calls today</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {data.connectors.map((c) => (
              <tr key={c.name} className="hover:bg-gray-50/80">
                <td className="px-4 py-3 font-medium text-gray-900">{c.name}</td>
                <td className="px-4 py-3 text-xs text-gray-500">{c.source_type}</td>
                <td className="px-4 py-3">
                  {c.configured ? (
                    <span className="inline-flex items-center gap-1 text-xs text-emerald-600"><CheckCircle2 size={13} /> set</span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs text-gray-400"><CircleSlash size={13} /> not set</span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">{pace(c.min_days)}</td>
                <td className="px-4 py-3 text-xs text-gray-500">{c.entities_pulled}</td>
                <td className="px-4 py-3 text-xs text-gray-500">{formatDateTime(c.last_pull)}</td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {c.budget && c.budget.date === new Date().toISOString().slice(0, 10) ? c.budget.used : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!!data.last_run?.errors.length && (
        <div className="card p-5">
          <p className="section-title">Source errors in the last run</p>
          <ul className="text-xs text-gray-500 space-y-1 font-mono">
            {data.last_run.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
