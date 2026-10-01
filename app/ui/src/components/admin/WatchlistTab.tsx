import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import toast from "react-hot-toast";
import { Check, ExternalLink, Plus, Search, X } from "lucide-react";

import { addWatchlistEntity, getSubsidiaries, getWatchlist, runDiscovery, updateWatchlistEntity, waitForJob } from "../../services/api";
import type { Subsidiary, WatchlistEntity } from "../../types";

const STATUS_TABS = [
  { key: "proposed", label: "Proposed" },
  { key: "watching", label: "Watching" },
  { key: "dismissed", label: "Dismissed" },
] as const;

function formatDate(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return value;
  }
}

// Real companies only. A discovered company is a proposal until a
// compliance_admin approves it here; only "watching" companies are ingested,
// and every change is audit-logged by the API.
export default function WatchlistTab() {
  const [rows, setRows] = useState<WatchlistEntity[]>([]);
  const [subsidiaries, setSubsidiaries] = useState<Subsidiary[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"proposed" | "watching" | "dismissed">("proposed");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [form, setForm] = useState({ name: "", sectors: [] as string[], nse_symbol: "", query_name: "" });
  const [adding, setAdding] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([getWatchlist(), getSubsidiaries()])
      .then(([w, s]) => {
        setRows(w.filter((e) => !e.is_fictional));
        setSubsidiaries(s);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const sectors = useMemo(() => Array.from(new Set(subsidiaries.flatMap((s) => s.sectors))).sort(), [subsidiaries]);
  const shown = rows.filter((r) => r.status === tab);
  const openGates = subsidiaries.filter((s) => s.compliance_gate).map((s) => s.code);

  const setStatus = async (row: WatchlistEntity, status: "watching" | "dismissed") => {
    setBusyId(row.id);
    try {
      const updated = await updateWatchlistEntity(row.id, { status });
      setRows((prev) => prev.map((r) => (r.id === row.id ? updated : r)));
      toast.success(status === "watching" ? `${row.name} approved — it will be ingested on the next run.` : `${row.name} dismissed.`);
    } catch {
      // handled globally
    } finally {
      setBusyId(null);
    }
  };

  const saveSymbol = async (row: WatchlistEntity, nse_symbol: string) => {
    if (nse_symbol.trim().toUpperCase() === (row.nse_symbol || "")) return;
    try {
      const updated = await updateWatchlistEntity(row.id, { nse_symbol });
      setRows((prev) => prev.map((r) => (r.id === row.id ? updated : r)));
      toast.success(`NSE symbol for ${row.name} saved.`);
    } catch {
      // handled globally
    }
  };

  const discover = async () => {
    setDiscovering(true);
    try {
      const job = await waitForJob(await runDiscovery());
      if (job.status === "failed" || !job.result) {
        toast.error(`Discovery failed: ${job.error || "unknown error"}`);
      } else {
        const r = job.result;
        toast.success(
          `Discovery done — ${r.proposed.length} new proposals, ${r.refreshed.length} confirmed` +
            (r.errors.length ? `; ${r.errors.length} errors: ${r.errors[0]}` : ".")
        );
        setTab("proposed");
        load();
      }
    } catch {
      // handled globally
    } finally {
      setDiscovering(false);
    }
  };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.name || form.sectors.length === 0) return;
    setAdding(true);
    try {
      const created = await addWatchlistEntity(form);
      setRows((prev) => [...prev, created]);
      setForm({ name: "", sectors: [], nse_symbol: "", query_name: "" });
      setTab("watching");
      toast.success(`${created.name} added and approved by you.`);
    } catch {
      toast.error("Could not add the company (already listed, or an unknown sector).");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-gray-500 max-w-2xl leading-relaxed">
          Real, publicly listed companies the live connectors track. Discovery proposes companies for subsidiaries whose
          compliance gate is open ({openGates.join(", ") || "none open"}); nothing is fetched about a company until you approve it.
        </p>
        <button type="button" onClick={discover} disabled={discovering} className="btn btn-secondary btn-sm shrink-0">
          <Search size={13} className={discovering ? "animate-pulse" : ""} />
          {discovering ? "Searching…" : "Find companies now"}
        </button>
      </div>

      <div className="flex items-center gap-1.5 border-b border-gray-100 pb-1">
        {STATUS_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-t-lg transition-colors ${
              tab === t.key ? "text-rose-700 border-b-2 border-rose-600" : "text-gray-400 hover:text-gray-600"
            }`}
          >
            {t.label} <span className="text-gray-300">({rows.filter((r) => r.status === t.key).length})</span>
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-sm text-gray-400 py-10 text-center">Loading watchlist…</div>
      ) : shown.length === 0 ? (
        <div className="text-sm text-gray-400 py-10 text-center border border-dashed border-gray-200 rounded-2xl">
          {tab === "proposed" ? "No proposals waiting. Run discovery or add a company below." : `No ${tab} companies.`}
        </div>
      ) : (
        <div className="card overflow-hidden divide-y divide-gray-50">
          {shown.map((r) => (
            <div key={r.id} className="px-5 py-4 flex flex-col gap-3 lg:flex-row lg:items-start">
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-gray-900">{r.name}</p>
                  <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-500">
                    {r.discovery?.for ? `for ${r.discovery.for}` : r.sectors.join(", ")}
                  </span>
                  {r.discovery?.kind && (
                    <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-600">{r.discovery.kind}</span>
                  )}
                  <span className="text-[10px] text-gray-400">{r.origin === "manual" ? "added by hand" : "found by discovery"}</span>
                </div>
                {r.discovery?.why && <p className="text-xs text-gray-500 mt-1 leading-relaxed">{r.discovery.why}</p>}
                {!!r.discovery?.sources?.length && (
                  <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5">
                    {r.discovery.sources.map((s) => (
                      <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] text-rose-600 hover:underline max-w-xs truncate">
                        {s.title} <ExternalLink size={10} />
                      </a>
                    ))}
                  </div>
                )}
                <p className="text-[10px] text-gray-400 mt-1.5">
                  {r.discovery?.last_seen_at && `Last confirmed by discovery ${formatDate(r.discovery.last_seen_at)}. `}
                  {r.approved_by && `Approved by ${r.approved_by} on ${formatDate(r.approved_at)}. `}
                  {r.status === "watching" && `${r.raw_signal_count} signals${r.score != null ? `, score ${Math.round(r.score)}` : ""}.`}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <input
                  defaultValue={r.nse_symbol || ""}
                  placeholder="NSE symbol"
                  onBlur={(e) => saveSymbol(r, e.target.value)}
                  className="input w-28 text-xs font-mono uppercase"
                  aria-label={`NSE symbol for ${r.name}`}
                />
                {r.status !== "watching" && (
                  <button type="button" disabled={busyId === r.id} onClick={() => setStatus(r, "watching")} className="btn btn-restricted btn-sm">
                    <Check size={13} /> Approve
                  </button>
                )}
                {r.status !== "dismissed" && (
                  <button type="button" disabled={busyId === r.id} onClick={() => setStatus(r, "dismissed")} className="btn btn-ghost btn-sm">
                    <X size={13} /> {r.status === "watching" ? "Stop watching" : "Dismiss"}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="card p-5">
        <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-1.5 mb-4">
          <Plus size={15} /> Add a company by hand
        </h3>
        <form onSubmit={add} className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <input className="input" placeholder="Company name, e.g. JK Tyre & Industries" value={form.name}
                 onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          <input className="input font-mono uppercase" placeholder="NSE symbol (optional)" value={form.nse_symbol}
                 onChange={(e) => setForm((f) => ({ ...f, nse_symbol: e.target.value }))} />
          <input className="input" placeholder="Name in headlines (optional)" value={form.query_name}
                 onChange={(e) => setForm((f) => ({ ...f, query_name: e.target.value }))} />
          <div className="sm:col-span-3">
            <p className="text-xs font-medium text-gray-500 mb-1.5">Sectors (routes its signals to the matching subsidiaries)</p>
            <div className="flex flex-wrap gap-1.5">
              {sectors.map((s) => (
                <button
                  type="button"
                  key={s}
                  onClick={() =>
                    setForm((f) => ({ ...f, sectors: f.sectors.includes(s) ? f.sectors.filter((x) => x !== s) : [...f.sectors, s] }))
                  }
                  className={
                    form.sectors.includes(s)
                      ? "chip-open"
                      : "rounded-full px-2.5 py-1 text-xs font-semibold bg-gray-50 text-gray-500 ring-1 ring-gray-200 hover:ring-rose-200"
                  }
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          <div className="sm:col-span-3">
            <button type="submit" disabled={adding || !form.name || form.sectors.length === 0} className="btn btn-restricted">
              {adding ? "Adding…" : "Add and approve"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
