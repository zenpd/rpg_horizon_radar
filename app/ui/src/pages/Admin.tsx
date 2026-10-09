import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import toast from "react-hot-toast";
import axios from "axios";
import { Building2, Plus, Radio, ScrollText, Trash2, Users } from "lucide-react";

import { usePageMeta } from "../context/PageMetaContext";
import {
  createReviewer,
  deleteReviewer,
  getAuditLog,
  getReviewers,
  getSubsidiaries,
  patchSubsidiaryGate,
} from "../services/api";
import ConfirmModal from "../components/ConfirmModal";
import SourcesTab from "../components/admin/SourcesTab";
import WatchlistTab from "../components/admin/WatchlistTab";
import type { AuditLogEntry, Reviewer, ReviewerCreate, Subsidiary } from "../types";

const TABS = [
  { key: "reviewers", label: "Reviewers", icon: Users },
  { key: "gates", label: "Sector Gates", icon: ScrollText },
  { key: "watchlist", label: "Watchlist", icon: Building2 },
  { key: "sources", label: "Live Sources", icon: Radio },
  { key: "audit", label: "Audit Log", icon: ScrollText },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return value;
  }
}

// Maps raw audit-log action strings onto the four audit-badge classes
// defined in index.css.
function actionBadgeClass(action: string): string {
  if (action === "mark_under_evaluation") return "action-escalate";
  if (["gate_change", "ingest_run", "watchlist_discovery", "swot_generated"].includes(action)) return "action-write";
  if (action === "admin_change") return "action-admin";
  return "action-view";
}

function ReviewersTab() {
  const [reviewers, setReviewers] = useState<Reviewer[]>([]);
  const [subsidiaries, setSubsidiaries] = useState<Subsidiary[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<ReviewerCreate>({
    name: "",
    email: "",
    password: "",
    role: "corp_strategy_reviewer",
    subsidiary_scopes: [],
  });
  const [submitting, setSubmitting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Reviewer | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([getReviewers(), getSubsidiaries()])
      .then(([r, s]) => {
        setReviewers(r);
        setSubsidiaries(s);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const toggleScope = (code: string) => {
    setForm((f) => {
      const has = f.subsidiary_scopes.includes(code);
      return {
        ...f,
        subsidiary_scopes: has
          ? f.subsidiary_scopes.filter((c) => c !== code)
          : [...f.subsidiary_scopes, code],
      };
    });
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.email || !form.password) return;
    setSubmitting(true);
    try {
      await createReviewer(form);
      toast.success("Reviewer added.");
      setForm({ name: "", email: "", password: "", role: "corp_strategy_reviewer", subsidiary_scopes: [] });
      load();
    } catch (err) {
      if (!axios.isAxiosError(err) || err.response?.status !== 403) {
        toast.error("Could not add reviewer.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteReviewer(pendingDelete.id);
      toast.success(`Removed ${pendingDelete.name} from the reviewer list.`);
      setReviewers((prev) => prev.filter((r) => r.id !== pendingDelete.id));
      setPendingDelete(null);
    } catch {
      // handled globally
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-widest text-slate-500 font-bold border-b border-gray-100">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Scopes</th>
              <th className="px-4 py-3">Added</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                  Loading reviewers…
                </td>
              </tr>
            ) : reviewers.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                  No reviewers yet.
                </td>
              </tr>
            ) : (
              reviewers.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50/80 transition-colors">
                  <td className="px-4 py-3 text-slate-900 font-medium">{r.name}</td>
                  <td className="px-4 py-3 text-slate-600">{r.email}</td>
                  <td className="px-4 py-3 text-slate-600">
                    {r.role === "compliance_admin" ? "Compliance Admin" : "Corp Strategy Reviewer"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {(r.subsidiary_scopes || []).map((c) => (
                        <span key={c} className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                          {c}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-500 font-mono text-xs">{formatDateTime(r.created_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => setPendingDelete(r)}
                      className="text-slate-500 hover:text-rose-600"
                      aria-label={`Remove ${r.name}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="card p-5">
        <h3 className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-1.5">
          <Plus size={15} />
          Add reviewer
        </h3>
        <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <input
            type="text"
            placeholder="Full name"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            required
            className="input"
          />
          <input
            type="email"
            placeholder="Email"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            required
            className="input"
          />
          <input
            type="password"
            placeholder="Temporary password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            required
            className="input"
          />
          <select
            value={form.role}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                role: e.target.value as ReviewerCreate["role"],
              }))
            }
            className="input"
          >
            <option value="corp_strategy_reviewer">Corp Strategy Reviewer</option>
            <option value="compliance_admin">Compliance Admin</option>
          </select>

          <div className="sm:col-span-2">
            <p className="text-xs font-medium text-slate-600 mb-1.5">Subsidiary scopes</p>
            <div className="flex flex-wrap gap-1.5">
              {subsidiaries.map((s) => (
                <button
                  type="button"
                  key={s.code}
                  onClick={() => toggleScope(s.code)}
                  className={
                    form.subsidiary_scopes.includes(s.code)
                      ? "chip-open"
                      : "rounded-full px-2.5 py-1 text-xs font-semibold bg-gray-50 text-slate-600 ring-1 ring-gray-200 hover:ring-zen-200"
                  }
                >
                  {s.code}
                </button>
              ))}
            </div>
          </div>

          <div className="sm:col-span-2">
            <button type="submit" disabled={submitting} className="btn btn-restricted">
              {submitting ? "Adding…" : "Add reviewer"}
            </button>
          </div>
        </form>
      </div>

      <ConfirmModal
        open={!!pendingDelete}
        title="Remove reviewer"
        description={
          <>
            Remove <strong>{pendingDelete?.name}</strong> from the named reviewer list? They will lose
            access immediately.
          </>
        }
        confirmLabel="Remove"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}

function GatesTab() {
  const [subsidiaries, setSubsidiaries] = useState<Subsidiary[]>([]);
  const [loading, setLoading] = useState(true);
  const [pendingCode, setPendingCode] = useState<string | null>(null);

  useEffect(() => {
    getSubsidiaries()
      .then(setSubsidiaries)
      .catch(() => setSubsidiaries([]))
      .finally(() => setLoading(false));
  }, []);

  const toggleGate = async (subsidiary: Subsidiary) => {
    const nextValue = !subsidiary.compliance_gate;
    setPendingCode(subsidiary.code);
    setSubsidiaries((prev) =>
      prev.map((s) => (s.code === subsidiary.code ? { ...s, compliance_gate: nextValue } : s))
    );
    try {
      const updated = await patchSubsidiaryGate(subsidiary.code, nextValue);
      setSubsidiaries((prev) => prev.map((s) => (s.code === subsidiary.code ? updated : s)));
      toast.success(`${subsidiary.name} sector gate ${nextValue ? "opened" : "closed"}.`);
    } catch {
      setSubsidiaries((prev) =>
        prev.map((s) => (s.code === subsidiary.code ? { ...s, compliance_gate: subsidiary.compliance_gate } : s))
      );
    } finally {
      setPendingCode(null);
    }
  };

  if (loading) {
    return <div className="text-sm text-slate-500 py-10 text-center">Loading subsidiaries…</div>;
  }

  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-widest text-slate-500 font-bold border-b border-gray-100">
            <th className="px-4 py-3">Subsidiary</th>
            <th className="px-4 py-3">Signal Focus</th>
            <th className="px-4 py-3">Sectors</th>
            <th className="px-4 py-3">Compliance Gate</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {subsidiaries.map((s) => (
            <tr key={s.code} className="hover:bg-gray-50/80 transition-colors">
              <td className="px-4 py-3 text-slate-900 font-medium">
                {s.name} <span className="text-slate-500 font-mono text-xs">({s.code})</span>
              </td>
              <td className="px-4 py-3 text-slate-600 max-w-xs">{s.signal_focus}</td>
              <td className="px-4 py-3 text-slate-500 text-xs">{(s.sectors || []).join(", ")}</td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => toggleGate(s)}
                    disabled={pendingCode === s.code}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${
                      s.compliance_gate ? "bg-emerald-500" : "bg-gray-200"
                    }`}
                    aria-label={`Toggle compliance gate for ${s.name}`}
                  >
                    <span
                      className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-sm transition-transform ${
                        s.compliance_gate ? "translate-x-[18px]" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                  <span className="text-[11px] text-slate-500">{s.compliance_gate ? "Open" : "Awaiting sign-off"}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditTab() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    getAuditLog(100)
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, []);

  const actions = useMemo(() => ["all", ...Array.from(new Set(entries.map((e) => e.action)))], [entries]);

  const filtered = useMemo(() => {
    return entries.filter((e) => {
      if (actionFilter !== "all" && e.action !== actionFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        const haystack = `${e.reviewer_name_snapshot} ${e.resource_type} ${e.resource_id} ${e.detail || ""}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [entries, actionFilter, search]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} className="input w-auto">
          {actions.map((a) => (
            <option key={a} value={a}>
              {a === "all" ? "All actions" : a}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search reviewer, resource, detail…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input flex-1 min-w-[200px]"
        />
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-widest text-slate-500 font-bold border-b border-gray-100">
              <th className="px-4 py-3">Timestamp</th>
              <th className="px-4 py-3">Reviewer</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Resource</th>
              <th className="px-4 py-3">Detail</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                  Loading audit log…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                  No matching entries.
                </td>
              </tr>
            ) : (
              filtered.map((e) => (
                <tr key={e.id} className="odd:bg-white even:bg-gray-50/50">
                  <td className="px-4 py-2.5 text-slate-600 font-mono whitespace-nowrap">{formatDateTime(e.created_at)}</td>
                  <td className="px-4 py-2.5 text-slate-700">{e.reviewer_name_snapshot}</td>
                  <td className="px-4 py-2.5">
                    <span className={actionBadgeClass(e.action)}>{e.action}</span>
                  </td>
                  <td className="px-4 py-2.5 text-slate-500 font-mono">
                    {e.resource_type}#{e.resource_id}
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">{e.detail}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Admin() {
  usePageMeta("Compliance Admin", "Reviewer list, sector gates, watched companies, live sources, and the immutable audit trail.");

  const [tab, setTab] = useState<TabKey>("reviewers");

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-semibold transition-all border ${
                active ? "bg-zen-600 text-white border-zen-600" : "bg-gray-50 text-slate-600 border-gray-200 hover:bg-gray-100"
              }`}
            >
              <Icon size={13} />
              {t.label}
            </button>
          );
        })}
      </div>

      {tab === "reviewers" && <ReviewersTab />}
      {tab === "gates" && <GatesTab />}
      {tab === "watchlist" && <WatchlistTab />}
      {tab === "sources" && <SourcesTab />}
      {tab === "audit" && <AuditTab />}
    </div>
  );
}
